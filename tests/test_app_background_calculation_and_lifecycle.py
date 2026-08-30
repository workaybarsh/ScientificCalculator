"""Background-calculation commits, history persistence, and app lifecycle.

A worker result reaches the engine only through the Tk-thread commit
boundary.  These tests hold that boundary, the persistence failures that
must not discard a result, and the packaged launch/restart lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from scientific_calculator import app as app_module
from scientific_calculator.calculation_errors import CalculationTimeout
from scientific_calculator.calculator_engine import CalculatorError

App = app_module.App


class _Result:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def config(self, **options: object) -> None:
        if "text" in options:
            self.messages.append(str(options["text"]))


class _CallbackController:
    def __init__(self, invoke: object) -> None:
        self.invoke = invoke
        self.calls: list[tuple[object, str, tuple[object, ...]]] = []

    def start_engine_method(self, core: object, method: str, *args: object, **callbacks: object) -> str:
        self.calls.append((core, method, args))
        self.invoke(callbacks)  # type: ignore[operator]
        return "operation-17"


def _app_with_core(*, history: list[object] | None = None) -> App:
    app = object.__new__(App)
    app.core = SimpleNamespace(
        ans="old answer",
        history=list(history or []),
        memory={"old": 1},
    )
    return app


def test_background_calculation_commits_the_worker_snapshot_on_the_ui_thread() -> None:
    app = _app_with_core(history=[("old", "1")])
    app.result = _Result()
    app._calculation_busy = False
    events: list[tuple[str, object]] = []
    payload = SimpleNamespace(
        ans="new answer",
        history=[("2+2", "4")],
        memory={"A": 4},
        result=4,
    )

    def invoke(callbacks: dict[str, object]) -> None:
        callbacks["on_start"]()  # type: ignore[operator]
        callbacks["on_success"](payload)  # type: ignore[operator]
        callbacks["on_finish"]()  # type: ignore[operator]

    controller = _CallbackController(invoke)
    app.calculation_controller = controller
    app._persist_calculation_history = lambda: events.append(("persist", None))
    app._log_settings_issue = mock.Mock()

    operation = App._run_background_calculation(
        app,
        "evaluate",
        ("2+2",),
        lambda result: events.append(("result", result)),
    )

    assert operation == "operation-17"
    assert controller.calls == [(app.core, "evaluate", ("2+2",))]
    assert app.result.messages == ["Calculating…"]
    assert app.core.ans == "new answer"
    assert app.core.history == [("2+2", "4")]
    assert app.core.memory == {"A": 4}
    assert events == [("result", 4), ("persist", None)]
    assert app._calculation_busy is False
    app._log_settings_issue.assert_not_called()


def test_background_calculation_keeps_results_when_history_persistence_fails() -> None:
    app = _app_with_core()
    app.result = _Result()
    app._calculation_busy = False
    persistence_error = OSError("read-only")
    payload = SimpleNamespace(ans=2, history=[("1+1", "2")], memory={}, result=2)

    def invoke(callbacks: dict[str, object]) -> None:
        callbacks["on_start"]()  # type: ignore[operator]
        callbacks["on_success"](payload)  # type: ignore[operator]
        callbacks["on_finish"]()  # type: ignore[operator]

    app.calculation_controller = _CallbackController(invoke)
    app._persist_calculation_history = mock.Mock(side_effect=persistence_error)
    app._log_settings_issue = mock.Mock()
    received: list[object] = []

    assert App._run_background_calculation(app, "evaluate", ("1+1",), received.append) == "operation-17"

    assert received == [2]
    assert app.core.history == [("1+1", "2")]
    app._log_settings_issue.assert_called_once_with("save history", persistence_error)
    assert app._calculation_busy is False


def test_background_calculation_reports_worker_and_startup_errors_without_leaving_busy_state() -> None:
    worker_error = CalculatorError("Math ERROR: failed")
    app = _app_with_core()
    app.result = _Result()
    app._calculation_busy = False
    app.err = mock.Mock()

    def invoke(callbacks: dict[str, object]) -> None:
        callbacks["on_start"]()  # type: ignore[operator]
        callbacks["on_error"](worker_error)  # type: ignore[operator]
        callbacks["on_finish"]()  # type: ignore[operator]

    app.calculation_controller = _CallbackController(invoke)
    assert App._run_background_calculation(app, "evaluate", ("bad",), mock.Mock()) == "operation-17"
    app.err.assert_called_once_with(worker_error)
    assert app._calculation_busy is False

    startup_error = RuntimeError("controller unavailable")
    startup = _app_with_core()
    startup.err = mock.Mock()

    class RaisingController:
        def start_engine_method(self, *_args: object, **_kwargs: object) -> object:
            raise startup_error

    startup.calculation_controller = RaisingController()
    assert App._run_background_calculation(startup, "evaluate", ("1",), mock.Mock()) is False
    startup.err.assert_called_once_with(startup_error)


def test_history_persistence_filters_invalid_records_and_limits_saved_history() -> None:
    valid = [(f"expression-{index}", str(index)) for index in range(12)]
    app = _app_with_core(history=[("numeric result", 1), ("short",), {"invalid": "record"}, *valid])
    store = SimpleNamespace(save_history=mock.Mock())

    persisted = App._persist_calculation_history(app, store)

    expected = valid[-app_module.SettingsStore.HISTORY_LIMIT :]
    assert persisted == expected
    assert app.core.history == expected
    assert app.history_pos == len(expected)
    store.save_history.assert_called_once_with(expected)


def test_history_load_failure_preserves_stale_memory_and_clear_history_rolls_back() -> None:
    load_error = OSError("database locked")
    app = _app_with_core(history=[("stale", "value")])
    app._settings_store = mock.Mock(return_value=SimpleNamespace(load_history=mock.Mock(side_effect=load_error)))
    app._log_settings_issue = mock.Mock()

    App.load_calculation_history(app)

    assert app.core.history == [("stale", "value")]
    app._log_settings_issue.assert_called_once_with("load history", load_error)

    app.core.history[:] = [("2+2", "4")]
    app.history_pos = 1
    app.save_settings_file = mock.Mock(return_value=False)
    app.err = mock.Mock()

    assert App.clear_calculation_history(app) is False

    assert app.core.history == [("2+2", "4")]
    assert app.history_pos == 1
    error = app.err.call_args.args[0]
    assert isinstance(error, CalculatorError)
    assert app.err.call_args.kwargs == {"clear_input": False}


def test_settings_save_commits_atomically_without_reopening_the_database_on_the_ui_thread() -> None:
    settings = SimpleNamespace(angle_unit="RAD", number_digits=3, engineer_symbol=True, digit_separator=False)
    history = [("2+2", "4")]
    app = _app_with_core(history=history)
    app.core.settings = settings
    app.ui_scale = 125
    app.skin_name = "Blue"
    expected = {
        "schema_version": App.SETTINGS_DATA_VERSION,
        "scale": 125,
        "skin": "Blue",
        "calculator_settings": App._sanitize_calculator_settings(vars(settings)),
    }
    store = SimpleNamespace(save_state=mock.Mock(), load=mock.Mock(), load_history=mock.Mock())
    app._settings_store = mock.Mock(return_value=store)
    app._lcd_message = mock.Mock()
    app._log_settings_issue = mock.Mock()

    assert App.save_settings_file(app, notify=True) is True
    assert app.saved_config == expected
    store.save_state.assert_called_once_with(App._flatten_settings(expected), history)
    store.load.assert_not_called()
    store.load_history.assert_not_called()
    app._lcd_message.assert_called_once_with("Settings saved")


def test_unexpected_errors_are_sanitized_before_the_lcd_and_timeouts_remain_specific() -> None:
    app = object.__new__(App)
    app._clear_active_input_for_error = mock.Mock()
    app._clear_modifiers = mock.Mock()
    app._lcd_message = mock.Mock()

    with mock.patch.object(app_module.LOGGER, "error") as logger:
        App.err(app, RuntimeError("sensitive internal detail"))

    logger.assert_called_once()
    app._clear_active_input_for_error.assert_called_once_with()
    app._clear_modifiers.assert_called_once_with()
    app._lcd_message.assert_called_once_with("Internal ERROR")

    app._clear_active_input_for_error.reset_mock()
    app._lcd_message.reset_mock()
    App.err(app, CalculationTimeout("late"), clear_input=False)
    app._clear_active_input_for_error.assert_not_called()
    app._lcd_message.assert_called_once_with("Math ERROR: calculation timed out")


def test_skin_hotspots_keep_calculation_input_safe_and_dispatch_topmost_button() -> None:
    app = object.__new__(App)
    app._skin_xy = lambda x, y: (x + 1, y + 2)
    app.skin_hotspots = []
    calls: list[str] = []

    App._add_hotspot(app, "AC", (0, 0, 10, 10), lambda: calls.append("ac"))
    name, x1, y1, x2, y2, command = app.skin_hotspots[0]
    assert (name, x1, y1, x2, y2) == ("AC", 1, 2, 11, 12)
    command()
    assert calls == ["ac"]
    calls.clear()

    app.skin_hotspots = [
        ("AC", 0, 0, 10, 10, lambda: calls.append("ac")),
        ("Evaluate", 0, 0, 10, 10, lambda: calls.append("evaluate")),
    ]
    app._calculation_busy = True

    assert App._skin_click(app, SimpleNamespace(x=5, y=5)) == "break"
    assert calls == []

    app.skin_hotspots = [("AC", 0, 0, 10, 10, lambda: calls.append("ac"))]
    assert App._skin_click(app, SimpleNamespace(x=5, y=5)) == "break"
    assert calls == ["ac"]

    app._calculation_busy = False
    app.skin_hotspots = [
        ("bottom", 0, 0, 10, 10, lambda: calls.append("bottom")),
        ("top", 0, 0, 10, 10, lambda: calls.append("top")),
    ]
    assert App._skin_click(app, SimpleNamespace(x=5, y=5)) == "break"
    assert calls[-1] == "top"


def test_history_navigation_clamps_to_real_records_without_touching_empty_history() -> None:
    app = _app_with_core(history=[("1+1", "2"), ("2+2", "4")])
    app.history_pos = 0
    app.set_expr = mock.Mock()
    app.result = _Result()

    App.history_move(app, 50)
    assert app.history_pos == 1
    app.set_expr.assert_called_once_with("2+2")
    assert app.result.messages == ["4"]

    app.set_expr.reset_mock()
    app.result.messages.clear()
    app.core.history = []
    App.history_move(app, -1)
    app.set_expr.assert_not_called()
    assert app.result.messages == []


def test_resource_lookup_and_restart_keep_packaged_launch_lifecycle_explicit(tmp_path: Path) -> None:
    app = object.__new__(App)

    with mock.patch.object(app_module.sys, "_MEIPASS", str(tmp_path), create=True):
        assert App._resource_path(app, "icons/app.ico") == app_module.os.path.join(str(tmp_path), "icons/app.ico")

    with (
        mock.patch.object(app_module.sys, "_MEIPASS", None, create=True),
        mock.patch.object(app_module.os.path, "exists", return_value=False),
    ):
        assert App._resource_path(app, "missing.asset").endswith("scientific_calculator" + app_module.os.sep + "missing.asset")

    restart = object.__new__(App)
    restart.calculation_controller = SimpleNamespace(close=mock.Mock(), cancel=mock.Mock())
    restart.save_settings_file = mock.Mock(return_value=True)
    restart.destroy = mock.Mock()
    with mock.patch.object(app_module, "restart_application") as restart_application:
        App._restart_application(restart)

    restart.calculation_controller.close.assert_called_once_with()
    restart.calculation_controller.cancel.assert_not_called()
    restart.save_settings_file.assert_called_once_with(False)
    restart_application.assert_called_once_with()
    restart.destroy.assert_called_once_with()


@pytest.mark.parametrize(
    ("history_active", "alpha", "shift", "expected"),
    [
        (True, False, False, "history"),
        (False, True, False, "insert"),
        (False, False, True, "solve"),
        (False, False, False, "dialog"),
    ],
)
def test_calc_key_routes_to_the_visible_calculator_action(
    history_active: bool, alpha: bool, shift: bool, expected: str
) -> None:
    app = object.__new__(App)
    app._history_lcd_active = mock.Mock(return_value=history_active)
    app.alpha = alpha
    app.shift = shift
    app.consume = mock.Mock()
    app.insert = mock.Mock()
    app.solve_dialog = mock.Mock()
    app.calc_dialog = mock.Mock()

    App.calc_key(app)

    if expected == "history":
        app.consume.assert_called_once_with()
        app.insert.assert_not_called()
        app.solve_dialog.assert_not_called()
        app.calc_dialog.assert_not_called()
    elif expected == "insert":
        app.insert.assert_called_once_with("=")
        app.consume.assert_not_called()
    elif expected == "solve":
        app.consume.assert_called_once_with()
        app.solve_dialog.assert_called_once_with()
        app.calc_dialog.assert_not_called()
    else:
        app.consume.assert_called_once_with()
        app.calc_dialog.assert_called_once_with()
        app.solve_dialog.assert_not_called()
