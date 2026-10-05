from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from scientific_calculator.app import App
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine
from scientific_calculator.math_template import MathTemplate, TemplateSlot
from scientific_calculator.spreadsheet import SpreadsheetModel


class DummyEntry:
    """Minimal Entry contract used by the LCD controller without a Tk root."""

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls: list[tuple[object, ...]] = []

    def delete(self, *_args: object) -> None:
        self.calls.append(("delete",))
        self.text = ""

    def insert(self, _index: object, text: object) -> None:
        self.calls.append(("insert", str(text)))
        self.text = str(text)

    def get(self) -> str:
        return self.text

    def icursor(self, index: object) -> None:
        self.calls.append(("cursor", index))

    def selection_range(self, start: object, end: object) -> None:
        self.calls.append(("selection_range", start, end))

    def selection_clear(self) -> None:
        self.calls.append(("selection_clear",))

    def focus_set(self) -> None:
        self.calls.append(("focus",))


class CursorEntry(DummyEntry):
    """Entry double that can place calculator-key input at its end."""

    def index(self, _index: object) -> int:
        return len(self.text)


class DummyResult:
    def __init__(self) -> None:
        self.text = ""
        self.calls: list[str] = []

    def config(self, **options: object) -> None:
        if "text" in options:
            self.text = str(options["text"])
            self.calls.append(self.text)


def _event(keysym: str = "", char: str = "", state: int = 0) -> SimpleNamespace:
    return SimpleNamespace(keysym=keysym, char=char, state=state)


def _app(*, flow: dict[str, object] | None = None, text: str = "") -> App:
    """Construct only the state consumed by non-visual LCD methods."""
    app = object.__new__(App)
    app._lcd_flow = flow
    app.expr = DummyEntry(text)
    app.result = DummyResult()
    app.core = ScientificCalculatorEngine(cas_isolated=False)
    app.err = mock.Mock()
    app._clear_active_input_for_error = mock.Mock()
    app._clear_modifiers = mock.Mock()
    return app


def _form_flow(fields: list[dict[str, object]], *, mode: str = "Matrix", index: int = 0) -> dict[str, object]:
    return {
        "mode": mode,
        "phase": "form",
        "title": "Matrix",
        "fields": fields,
        "values": {},
        "draft": {},
        "index": index,
        "last_error": "",
    }


def test_lcd_text_helpers_and_flow_lifecycle_are_bounded_and_nonvisual() -> None:
    app = _app()

    assert App._lcd_clip("one\ntwo", 28) == "one two"
    assert App._lcd_clip("abcdef", 4) == "abc…"
    assert App._history_line("a very long expression", "123456789012345") == "a very long expression = 123456789012345"
    assert App._lcd_title("Matrix values") == "MAT"
    assert App._lcd_title("unmapped workflow") == "UNMAPPED"
    assert app._format_error_message(CalculatorError("Bilinmeyen ad")) == "Unknown name"

    assert App._lcd_flow_active(app) is False
    assert App._history_lcd_active(app) is False
    app._lcd_flow = {"mode": "History"}
    assert App._lcd_flow_active(app) is True
    assert App._history_lcd_active(app) is True
    App._reset_lcd_flow(app)
    assert app._lcd_flow is None


def test_lcd_field_text_current_spec_and_direct_entry_obey_priority_and_bounds() -> None:
    choice = {"key": "kind", "label": "Kind", "type": "choice", "choices": {1: "one", 2: "two"}}
    fields: list[dict[str, object]] = [choice, {"key": "count", "type": "integer", "default": 3}]
    flow = _form_flow(fields)
    flow["values"] = {"kind": "two", "count": 7}
    flow["draft"] = {"kind": "unparsed draft"}
    app = _app(flow=flow, text="default")

    assert App._lcd_field_text(app, flow, choice) == "unparsed draft"
    flow["draft"] = {}
    assert App._lcd_field_text(app, flow, choice) == "2"
    assert App._lcd_field_text(app, flow, fields[1]) == "7"
    assert App._lcd_field_text(app, {"values": {}, "draft": {}}, {**choice, "default": "one"}) == "1"
    assert App._lcd_current_spec(app) is choice
    flow["index"] = 2
    assert App._lcd_current_spec(app) is None
    flow["index"] = 0

    flow["field_armed"] = True
    App._lcd_prepare_direct_entry(app)
    assert app.expr.get() == ""
    assert flow["field_armed"] is False
    assert ("selection_clear",) in app.expr.calls

    flow["phase"] = "results"
    assert App._lcd_current_spec(app) is None
    app.expr.text = "preserve"
    App._lcd_prepare_direct_entry(app)
    assert app.expr.get() == "preserve"


def test_form_rendering_captures_drafts_and_recovers_from_invalid_choice_display() -> None:
    choice = {"key": "operation", "label": "Operation", "type": "choice", "choices": {1: "add", 2: "copy"}}
    detail = {"key": "detail", "label": "Detail", "default": ""}
    app = _app(flow={"mode": "Matrix", "values": {}, "draft": {}, "last_error": ""})

    App._lcd_begin_form(app, "Matrix actions", [choice, detail], "select")

    assert app._lcd_flow["phase"] == "form"
    assert app._lcd_flow["stage"] == "select"
    assert app.expr.get() == ""
    assert app._lcd_flow["field_armed"] is False
    assert "MAT add" in app.result.text
    assert "1/2" not in app.result.text

    App._lcd_capture_draft(app)
    assert app._lcd_flow["draft"] == {"operation": "1"}

    app.expr.text = "2"
    App._lcd_capture_draft(app)
    assert app._lcd_flow["draft"] == {"operation": "2"}
    assert App._lcd_vertical_move(app, 1) is True
    assert app._lcd_flow["index"] == 1
    assert app.expr.get() == ""

    app._lcd_flow["index"] = 0
    app._lcd_flow["draft"] = {"operation": "99"}
    App._lcd_render_field(app)
    assert "choose" in app.result.text


def test_choice_cycle_wraps_and_uses_a_safe_default_when_the_current_text_is_invalid() -> None:
    choice = {"key": "kind", "label": "Kind", "type": "choice", "choices": {1: "one", 2: "two", 3: "three"}}
    app = _app(flow=_form_flow([choice]), text="1")

    assert App._lcd_cycle_choice(app, -1) is True
    assert app.expr.get() == ""
    assert app._lcd_flow["draft"] == {"kind": "3"}

    app.expr.text = "not a number"
    assert App._lcd_cycle_choice(app, 1) is True
    assert app.expr.get() == ""

    app._lcd_flow["fields"] = [{"key": "text"}]
    assert App._lcd_cycle_choice(app, 1) is False


def test_matrix_row_fields_require_the_declared_number_of_values() -> None:
    app = _app(text="1, 2, 3")
    spec = {"key": "matrix_row_0", "label": "row 1", "type": "matrix_row", "columns": 3}

    assert App._lcd_parse_field(app, spec, app.expr.get()) == [1.0, 2.0, 3.0]
    assert App._lcd_parse_field(app, spec, "1+2+3") == [1.0, 2.0, 3.0]
    assert App._lcd_parse_field(app, spec, "1-2+3") == [1.0, -2.0, 3.0]
    assert App._lcd_parse_field(app, spec, "1+1−1") == [1.0, 1.0, -1.0]
    assert App._lcd_parse_field(app, spec, "-1-1-1") == [-1.0, -1.0, -1.0]
    assert App._lcd_parse_field(app, spec, "1−1−1") == [1.0, -1.0, -1.0]
    assert App._lcd_parse_field(app, spec, "-1+2e-3+4") == [-1.0, 0.002, 4.0]
    assert App._lcd_parse_field(app, spec, "-1+2e−3+4") == [-1.0, 0.002, 4.0]
    assert App._lcd_matrix_row_tokens("+2") == ["2"]
    with pytest.raises(CalculatorError, match="row 1 is required"):
        App._lcd_parse_field(app, spec, "")
    with pytest.raises(CalculatorError, match="requires 3 values"):
        App._lcd_parse_field(app, spec, "1 2")
    with pytest.raises(CalculatorError, match="accepts at most 3 values"):
        App._lcd_parse_field(app, spec, "1+2+3+4")

    # Minimal test entries do not implement Tk's cursor API; the guard must
    # leave those non-visual callers usable rather than rejecting input.
    app._lcd_flow = _form_flow([spec])
    assert App._lcd_matrix_row_allows_insert(app, "4") is True
    app.expr = CursorEntry("1+2+3+")
    assert App._lcd_matrix_row_allows_insert(app, "4") is False
    app.expr = CursorEntry("1+2+3")
    assert App._lcd_matrix_row_allows_insert(app, "+") is False
    assert App._lcd_matrix_row_allows_insert(app, "−") is False


def test_text_form_fields_use_the_pure_template_for_left_right_navigation() -> None:
    fields = [
        {"key": "integrand", "label": "f(x)"},
        {"key": "lower", "label": "lower"},
        {"key": "upper", "label": "upper"},
    ]
    app = _app(flow={"mode": "Integral", "values": {}, "draft": {}, "last_error": ""}, text="x^2")
    App._lcd_begin_form(app, "Integral", fields, "calculus")
    app.expr.text = "x^2"

    assert App._lcd_move(app, 1) is True
    assert app._lcd_flow["index"] == 1
    assert app._lcd_flow["draft"] == {"integrand": "x^2"}
    assert App._lcd_move(app, -1) is True
    assert app._lcd_flow["index"] == 0
    assert App._lcd_move(app, -1) is False


def test_template_navigation_rejects_non_form_missing_and_stale_template_states() -> None:
    app = _app(flow={"phase": "other"})
    assert App._lcd_move(app, 1) is False

    app = _app(flow=_form_flow([{"key": "x", "label": "x"}]))
    app._lcd_flow["template"] = None
    assert App._lcd_move(app, 1) is False

    app._lcd_flow["template"] = MathTemplate((TemplateSlot("stale"),), "stale")
    assert App._lcd_move(app, 1) is False

    app._lcd_flow["template"] = MathTemplate((TemplateSlot("x", right="stale"), TemplateSlot("stale")), "x")
    assert App._lcd_move(app, 1) is False


def test_complex_calculus_lcd_flow_keeps_derivative_out_of_the_integral_chooser() -> None:
    app = _app(flow={"mode": "Complex Integral", "source_expression": "z^2", "values": {}, "draft": {}, "last_error": ""})
    app._lcd_flow["values"] = {"calculus_action": "definite"}
    app._reset_lcd_flow = mock.Mock()
    app.set_expr = mock.Mock()
    app.start_integral_template = mock.Mock()
    App._lcd_choose_calculus_action(app)
    app.set_expr.assert_called_once_with("z^2")
    app.start_integral_template.assert_called_once_with()
    app._lcd_flow = None
    assert App._lcd_cycle_choice(app, 1) is False


def test_submit_commits_fields_and_routes_parse_and_completion_errors_to_the_lcd() -> None:
    fields = [
        {"key": "count", "label": "Count", "type": "integer"},
        {"key": "note", "label": "Note", "type": "raw"},
    ]
    app = _app(flow=_form_flow(fields), text="2")
    app._lcd_complete_flow = mock.Mock()

    App._lcd_submit(app)
    assert app._lcd_flow["values"] == {"count": 2}
    assert app._lcd_flow["index"] == 1

    app.expr.text = "  retain spaces  "
    App._lcd_submit(app)
    assert app._lcd_flow["values"] == {"count": 2, "note": "  retain spaces  "}
    app._lcd_complete_flow.assert_called_once_with()

    invalid = _app(flow=_form_flow([{"key": "count", "label": "Count", "type": "integer"}]), text="1.5")
    App._lcd_submit(invalid)
    assert invalid._lcd_flow["values"] == {}
    assert invalid._lcd_flow["last_error"].startswith("Argument ERROR")
    assert invalid.result.text.startswith("ERROR:")
    invalid._clear_active_input_for_error.assert_called_once_with()
    invalid._clear_modifiers.assert_called_once_with()

    completion_error = _app(flow=_form_flow([{"key": "name", "type": "raw"}]), text="A")
    completion_error._lcd_complete_flow = mock.Mock(side_effect=CalculatorError("Math ERROR: failed"))
    App._lcd_submit(completion_error)
    assert completion_error._lcd_flow["last_error"] == "Math ERROR: failed"


def test_submit_dispatches_sheet_and_results_phases_without_parsing_a_form() -> None:
    app = _app(flow={"mode": "Matrix", "phase": "results"})
    app._start_lcd_flow = mock.Mock()

    App._lcd_submit(app)
    app._start_lcd_flow.assert_called_once_with("Matrix")

    app._lcd_flow = {"mode": "Spreadsheet", "phase": "sheet"}
    app._lcd_submit_sheet = mock.Mock()
    App._lcd_submit(app)
    app._lcd_submit_sheet.assert_called_once_with()

    app._lcd_flow = None
    App._lcd_submit(app)


def test_results_and_vertical_navigation_clamp_indices_and_preserve_form_drafts() -> None:
    app = _app(flow={"mode": "Matrix", "values": {}, "draft": {}, "last_error": ""})

    App._lcd_show_results(app, "Matrix result", ["first", "second"])
    assert app._lcd_flow["phase"] == "results"
    assert app.expr.get().startswith("MAT")
    assert "1/2" not in app.expr.get()
    assert app.result.text == "first"

    assert App._lcd_vertical_move(app, 99) is True
    assert app._lcd_flow["result_index"] == 1
    assert app.result.text == "second"
    assert App._lcd_vertical_move(app, -99) is True
    assert app._lcd_flow["result_index"] == 0

    App._lcd_show_results(app, "Matrix result", [])
    assert app._lcd_flow["result_lines"] == ["0"]
    assert app.result.text == "0"

    field = {"key": "name", "label": "Name"}
    app._lcd_flow = _form_flow([field])
    app.expr.text = "draft value"
    assert App._lcd_vertical_move(app, -1) is True
    assert app._lcd_flow["index"] == 0
    assert app._lcd_flow["draft"] == {"name": "draft value"}

    app._lcd_flow = {"mode": "Matrix", "phase": "unknown"}
    assert App._lcd_vertical_move(app, 1) is False
    app._lcd_flow = None
    assert App._lcd_vertical_move(app, 1) is False


def test_lcd_move_routes_sheet_columns_or_choice_cycles_only_when_a_flow_is_active() -> None:
    app = _app(flow=None)
    assert App._lcd_move(app, 1) is False

    app._lcd_flow = {"mode": "Spreadsheet", "phase": "sheet"}
    app._lcd_move_sheet_column = mock.Mock(return_value=True)
    assert App._lcd_move(app, -1) is True
    app._lcd_move_sheet_column.assert_called_once_with(-1)

    app._lcd_flow = _form_flow([])
    app._lcd_cycle_choice = mock.Mock(return_value=False)
    assert App._lcd_move(app, 1) is False
    app._lcd_cycle_choice.assert_called_once_with(1)


def test_lcd_keypress_only_arms_editing_in_allowed_form_and_sheet_states() -> None:
    app = _app(flow=None)
    assert App._lcd_keypress(app, _event(char="7")) is None

    app._lcd_flow = {"phase": "form", "field_armed": True}
    App._lcd_keypress(app, _event(char="7"))
    assert app._lcd_flow["field_armed"] is False
    app._lcd_flow["field_armed"] = True
    App._lcd_keypress(app, _event(keysym="Left"))
    assert app._lcd_flow["field_armed"] is True

    app._lcd_matrix_row_allows_insert = mock.Mock(return_value=False)
    assert App._lcd_keypress(app, _event(char="4")) == "break"

    app._lcd_flow = {"phase": "sheet", "sheet_phase": "browse", "editing": False}
    App._lcd_keypress(app, _event(char="x"))
    assert app._lcd_flow["editing"] is True
    app._lcd_flow["editing"] = False
    App._lcd_keypress(app, _event(keysym="Left"))
    assert app._lcd_flow["editing"] is False
    app._lcd_flow["sheet_phase"] = "tools"
    App._lcd_keypress(app, _event(char="x"))
    assert app._lcd_flow["editing"] is False


def test_lcd_sheet_reference_insert_uses_explicit_source_and_destination() -> None:
    app = _app(flow={
        "sheet_column": 0,
        "sheet_row": 0,
        "values": {
            "sheet_target_column": "B", "sheet_target_row": 1,
            "sheet_reference_prefix": "=1+",
        },
    })
    app.sheet = SpreadsheetModel(app.core)
    app.sheet.set("A1", "2")
    app._lcd_sheet_return = mock.Mock()

    App._lcd_run_sheet_grab(app)

    assert app.sheet.cells["B1"] == "=1+A1"
    assert app.sheet.cache["B1"] == 3
    app._lcd_sheet_return.assert_called_once_with("Inserted A1 into B1")

    app._lcd_flow["values"] = {
        "sheet_target_column": "A", "sheet_target_row": 1,
        "sheet_reference_prefix": "=",
    }
    with pytest.raises(CalculatorError, match="must be different"):
        App._lcd_run_sheet_grab(app)

    app._lcd_flow["values"] = {
        "sheet_target_column": "C", "sheet_target_row": 1,
        "sheet_reference_prefix": "1+",
    }
    with pytest.raises(CalculatorError, match="must start with ="):
        App._lcd_run_sheet_grab(app)


def test_entry_navigation_and_physical_keyboard_follow_the_lcd_state_machine() -> None:
    app = _app(flow=None)
    app.template_kind = None
    app.vertical_move = mock.Mock()
    app.history_move = mock.Mock()
    assert App._entry_vertical_key(app, 1) == "break"
    app.vertical_move.assert_called_once_with(1)

    app._lcd_flow = {"mode": "Matrix"}
    App._entry_vertical_key(app, -1)
    app.vertical_move.assert_has_calls([mock.call(1), mock.call(-1)])
    app._lcd_move = mock.Mock(return_value=True)
    assert App._entry_horizontal_key(app, 1) == "break"
    app._lcd_move.return_value = False
    assert App._entry_horizontal_key(app, 1) is None

    app._calculation_busy = True
    app.ac_key = mock.Mock()
    assert App._physical_keypress(app, _event(keysym="Escape")) == "break"
    app.ac_key.assert_called_once_with()
    assert App._physical_keypress(app, _event(char="1")) == "break"

    app._calculation_busy = False
    app.template_kind = None
    app.equals = mock.Mock()
    app.del_key = mock.Mock()
    app.move = mock.Mock()
    app.insert = mock.Mock()
    assert App._physical_keypress(app, _event(keysym="Return")) == "break"
    app.equals.assert_called_once_with()
    assert App._physical_keypress(app, _event(keysym="BackSpace")) == "break"
    app.del_key.assert_called_once_with()
    assert App._physical_keypress(app, _event(keysym="Right")) == "break"
    app.move.assert_called_once_with(1)
    assert App._physical_keypress(app, _event(char="x")) == "break"
    app.insert.assert_called_once_with("x")
    assert App._physical_keypress(app, _event(char="@")) == "break"
    assert App._physical_keypress(app, _event(char="x", state=0x4)) == "break"
    assert App._physical_keypress(app, _event(keysym="F1")) is None


@pytest.mark.parametrize(
    ("mode", "char", "expected"),
    [
        ("Calculate", "*", "×"),
        ("Calculate", "-", "−"),
        ("Calculate", "x", "x"),
        ("Calculate", "i", None),
        ("Complex", "i", "i"),
        ("Calculate", "@", None),
    ],
)
def test_keyboard_character_tokens_remain_limited_to_visible_calculator_keys(
    mode: str, char: str, expected: str | None
) -> None:
    app = _app()
    app.mode = mode
    assert App._keyboard_character_token(app, char) == expected


def test_lcd_options_and_starter_routing_preserve_mode_and_sheet_safety() -> None:
    app = _app(flow=None)
    App._lcd_options(app)

    app._lcd_flow = {"mode": "Matrix", "phase": "form"}
    app._start_lcd_flow = mock.Mock()
    App._lcd_options(app)
    app._start_lcd_flow.assert_called_once_with("Matrix")

    app._lcd_flow = {"mode": "Spreadsheet", "phase": "results"}
    app._lcd_start_sheet = mock.Mock()
    App._lcd_options(app)
    app._lcd_start_sheet.assert_called_once_with()

    app._lcd_flow = {"mode": "Spreadsheet", "phase": "sheet", "editing": True}
    app._lcd_error = mock.Mock()
    App._lcd_options(app)
    error = app._lcd_error.call_args.args[0]
    assert isinstance(error, CalculatorError)
    assert "Save or cancel" in str(error)

    app._lcd_flow = {"mode": "Spreadsheet", "phase": "sheet", "editing": False}
    app._lcd_sheet_tools = mock.Mock()
    App._lcd_options(app)
    app._lcd_sheet_tools.assert_called_once_with()

    starter = _app()
    starter.cancel_template = mock.Mock()
    starter_names = (
        "_lcd_start_integral",
        "_lcd_start_complex_integral",
        "_lcd_start_matrix",
        "_lcd_start_vector",
        "_lcd_start_statistics",
        "_lcd_start_distribution",
        "_lcd_start_sheet",
        "_lcd_start_table",
        "_lcd_start_equation",
        "_lcd_start_inequality",
        "_lcd_start_ratio",
        "_lcd_start_history",
    )
    for name in starter_names:
        setattr(starter, name, mock.Mock())

    App._start_lcd_flow(starter, "Matrix")
    assert starter._lcd_flow == {"mode": "Matrix", "values": {}, "draft": {}, "last_error": ""}
    starter.cancel_template.assert_called_once_with()
    starter._lcd_start_matrix.assert_called_once_with()
