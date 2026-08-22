from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from scientific_calculator import app as app_module
from scientific_calculator.calculator_engine import CalculatorError

App = app_module.App


class _Result:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def config(self, **options: object) -> None:
        if "text" in options:
            self.messages.append(str(options["text"]))


def _app(*, history: list[object] | None = None) -> App:
    app = object.__new__(App)
    app.core = SimpleNamespace(
        history=list(history or []),
        settings=SimpleNamespace(angle_unit="RAD", number_digits=3, engineer_symbol=False, digit_separator=False),
    )
    return app


def test_settings_payload_validation_rejects_corrupt_values_without_losing_supported_ones() -> None:
    persisted = {
        "schema_version": 1,
        "scale": "125",
        "skin": "Blue",
        "calculator_settings": {
            "angle_unit": "GRA",
            "engineer_symbol": "On",
            "digit_separator": "bad",
            "number_digits": 8,
            "table_two_functions": False,
            "unknown": "discarded",
        },
    }

    migrated = App._migrate_settings(persisted)
    assert migrated is not None
    assert migrated["schema_version"] == App.SETTINGS_DATA_VERSION
    assert persisted["schema_version"] == 1
    clean = App._sanitize_saved_config(migrated)
    assert clean == {
        "schema_version": App.SETTINGS_DATA_VERSION,
        "scale": 125,
        "skin": "Blue",
        "calculator_settings": {
            "angle_unit": "GRA",
            "engineer_symbol": True,
            "number_digits": 8,
            "table_two_functions": False,
        },
    }
    assert App._unflatten_settings(App._flatten_settings(clean)) == clean

    assert App._sanitize_saved_config("not a mapping") == App._default_saved_config()
    assert App._unflatten_settings(["not", "a", "mapping"]) is None
    assert App._sanitize_calculator_settings(["not", "a", "mapping"]) == {}
    assert App._migrate_settings(None) is None
    assert App._migrate_settings({"schema_version": True}) is None
    assert App._migrate_settings({"schema_version": 0}) is None
    assert App._migrate_settings({"schema_version": App.SETTINGS_DATA_VERSION + 1}) is None
    assert App._validated_ui_scale("not a scale") == 100
    assert App._coerce_boolean_setting("unrelated", "leave unchanged") == "leave unchanged"
    assert App._coerce_boolean_setting("engineer_symbol", "Off") is False
    with pytest.raises(ValueError, match="Invalid boolean setting"):
        App._coerce_boolean_setting("engineer_symbol", "yes")


def test_database_path_uses_local_appdata_and_falls_back_to_the_user_configuration_directory(tmp_path: Path) -> None:
    app = object.__new__(App)
    local_root = tmp_path / "local-app-data"

    with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(local_root)}):
        assert App._db_base_path(app) == str(local_root / "ScientificCalculator" / "settings.db")

    fallback_root = tmp_path / "user-home"
    with (
        mock.patch.dict(os.environ, {"LOCALAPPDATA": ""}),
        mock.patch.object(app_module.os.path, "expanduser", return_value=str(fallback_root)),
    ):
        assert App._db_base_path(app) == str(fallback_root / ".scientific_calculator" / "ScientificCalculator" / "settings.db")


def test_settings_load_uses_defaults_when_the_profile_directory_is_unavailable() -> None:
    app = object.__new__(App)
    app._log_settings_issue = mock.Mock()
    blocked = PermissionError("profile is read-only")

    # ``_db_base_path`` must not create the directory itself.  The store owns
    # creation and converts its OSError to an empty/default configuration.
    with (
        mock.patch.object(app_module.os, "makedirs", side_effect=blocked) as makedirs,
        mock.patch.object(app_module.SettingsStore, "_connect", side_effect=blocked),
    ):
        App.load_settings_file(app)

    makedirs.assert_not_called()
    app._log_settings_issue.assert_called_once_with("load", blocked)
    assert app.saved_config == App._default_saved_config()
    assert app.ui_scale == 100
    assert app.skin_name == "Graphite"


def test_settings_issue_log_is_deduplicated_and_never_raises_if_diagnostics_fail(tmp_path: Path) -> None:
    app = object.__new__(App)
    app._db_base_path = mock.Mock(return_value=str(tmp_path / "settings.db"))
    handler = SimpleNamespace(baseFilename=str(tmp_path / "settings.log"), setFormatter=mock.Mock())
    logger = SimpleNamespace(handlers=[], setLevel=mock.Mock(), warning=mock.Mock())
    logger.addHandler = mock.Mock(side_effect=logger.handlers.append)

    with (
        mock.patch.object(app_module.logging, "getLogger", return_value=logger),
        mock.patch.object(app_module, "RotatingFileHandler", return_value=handler) as file_handler,
    ):
        App._log_settings_issue(app, "save", OSError("private disk path"))
        App._log_settings_issue(app, "save", OSError("another private path"))

    assert handler.baseFilename == str(tmp_path / "settings.log")
    assert file_handler.call_count == 1
    # The formatter and class-only message deliberately avoid saving user data.
    assert logger.warning.call_args_list == [
        mock.call("settings_%s_failed error=%s", "save", "OSError"),
        mock.call("settings_%s_failed error=%s", "save", "OSError"),
    ]

    broken = object.__new__(App)
    broken._db_base_path = mock.Mock(side_effect=OSError("no logging directory"))
    App._log_settings_issue(broken, "load", OSError("ignored"))


def test_load_and_persist_history_normalize_empty_and_invalid_records_through_the_default_store() -> None:
    app = _app(history=[("stale", "1")])
    store = SimpleNamespace(load_history=mock.Mock(return_value=None), save_history=mock.Mock())
    app._settings_store = mock.Mock(return_value=store)

    App.load_calculation_history(app)
    assert app.core.history == []

    app.core.history[:] = [("valid", "2"), ("wrong result type", 2), ["also valid", "3"], ("too", "many", "parts")]
    assert App._persist_calculation_history(app) == [("valid", "2"), ("also valid", "3")]
    assert app.core.history == [("valid", "2"), ("also valid", "3")]
    assert app.history_pos == 1
    store.save_history.assert_called_once_with([("valid", "2"), ("also valid", "3")])


def test_loading_settings_applies_only_supported_engine_properties() -> None:
    app = _app()
    raw = {
        "schema_version": App.SETTINGS_DATA_VERSION,
        "scale": 150,
        "skin": "Pink",
        "calculator.angle_unit": "GRA",
        "calculator.engineer_symbol": "On",
        "calculator.missing_property": "ignored",
    }
    app._settings_store = mock.Mock(return_value=SimpleNamespace(load=mock.Mock(return_value=raw)))

    App.load_settings_file(app)
    App.apply_saved_engine_settings(app)

    assert app.ui_scale == 150
    assert app.skin_name == "Pink"
    assert app.core.settings.angle_unit == "GRA"
    assert app.core.settings.engineer_symbol is True
    assert not hasattr(app.core.settings, "missing_property")


def test_settings_store_factory_and_save_failure_keep_the_current_session_usable() -> None:
    app = _app(history=[("one", "1"), ("invalid", 2)])
    app._db_base_path = mock.Mock(return_value="C:/safe/settings.db")
    app._log_settings_issue = mock.Mock()
    sentinel = object()
    with mock.patch.object(app_module, "SettingsStore", return_value=sentinel) as settings_store:
        assert App._settings_store(app) is sentinel
    settings_store.assert_called_once_with("C:/safe/settings.db", app._log_settings_issue)

    app.ui_scale = 100
    app.skin_name = "Graphite"
    write_error = OSError("read-only")
    app._settings_store = mock.Mock(return_value=SimpleNamespace(save_state=mock.Mock(side_effect=write_error)))
    app.err = mock.Mock()

    assert App.save_settings_file(app, notify=False) is False
    assert app.core.history == [("one", "1")]
    app._log_settings_issue.assert_called_once_with("save", write_error)
    app.err.assert_not_called()

    app._settings_store = mock.Mock(return_value=SimpleNamespace(load_history=mock.Mock(side_effect=write_error)))
    App.load_calculation_history(app)
    assert app.core.history == []
    assert app._log_settings_issue.call_args_list[-1] == mock.call("load history", write_error)

    sparse = _app()
    sparse.core.settings = SimpleNamespace()
    sparse.saved_config = {"calculator_settings": {"angle_unit": "GRA"}}
    App.apply_saved_engine_settings(sparse)
    assert not hasattr(sparse.core.settings, "angle_unit")


def test_lifecycle_still_restarts_or_destroys_when_persistence_is_unavailable() -> None:
    restart = object.__new__(App)
    restart.save_settings_file = mock.Mock(return_value=False)
    restart.destroy = mock.Mock()
    restart.calculation_controller = SimpleNamespace(close=mock.Mock(), cancel=mock.Mock())
    with mock.patch.object(app_module, "restart_application") as restart_application:
        App._restart_application(restart)
    restart.calculation_controller.close.assert_called_once_with()
    restart.calculation_controller.cancel.assert_not_called()
    restart_application.assert_called_once_with()
    restart.destroy.assert_called_once_with()

    closing = object.__new__(App)
    closing.calculation_controller = SimpleNamespace(close=mock.Mock())
    closing.save_settings_file = mock.Mock(side_effect=OSError("read-only"))
    closing.destroy = mock.Mock()
    with pytest.raises(OSError, match="read-only"):
        App._on_close(closing)
    closing.calculation_controller.close.assert_called_once_with()
    closing.destroy.assert_called_once_with()


def test_error_helpers_keep_errors_on_the_lcd_and_do_not_clear_when_told_to_preserve_input() -> None:
    app = object.__new__(App)
    app._clear_active_input_for_error = mock.Mock()
    app._clear_modifiers = mock.Mock()
    app._lcd_message = mock.Mock()

    App.err(app, "Bilinmeyen ad: x", clear_input=False)
    app._clear_active_input_for_error.assert_not_called()
    app._clear_modifiers.assert_called_once_with()
    app._lcd_message.assert_called_once_with("Unknown name: x")

    app._lcd_flow = None
    app.err = mock.Mock()
    App._lcd_error(app, CalculatorError("Math ERROR: bad input"))
    app.err.assert_called_once_with(mock.ANY)

    app._lcd_flow = {"phase": "form"}
    app._format_error_message = mock.Mock(return_value="translated")
    app._clear_active_input_for_error = mock.Mock()
    app._clear_modifiers = mock.Mock()
    app.result = _Result()
    App._lcd_error(app, CalculatorError("ignored"))
    assert app._lcd_flow["last_error"] == "translated"
    app._clear_active_input_for_error.assert_called_once_with()
    app._clear_modifiers.assert_called_once_with()
    assert app.result.messages == ["ERROR: translated"]


def test_lcd_message_safely_handles_a_missing_result_widget_and_clips_visible_text() -> None:
    app = object.__new__(App)
    App._lcd_message(app, "this must not crash before the UI exists")

    app.result = _Result()
    App._lcd_message(app, "x" * 40)
    assert app.result.messages == ["x" * 27 + "…"]
