from __future__ import annotations

from types import SimpleNamespace

import pytest
import sympy as sp

from scientific_calculator import app as app_module
from scientific_calculator.application_persistence import ApplicationPersistence
from scientific_calculator.application_services import ApplicationServices
from scientific_calculator.calculation_worker import CalculationOperation, CalculationOperationRegistry
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine
from scientific_calculator.engine.distributions import distribution
from scientific_calculator.engine.expression_normalization import (
    normalize_expression,
    percent_operand_start,
    rewrite_postfix_percent,
)
from scientific_calculator.engine.outcomes import NO_ANS_UPDATE, EngineOutcome
from scientific_calculator.expression_document import (
    EngineeringPrefixSpan,
    ExpressionDocument,
    TextSpan,
)
from scientific_calculator.history import CalculationHistoryEntry
from scientific_calculator.lcd_flow_state import LCDFlowState
from scientific_calculator.settings_codec import SettingsCodec, SettingsPolicy
from scientific_calculator.spreadsheet_cursor import SpreadsheetCursor
from scientific_calculator.template_session import TemplateSession


class Entry:
    def __init__(self, text="", cursor=None):
        self.text, self.cursor = text, len(text) if cursor is None else cursor

    def get(self): return self.text
    def delete(self, *_args): self.text = ""
    def insert(self, _index, value): self.text = str(value)
    def icursor(self, value): self.cursor = value
    def index(self, _index): return self.cursor


class Store:
    def __init__(self) -> None:
        self.values = {"scale": 100}
        self.history = [CalculationHistoryEntry("1+1", "2")]
        self.calls: list[tuple] = []

    def load(self):
        return self.values

    def load_history(self):
        return self.history

    def save_history(self, entries):
        self.calls.append(("history", entries))

    def save_state(self, values, entries):
        self.calls.append(("state", values, entries))

    def reset_defaults(self):
        self.calls.append(("reset",))


def test_application_persistence_normalizes_and_delegates() -> None:
    store = Store()
    persistence = ApplicationPersistence(lambda: store, history_limit=1)
    assert persistence.load_settings() == {"scale": 100}
    assert persistence.load_history() == store.history
    assert persistence.normalize_history([("1", "1"), object()]) == [CalculationHistoryEntry("1", "1")]
    assert persistence.normalize_history(object()) == []
    persistence.save_history(store.history)
    persistence.save_state({"scale": 125}, store.history)
    persistence.reset_defaults()
    assert [call[0] for call in store.calls] == ["history", "state", "reset"]


def _codec() -> SettingsCodec:
    return SettingsCodec(
        SettingsPolicy(
            3,
            frozenset({75, 100, 125}),
            frozenset({"Graphite", "Blue"}),
            frozenset({"enabled"}),
            {"angle": frozenset({"RAD", "DEG"})},
        )
    )


def test_settings_codec_covers_validation_migration_and_wire_format() -> None:
    codec = _codec()
    assert codec.default_config(100)["scale"] == 100
    assert codec.coerce_boolean("other", "value") == "value"
    assert codec.coerce_boolean("enabled", True) is True
    assert codec.coerce_boolean("enabled", "On") is True
    assert codec.coerce_boolean("enabled", "Off") is False
    with pytest.raises(ValueError):
        codec.coerce_boolean("enabled", "yes")
    assert codec.validated_ui_scale("125") == 125
    assert codec.validated_ui_scale("bad") == 100
    assert codec.validated_skin_name("Blue") == "Blue"
    assert codec.validated_skin_name(4) == "Graphite"
    assert codec.sanitize_calculator_settings("bad") == {}
    assert codec.sanitize_calculator_settings({"enabled": "On", "table_two_functions": True, "number_digits": 2, "angle": "RAD", "bad": 1}) == {"enabled": True, "table_two_functions": True, "number_digits": 2, "angle": "RAD"}
    assert codec.sanitize_calculator_settings({"enabled": "bad", "table_two_functions": 1, "number_digits": True, "angle": "bad"}) == {}
    assert codec.sanitize_saved_config(None, default_scale=75)["scale"] == 75
    assert codec.sanitize_saved_config({"scale": 125, "skin": "Blue", "calculator_settings": {"enabled": False}}, default_scale=100)["calculator_settings"] == {"enabled": False}
    assert codec.migrate(None) is None
    assert codec.migrate({"schema_version": True}) is None
    assert codec.migrate({"schema_version": 4}) is None
    assert codec.migrate({"schema_version": 1}) == {"schema_version": 3}
    assert codec.migrate({"schema_version": 3}) == {"schema_version": 3}
    assert codec.flatten({"schema_version": 3, "scale": 125, "skin": "Blue", "calculator_settings": {"enabled": True}}) == {"schema_version": 3, "scale": 125, "skin": "Blue", "calculator.enabled": True}
    assert codec.flatten({"calculator_settings": "bad"})["scale"] == 100
    assert codec.unflatten(None) is None
    assert codec.unflatten({"calculator.enabled": True, 4: "ignored"}) == {"schema_version": 3, "scale": 100, "skin": "Graphite", "calculator_settings": {"enabled": True}}


def test_lcd_flow_state_named_accessors_and_promotion() -> None:
    assert LCDFlowState.promote(None) is None
    state = LCDFlowState.promote({"mode": "Matrix"})
    assert isinstance(state, LCDFlowState)
    assert LCDFlowState.promote(state) is state
    for name, value in (("mode", "Table"), ("phase", "form"), ("stage", "run"), ("title", "T"), ("values", {"x": 1}), ("draft", {"x": "1"}), ("fields", ["x"]), ("index", 1), ("field_armed", True), ("result_lines", ["1"]), ("result_index", 0), ("result_offset", 2), ("template", "t"), ("last_error", "e")):
        setattr(state, name, value)
        assert getattr(state, name) == value


def test_template_session_cursor_and_spreadsheet_cursor_rules() -> None:
    with pytest.raises(ValueError):
        TemplateSession("x", {}, [], 0)
    with pytest.raises(ValueError):
        TemplateSession("x", {"a": ""}, ["a"], 1)
    with pytest.raises(ValueError):
        TemplateSession("x", {}, ["a"], 0)
    session = TemplateSession("x", {"a": "hi", "b": ""}, ["a", "b"], 0, {"a": 99})
    assert session.cursors["a"] == 2
    assert session.active_key == "a"
    assert session.move(-1) is False
    assert session.move(1) is True and session.active_key == "b"
    assert session.snapshot().fields == session.fields
    with pytest.raises(ValueError):
        SpreadsheetCursor(5, 0)
    cursor = SpreadsheetCursor.from_flow({"sheet_column": 1, "sheet_row": 2, "editing": False})
    assert cursor.address == "B3"
    assert cursor.move_column(-4).address == "A3"
    assert cursor.move_row(100).address == "B45"
    editing = SpreadsheetCursor(1, 2, True)
    assert editing.move_column(1) is editing and editing.move_row(1) is editing
    flow: dict[str, object] = {}
    cursor.apply_to(flow)
    assert flow == {"sheet_column": 1, "sheet_row": 2, "editing": False}


def test_application_services_accepts_factories() -> None:
    engine = SimpleNamespace()
    services = ApplicationServices.build(lambda: engine, lambda value: ("session", value), lambda value: ("sheet", value))
    assert services.engine is engine
    assert services.calculation_session == ("session", engine)
    assert services.spreadsheet == ("sheet", engine)


def test_explicit_operation_registry_and_gradian_vector_angle() -> None:
    registry = CalculationOperationRegistry({})
    with pytest.raises(CalculatorError, match="not allowed"):
        registry.resolve(CalculationOperation.EVALUATE)
    engine = ScientificCalculatorEngine(cas_isolated=False)
    assert engine.vector_op("angle", [1, 0], [0, 1]) == pytest.approx(1.5707963267948966)
    engine.settings.angle_unit = "GRA"
    assert engine.vector_op("angle", [1, 0], [0, 1]) == pytest.approx(100)


def test_distribution_service_retains_exact_integer_parameter_rules() -> None:
    assert distribution("Binomial PD", {"x": 2.0, "N": 4.0, "p": 0.5}) == pytest.approx(0.375)
    assert distribution("Binomial PD", {"x": sp.Integer(2), "N": 4, "p": 0.5}) == pytest.approx(0.375)
    with pytest.raises(CalculatorError, match="negatif olmayan"):
        distribution("Binomial PD", {"x": True, "N": 4, "p": 0.5})
    with pytest.raises(CalculatorError, match="Argument ERROR: x"):
        distribution("Binomial PD", {"N": 4, "p": 0.5})


def test_expression_normalization_service_enforces_lexical_boundaries() -> None:
    calls = frozenset({"sin"})
    with pytest.raises(CalculatorError, match="İfade çok uzun"):
        normalize_expression("²", maximum_length=1, allowed_call_names=calls)
    with pytest.raises(CalculatorError, match="sol değer gerekli"):
        rewrite_postfix_percent("%", calls)
    with pytest.raises(CalculatorError, match="geçerli sol değer gerekli"):
        rewrite_postfix_percent("@%", calls)
    assert percent_operand_start("@", calls) is None
    assert ScientificCalculatorEngine._rewrite_postfix_percent("2%") == "(2/100)"


def test_engine_outcome_distinguishes_no_ans_update_from_empty_values() -> None:
    untouched = EngineOutcome("value")
    assert untouched.ans is NO_ANS_UPDATE
    assert repr(NO_ANS_UPDATE) == "NO_ANS_UPDATE"
    assert not untouched.updates_ans and not untouched.has_state_changes
    changed = EngineOutcome(None, ans=None, history=(CalculationHistoryEntry("x", "0"),), memory_updates={"M": 0})
    assert changed.updates_ans and changed.has_state_changes


def test_expression_document_keeps_semantic_prefixes_atomic() -> None:
    assert ExpressionDocument.from_text("").display == ""
    with pytest.raises(ValueError):
        TextSpan("")
    with pytest.raises(ValueError):
        EngineeringPrefixSpan("X")
    document = ExpressionDocument.from_text("500").insert_engineering_prefix(3, "k")
    assert document.display == "500k"
    assert document.source == "500×10^(3)"
    assert document.insert_text(3, " ").display == "500 k"
    assert document.insert_text(4, "!").display == "500k!"
    assert document.insert_text(2, "").display == "500k"
    assert document.delete_backward(0) is document
    assert document.delete_forward(99) is document
    assert document.delete_backward(4).display == "500"
    assert document.delete_forward(3).display == "500"
    assert document.delete_backward(2).display == "50k"
    assert ExpressionDocument.from_text("ab").insert_text(1, "x").display == "axb"
    assert ExpressionDocument.from_text("ab").insert_text(0, "x").display == "xab"
    assert ExpressionDocument.from_text("a").delete_forward(0).display == ""


def test_app_document_helpers_keep_display_and_source_separate(monkeypatch) -> None:
    app = object.__new__(app_module.App)
    app.mode = "Calculate"; app.template_kind = None; app._lcd_flow = None
    app.expr = Entry("500", 3); app.undo = []; app._expression_document = ExpressionDocument.from_text("500")
    app._begin_independent_edit = lambda: None; app._lcd_prepare_direct_entry = lambda: None
    app.consume = lambda: None; app.status_refresh = lambda: None
    app_module.App._insert_engineering_prefix(app, "k")
    assert app.expr.text == "500k"
    assert app_module.App._expression_source(app) == "500×10^(3)"
    app._history_documents = {"x": app._expression_document}
    app_module.App._recall_expression(app, "x")
    assert app.expr.text == "500k"
    app._history_documents = {}
    app.set_expr = lambda value: setattr(app.expr, "text", value)
    app_module.App._recall_expression(app, "plain")
    assert app.expr.text == "plain"
    app._last_submitted_expression = None; app._history_entries = lambda: []
    app_module.App._record_submitted_expression(app, "500×10^(3)")
    assert app._history_documents["500×10^(3)"].display == "500k"


def test_app_document_editing_handles_external_changes_and_atomic_delete() -> None:
    app = object.__new__(app_module.App)
    app.mode = "Calculate"; app.template_kind = None; app._lcd_flow = None
    app.expr = Entry("abc", 1); app.undo = []; app.overwrite = True; app.shift = False; app.alpha = False
    app._expression_document = ExpressionDocument.from_text("old")
    app._history_lcd_active = lambda: False; app._lcd_matrix_row_allows_insert = lambda _value: True
    app._begin_independent_edit = lambda: None; app._lcd_prepare_direct_entry = lambda: None
    app.consume = lambda: None; app.status_refresh = lambda: None
    assert app_module.App._expression_document_for_entry(app).display == "abc"
    app_module.App.insert(app, "X")
    assert app.expr.text == "aXc"
    app.overwrite = False
    app_module.App.insert(app, "Y")
    assert app.expr.text == "aXYc"
    app.expr.icursor(2)
    app_module.App.del_key(app)
    assert app.expr.text == "aYc"
    app.alpha = True
    app.undo = [ExpressionDocument.from_text("saved")]
    app_module.App.del_key(app)
    assert app.expr.text == "saved"
    app.undo = []
    app_module.App.del_key(app)
    app.alpha = False; app.expr.icursor(0)
    app_module.App.del_key(app)
    app.mode = "Base-N"
    assert app_module.App._expression_source(app) == "saved"
    assert app_module.App._insert_engineering_prefix(app, "k") is None


def test_app_document_helpers_tolerate_lightweight_entries_and_history_cap() -> None:
    app = object.__new__(app_module.App)
    app.mode = "Calculate"; app.template_kind = None; app._lcd_flow = None
    app.expr = SimpleNamespace(get=lambda: (_ for _ in ()).throw(AttributeError()))
    assert app_module.App._expression_document_for_entry(app).display == ""
    app.expr = Entry("0")
    app._expression_document = ExpressionDocument.from_text("0")
    app._history_entries = lambda: []
    for number in range(11):
        document = ExpressionDocument.from_text(str(number))
        app._expression_document = document
        app_module.App._record_submitted_expression(app, document.source)
    assert len(app._history_documents) == 10


def test_engineering_display_cycles_and_reports_invalid_values() -> None:
    app = object.__new__(app_module.App)
    app.mode = "Calculate"; app.shift = False; app._engineering_exponent = None
    app.consume = lambda: None
    output: list[str] = []
    errors: list[Exception] = []
    app._show_completed_result = output.append; app.err = errors.append
    app.core = SimpleNamespace(ans=1234)
    app_module.App.eng_key(app)
    app_module.App.eng_key(app)
    app.shift = True
    app_module.App.eng_key(app)
    assert output == ["1.234×10^3", "1234×10^0", "1.234×10^3"]
    app.shift = False; app.core.ans = 0; app._engineering_exponent = None
    app_module.App.eng_key(app)
    assert output[-1] == "0×10^0"
    app.core.ans = float("inf")
    app_module.App.eng_key(app)
    assert "finite real" in str(errors[-1])


def test_macos_geometry_fallback_is_bounded(monkeypatch) -> None:
    app = object.__new__(app_module.App)
    app.ui_scale = 100; app._sp = lambda value: value; app._validated_ui_scale = lambda value: value
    app.update_idletasks = lambda: None; app.winfo_width = lambda: 400; app.winfo_height = lambda: 900
    app.skin_canvas = SimpleNamespace(winfo_width=lambda: 400, winfo_height=lambda: 900)
    rebuilt = []; app._rebuild_scaled_ui = lambda: rebuilt.append(True)
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    assert app_module.App._verify_skin_geometry(app) is True
    assert app.ui_scale == 75 and rebuilt == [True]
    app.winfo_width = lambda: 480; app.winfo_height = lambda: 980
    app.skin_canvas = SimpleNamespace(winfo_width=lambda: 480, winfo_height=lambda: 980)
    assert app_module.App._verify_skin_geometry(app) is False
    callbacks = []; app.after_idle = callbacks.append
    app_module.App._schedule_skin_geometry_validation(app)
    assert callbacks == [app._verify_skin_geometry]


def test_macos_geometry_validation_handles_transient_and_tk_failures(monkeypatch) -> None:
    app = object.__new__(app_module.App)
    app.ui_scale = 100; app._sp = lambda value: value; app._validated_ui_scale = lambda value: value
    app.update_idletasks = lambda: None; app.winfo_width = lambda: 1; app.winfo_height = lambda: 1
    app.skin_canvas = SimpleNamespace(winfo_width=lambda: 1, winfo_height=lambda: 1)
    app.after = lambda delay, callback: setattr(app, "scheduled", (delay, callback))
    app._rebuild_scaled_ui = lambda: pytest.fail("transient geometry must not rebuild")
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    assert app_module.App._verify_skin_geometry(app) is False
    assert app.scheduled[0] == 50 and app._skin_geometry_retry_count == 1
    assert app_module.App._verify_skin_geometry(app) is False
    app.after = lambda *_args: (_ for _ in ()).throw(AttributeError())
    app._skin_geometry_retry_count = 0
    assert app_module.App._verify_skin_geometry(app) is False
    assert app._skin_geometry_validation_scheduled is False
    app.update_idletasks = lambda: (_ for _ in ()).throw(AttributeError())
    assert app_module.App._verify_skin_geometry(app) is False
    app.after_idle = lambda *_args: (_ for _ in ()).throw(AttributeError())
    app._skin_geometry_validation_scheduled = False
    app_module.App._schedule_skin_geometry_validation(app)
    assert app._skin_geometry_validation_scheduled is False
    monkeypatch.setattr(app_module.sys, "platform", "win32")
    assert app_module.App._verify_skin_geometry(app) is False
    app_module.App._schedule_skin_geometry_validation(app)


def test_macos_geometry_skips_already_tried_scales(monkeypatch) -> None:
    app = object.__new__(app_module.App)
    app.ui_scale = 75; app._sp = lambda value: value; app._validated_ui_scale = lambda value: value
    app.update_idletasks = lambda: None; app.winfo_width = lambda: 10; app.winfo_height = lambda: 10
    app.skin_canvas = SimpleNamespace(winfo_width=lambda: 10, winfo_height=lambda: 10)
    app._skin_geometry_checked_scales = {40, 50, 60, 75}
    monkeypatch.setattr(app_module.sys, "platform", "darwin")
    assert app_module.App._verify_skin_geometry(app) is False


def test_gui_smoke_and_main_gui_branch(monkeypatch) -> None:
    events: list[str] = []

    class Root:
        def withdraw(self): events.append("withdraw")
        def update_idletasks(self): events.append("update")
        def destroy(self): events.append("destroy")

    class Photo:
        def __init__(self, *_args, **_kwargs): pass
        def width(self): return 1
        def height(self): return 1

    monkeypatch.setattr(app_module.tk, "Tk", Root)
    monkeypatch.setattr(app_module.ImageTk, "PhotoImage", Photo)
    app_module.run_gui_smoke_test()
    assert events == ["withdraw", "update", "destroy"]

    class InvalidPhoto(Photo):
        def height(self): return 0

    monkeypatch.setattr(app_module.ImageTk, "PhotoImage", InvalidPhoto)
    with pytest.raises(RuntimeError, match="invalid image"):
        app_module.run_gui_smoke_test()
    assert events[-1] == "destroy"
    monkeypatch.setattr(app_module.sys, "argv", ["calculator", "--gui-smoke-test"])
    calls: list[bool] = []
    monkeypatch.setattr(app_module, "run_gui_smoke_test", lambda: calls.append(True))
    app_module.main()
    assert calls == [True]
    monkeypatch.setattr(app_module, "run_gui_smoke_test", lambda: (_ for _ in ()).throw(RuntimeError("bad bridge")))
    with pytest.raises(SystemExit):
        app_module.main()
