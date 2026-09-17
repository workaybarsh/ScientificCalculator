"""Keyboard routing across entry, template, history, and LCD flows.

Every key must reach the action a user can actually see.  These tests keep
the modifier, navigation, editing, and template-dispatch routes distinct so
a shortcut cannot quietly bypass the visible LCD flow.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from scientific_calculator import app as app_module
from scientific_calculator.app import App
from scientific_calculator.calculation_result import CalculationResult, ResultStatus
from scientific_calculator.calculator_engine import CalculatorError
from scientific_calculator.history import CalculationHistoryEntry


class _Entry:
    """Small Entry double that preserves the edit operations under test."""

    def __init__(self, text: str = "", cursor: int = 0) -> None:
        self.text = text
        self.cursor = cursor
        self.operations: list[tuple[object, ...]] = []

    def get(self) -> str:
        return self.text

    def index(self, _index: object) -> int:
        return self.cursor

    def icursor(self, index: int) -> None:
        self.cursor = index
        self.operations.append(("icursor", index))

    def delete(self, start: int, end: object | None = None) -> None:
        self.operations.append(("delete", start, end))
        if end in (None, start + 1):
            self.text = self.text[:start] + self.text[start + 1 :]
        elif end == app_module.tk.END:
            self.text = self.text[:start]

    def insert(self, index: int, value: object) -> None:
        value = str(value)
        self.operations.append(("insert", index, value))
        self.text = self.text[:index] + value + self.text[index:]


class _Result:
    def __init__(self) -> None:
        self.text = ""

    def config(self, **options: object) -> None:
        self.text = str(options.get("text", self.text))


class _Menu:
    instances: list[_Menu] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.commands: dict[str, object] = {}
        self.cascades: dict[str, _Menu] = {}
        self.popup_calls: list[tuple[object, object]] = []
        self.released = False
        self.__class__.instances.append(self)

    def add_command(self, *, label: str, command: object) -> None:
        self.commands[label] = command

    def add_cascade(self, *, label: str, menu: _Menu) -> None:
        self.cascades[label] = menu

    def add_separator(self) -> None:
        pass

    def tk_popup(self, x: object, y: object) -> None:
        self.popup_calls.append((x, y))

    def grab_release(self) -> None:
        self.released = True


def _event(*, keysym: str = "", char: str = "", state: int = 0) -> SimpleNamespace:
    return SimpleNamespace(keysym=keysym, char=char, state=state)


def _key_app() -> App:
    """Create only the state used by the calculator-key contracts below."""
    app = object.__new__(App)
    app.shift = False
    app.alpha = False
    app.template_kind = None
    app._lcd_flow = None
    app.overwrite = False
    app.undo = []
    app.expr = _Entry("abcd", 2)
    app._history_lcd_active = mock.Mock(return_value=False)
    app._lcd_move = mock.Mock(return_value=False)
    app._lcd_vertical_move = mock.Mock(return_value=False)
    app._lcd_prepare_direct_entry = mock.Mock()
    app.remember = mock.Mock()
    app.consume = mock.Mock()
    app.template_insert = mock.Mock()
    app.template_backspace = mock.Mock()
    app.set_expr = mock.Mock()
    return app


def test_modifier_and_navigation_keys_keep_history_template_lcd_and_entry_paths_distinct() -> None:
    app = _key_app()
    app.status_refresh = mock.Mock()

    App.shift_key(app)
    assert (app.shift, app.alpha) == (True, False)
    App.alpha_key(app)
    assert (app.shift, app.alpha) == (False, True)
    assert app.status_refresh.call_count == 2

    app._history_lcd_active.return_value = True
    App.move(app, 1)
    assert app.expr.operations == []
    app._lcd_move.assert_called_once_with(1)
    app._lcd_move.reset_mock()

    app._history_lcd_active.return_value = False
    app.template_kind = "integral"
    app.template_order = ["body", "lower", "upper"]
    app.template_index = 0
    app.template_fields = {"body": "abc"}
    app.template_cursors = {"body": 1}
    app.render_template = mock.Mock()
    App.move(app, -5)
    App.move(app, 99)
    assert app.template_cursors["body"] == 3
    assert app._active_template_field() == "body"
    assert app.render_template.call_count == 2

    app.template_kind = None
    app._lcd_move.return_value = True
    App.move(app, 1)
    app._lcd_move.assert_called_once_with(1)
    assert app.expr.operations == []

    app._lcd_move.return_value = False
    app.expr.cursor = 1
    App.move(app, 1)
    assert app.expr.operations == [("icursor", 2)]

    app.template_kind = None
    App.template_cursor_move(app, 1)


def test_vertical_navigation_uses_integral_and_derivative_geometry_before_history() -> None:
    app = _key_app()
    app.render_template = mock.Mock()
    app.history_move = mock.Mock()

    app.template_kind = "integral"
    app.template_order = ["body", "upper", "lower", "var"]
    app.template_index = 1
    app.template_fields = {key: "" for key in app.template_order}
    app.template_cursors = {}
    App.vertical_move(app, 1)
    assert app.template_order[app.template_index] == "lower"
    App.vertical_move(app, 1)
    assert app.template_order[app.template_index] == "var"
    App.vertical_move(app, -1)
    assert app.template_order[app.template_index] == "lower"

    app.template_kind = "derivative"
    app.template_order = ["body", "point"]
    app.template_index = 0
    app.template_fields = {key: "" for key in app.template_order}
    app.template_cursors = {}
    App.vertical_move(app, 1)
    assert app.template_order[app.template_index] == "point"
    App.vertical_move(app, -1)
    assert app.template_order[app.template_index] == "body"

    app.template_kind = "multiple_integral"
    app.template_order = ["body", "inner_lower", "inner_upper"]
    app.template_fields = {"body": "x*y", "inner_lower": "0", "inner_upper": "1"}
    app.template_cursors = {}
    app.template_index = 0
    App.vertical_move(app, 1)
    assert app.template_order[app.template_index] == "inner_lower"

    app.template_kind = None
    App.vertical_move(app, -1)
    app.history_move.assert_not_called()


def test_template_keyboard_routes_editing_commands_without_using_hidden_input_paths() -> None:
    app = _key_app()
    app.template_kind = "integral"
    app.move = mock.Mock()
    app.vertical_move = mock.Mock()
    app.equals = mock.Mock()
    app.cancel_template = mock.Mock()
    app.template_move = mock.Mock()
    app._keyboard_character_token = mock.Mock(return_value="x")

    assert App._template_keypress(app, _event(keysym="Left")) == "break"
    app.move.assert_called_once_with(-1)
    assert App._template_keypress(app, _event(keysym="Down")) == "break"
    app.vertical_move.assert_called_once_with(1)
    assert App._template_keypress(app, _event(keysym="BackSpace")) == "break"
    app.template_backspace.assert_called_once_with(delete_forward=False)
    assert App._template_keypress(app, _event(keysym="Delete")) == "break"
    app.template_backspace.assert_called_with(delete_forward=True)
    assert App._template_keypress(app, _event(keysym="Return")) == "break"
    app.equals.assert_called_once_with()
    assert App._template_keypress(app, _event(keysym="Escape")) == "break"
    app.cancel_template.assert_called_once_with()
    app.set_expr.assert_called_once_with("")
    assert App._template_keypress(app, _event(keysym="Tab", state=1)) == "break"
    app.template_move.assert_called_once_with(-1)
    assert App._template_keypress(app, _event(char="x")) == "break"
    app.template_insert.assert_called_once_with("x")
    assert App._template_keypress(app, _event(char="x", state=0x4)) == "break"
    assert app.template_insert.call_count == 1


def test_insert_and_delete_keys_preserve_flow_template_overwrite_and_undo_rules() -> None:
    history = _key_app()
    history._history_lcd_active.return_value = True
    App.insert(history, "9")
    history.consume.assert_called_once_with()
    assert history.expr.text == "abcd"

    template = _key_app()
    template.template_kind = "integral"
    App.insert(template, "9")
    template.template_insert.assert_called_once_with("9")
    template.consume.assert_called_once_with()

    normal = _key_app()
    normal.overwrite = True
    normal._lcd_flow = {"phase": "sheet", "sheet_phase": "browse", "editing": False}
    App.insert(normal, "Z")
    assert normal._lcd_flow["editing"] is True
    assert normal.expr.text == "abZd"
    normal._lcd_prepare_direct_entry.assert_called_once_with()
    normal.remember.assert_called_once_with()
    normal.consume.assert_called_once_with()

    template_delete = _key_app()
    template_delete.template_kind = "derivative"
    App.del_key(template_delete)
    template_delete.template_backspace.assert_called_once_with(delete_forward=False)
    template_delete.consume.assert_called_once_with()

    overwrite = _key_app()
    overwrite.shift = True
    App.del_key(overwrite)
    assert overwrite.overwrite is True
    overwrite.consume.assert_called_once_with()

    undo = _key_app()
    undo.alpha = True
    undo.undo = ["prior"]
    App.del_key(undo)
    assert undo.undo == ["abcd"]
    undo.set_expr.assert_called_once_with("prior")
    undo.consume.assert_called_once_with()

    delete = _key_app()
    delete._lcd_flow = {"phase": "sheet", "sheet_phase": "browse", "editing": False}
    App.del_key(delete)
    assert delete._lcd_flow["editing"] is True
    assert delete.expr.text == "acd"
    delete.remember.assert_called_once_with()


def test_derivative_template_and_template_execution_keep_symbolic_and_point_routes_separate() -> None:
    starter = _key_app()
    starter.expr = _Entry("sin(x)")
    starter._reset_lcd_flow = mock.Mock()
    starter.render_template = mock.Mock()
    starter.result = _Result()

    App.start_derivative_template(starter)

    assert starter.template_kind == "derivative"
    assert starter.template_fields == {"body": "sin(x)", "var": "x", "point": ""}
    assert starter.template_order == ["body", "var", "point"]
    assert starter.result.text == ""

    symbolic = object.__new__(App)
    symbolic.template_kind = "integral"
    symbolic.template_fields = {"body": "x^2", "var": "x", "lower": "", "upper": ""}
    symbolic.template_cursors = {"body": 3}
    symbolic._run_background_calculation = mock.Mock()
    App.evaluate_template(symbolic)
    assert symbolic._run_background_calculation.call_args.args[:2] == ("symbolic_integral", ("x^2", "x"))

    point = object.__new__(App)
    point.template_kind = "derivative"
    point.template_fields = {"body": "x^3", "var": "x", "point": "2"}
    point._run_background_calculation = mock.Mock()
    point.cancel_template = mock.Mock()
    point._calculation_busy = False
    App.evaluate_template(point)
    assert point._run_background_calculation.call_args.args[:2] == ("derivative", ("x^3", "2", "x"))
    point.cancel_template.assert_called_once_with()

    invalid = object.__new__(App)
    invalid.template_kind = "integral"
    invalid.template_fields = {"body": "x", "var": "x", "lower": "0", "upper": ""}
    invalid.template_cursors = {"body": 1}
    with pytest.raises(CalculatorError, match="Enter both lower"):
        App.evaluate_template(invalid)


def test_structured_history_recall_restores_calculus_fields_without_parsing_display_text() -> None:
    app = object.__new__(App)
    app.template_fields = {}
    app.template_cursors = {}
    app._show_completed_result = mock.Mock()

    def start_integral(body=""):
        app.template_fields = {"body": body, "var": "", "lower": "", "upper": ""}

    def start_derivative(_body=""):
        app.template_fields = {"body": "", "var": "", "point": ""}

    def start_multiple(order):
        app.template_fields = {"body": "", "order": order}
        for name in (["outer", "inner"] if order == "double" else ["outer", "middle", "inner"]):
            app.template_fields.update({f"{name}_var": "", f"{name}_lower": "", f"{name}_upper": ""})

    app.start_integral_template = start_integral
    app.start_derivative_template = start_derivative
    app.start_multiple_integral_template = start_multiple
    app.start_ode_template = mock.Mock()
    app.set_expr = mock.Mock()
    assert App._recall_structured_history(app, CalculationHistoryEntry(
        "ignored", "π", "integral_single",
        {"integrand": "sin(x)", "variables": ["x"], "bounds": [{"lower": "0", "upper": "pi"}]},
    ))
    assert app.template_fields == {"body": "sin(x)", "var": "x", "lower": "0", "upper": "pi"}

    assert App._recall_structured_history(app, CalculationHistoryEntry(
        "ignored", "12", "derivative", {"expression": "x^3", "variable": "x", "evaluation_point": "2"},
    ))
    assert app.template_fields["point"] == "2"

    assert App._recall_structured_history(app, CalculationHistoryEntry(
        "ignored", "1", "integral_triple",
        {"integrand": "x+y+z", "bounds": [
            {"variable": "x", "lower": "0", "upper": "1"},
            {"variable": "y", "lower": "0", "upper": "x"},
            {"variable": "z", "lower": "0", "upper": "y"},
        ]},
    ))
    assert app.template_fields["middle_upper"] == "x"
    assert App._recall_structured_history(app, CalculationHistoryEntry("ignored", "0", "integral_double", {"integrand": "x", "bounds": None}))
    assert App._recall_structured_history(app, CalculationHistoryEntry("ignored", "0", "integral_double", {"integrand": "x", "bounds": [None]}))
    assert App._recall_structured_history(app, CalculationHistoryEntry(
        "ignored", "y=x", "ode",
        {"equation": "dy/dx=1", "dependent_function": "y", "independent_variable": "x", "initial_conditions": "x0=0,y0=0"},
    ))
    app.start_ode_template.assert_called_once_with("dy/dx=1", "y", "x", "x0=0,y0=0")

    assert App._recall_structured_history(app, CalculationHistoryEntry(
        "ignored", "2", "complex_calculus", {"operation": "integral", "integrand": "z", "variable": "z", "lower": "0", "upper": "1"},
    ))
    assert app.template_fields["upper"] == "1"
    assert App._recall_structured_history(app, CalculationHistoryEntry(
        "ignored", "1", "complex_calculus", {"operation": "derivative", "expression": "z^2", "variable": "z", "point": None},
    ))
    assert app.template_fields["point"] == ""
    assert App._recall_structured_history(app, CalculationHistoryEntry(
        "ignored", "1+i", "complex_calculus", {"operation": "evaluate", "expression": "1+i"},
    ))
    app.set_expr.assert_called_once_with("1+i")

    assert App._recall_structured_history(app, CalculationHistoryEntry(
        "ignored", "0", "integral_indefinite", {"integrand": "x", "variables": [] , "bounds": None},
    ))
    assert App._recall_structured_history(app, CalculationHistoryEntry("x", "1")) is False

    app._history_entries = lambda: [CalculationHistoryEntry("ignored", "0", "derivative", {"expression": "x", "variable": "x", "evaluation_point": None})]
    app.history_pos = 1
    App.history_move(app, -1)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (CalculationResult(ResultStatus.INTEGRAL_EXISTS, 3, metadata={"kind": "proper"}), "∫=3\nDefinite integral"),
        (CalculationResult(ResultStatus.INTEGRAL_EXISTS, 3, metadata={"kind": "improper"}), "Improper integral • Convergent"),
        (CalculationResult(ResultStatus.INTEGRAL_DIVERGES), "DIVERGES"),
        (CalculationResult(ResultStatus.INTEGRAL_UNDEFINED), "UNDEFINED"),
        (CalculationResult(ResultStatus.INTEGRAL_UNDETERMINED), "UNDETERMINED"),
    ],
)
def test_real_integral_template_renders_typed_semantics(result, expected) -> None:
    app = object.__new__(App)
    app.template_kind = "integral"
    app.template_fields = {"body": "x", "var": "x", "lower": "0", "upper": "1"}
    app.template_cursors = {"body": 1}
    app.mode = "Calculate"
    app.core = SimpleNamespace(format_result=lambda value, _approx=False: str(value))
    app._show_completed_result = mock.Mock()
    app.cancel_template = mock.Mock()

    def run(_operation, _args, callback):
        callback(result)

    app._run_background_calculation = run
    App.evaluate_template(app)
    assert expected in app._show_completed_result.call_args.args[0]
    app.cancel_template.assert_called_once_with()


def test_real_integral_template_displays_exact_values_as_decimals() -> None:
    app = object.__new__(App)
    app.template_kind = "integral"
    app.template_fields = {"body": "sin(x)/x", "var": "x", "lower": "-inf", "upper": "inf"}
    app.template_cursors = {"body": 8}
    app.mode = "Calculate"
    app.core = SimpleNamespace(format_result=lambda _value, approximate=False: "3.14159265359" if approximate else "pi")
    app._show_completed_result = mock.Mock()
    app.cancel_template = mock.Mock()
    app._run_background_calculation = lambda _operation, _args, callback: callback(
        CalculationResult(ResultStatus.INTEGRAL_EXISTS, metadata={"kind": "improper"}, exact_value=3.14159265359, value=3.14159265359)
    )

    App.evaluate_template(app)

    assert app._show_completed_result.call_args.args[0].startswith("∫=3.14159265359")


def test_structured_ode_template_validates_and_dispatches_full_ode_payload() -> None:
    app = object.__new__(App)
    app.template_kind = "ode_details"
    app.template_fields = {"equation": "dy/dx=y", "dependent_variable": "y", "independent_variable": "x", "initial_conditions": "x0=0,y0=1"}
    app.core = SimpleNamespace(format_result=str)
    app._run_background_calculation = mock.Mock()
    App.evaluate_template(app)
    assert app._run_background_calculation.call_args.args[:2] == ("solve_ode", ("dy/dx=y", "y", "x", "x0=0,y0=1"))

    app.template_fields["equation"] = ""
    with pytest.raises(CalculatorError, match="Differential equation is empty"):
        App.evaluate_template(app)
    app.template_fields.update({"equation": "dy/dx=y", "dependent_variable": "yy"})
    with pytest.raises(CalculatorError, match="one-letter"):
        App.evaluate_template(app)


def test_template_errors_preserve_the_entered_math_for_correction() -> None:
    app = object.__new__(App)
    app.template_kind = "integral"
    app._clear_active_input_for_error = mock.Mock()
    app._clear_modifiers = mock.Mock()
    app._show_template_error = mock.Mock()

    App.err(app, CalculatorError("Syntax ERROR: bad input"))

    app._clear_active_input_for_error.assert_not_called()
    app._show_template_error.assert_called_once_with("Syntax ERROR: bad input")


def test_equals_handles_busy_history_lcd_approx_template_errors_and_blank_input() -> None:
    busy = object.__new__(App)
    busy._calculation_busy = True
    App.equals(busy)

    history = _key_app()
    history._calculation_busy = False
    history._history_lcd_active.return_value = True
    App.equals(history)
    history.consume.assert_called_once_with()

    lcd = _key_app()
    lcd._calculation_busy = False
    lcd._lcd_flow_active = mock.Mock(return_value=True)
    lcd.shift = True
    lcd.status_refresh = mock.Mock()
    lcd._lcd_submit = mock.Mock()
    App.equals(lcd)
    assert lcd.shift is False
    lcd.status_refresh.assert_called_once_with()
    lcd._lcd_submit.assert_called_once_with()
    lcd.consume.assert_called_once_with()

    approx = _key_app()
    approx._calculation_busy = False
    approx._lcd_flow_active = mock.Mock(return_value=False)
    approx.shift = True
    approx.status_refresh = mock.Mock()
    approx.approx = mock.Mock()
    App.equals(approx)
    approx.approx.assert_called_once_with()
    approx.consume.assert_not_called()

    template = _key_app()
    template._calculation_busy = False
    template._lcd_flow_active = mock.Mock(return_value=False)
    template.template_kind = "derivative"
    template.evaluate_template = mock.Mock(side_effect=CalculatorError("Math ERROR: bad derivative"))
    template.err = mock.Mock()
    App.equals(template)
    template.err.assert_called_once()
    template.consume.assert_called_once_with()

    blank = _key_app()
    blank._calculation_busy = False
    blank._lcd_flow_active = mock.Mock(return_value=False)
    blank.expr = _Entry("  ")
    blank.mode = "Calculate"
    blank._run_background_calculation = mock.Mock()
    App.equals(blank)
    blank._run_background_calculation.assert_not_called()
    blank.consume.assert_not_called()


def test_menu_and_mode_selection_reset_state_open_setup_and_start_lcd_workspaces() -> None:
    history = _key_app()
    history._history_lcd_active.return_value = True
    history.setup_dialog = mock.Mock()
    with mock.patch.object(app_module.tk, "Menu") as menu:
        App.menu_key(history)
    menu.assert_not_called()
    history.consume.assert_called_once_with()

    setup = _key_app()
    setup.shift = True
    setup.setup_dialog = mock.Mock()
    with mock.patch.object(app_module.tk, "Menu") as menu:
        App.menu_key(setup)
    menu.assert_not_called()
    setup.consume.assert_called_once_with()
    setup.setup_dialog.assert_called_once_with()

    dialog = mock.Mock()
    change = object.__new__(App)
    change.mode = "Calculate"
    change._lcd_flow = {"mode": "old"}
    change.cancel_template = mock.Mock()
    change.consume = mock.Mock()
    change.status_refresh = mock.Mock()
    change.result = _Result()
    change.MODE_HINTS = App.MODE_HINTS
    change._start_lcd_flow = mock.Mock()
    App.select_mode(change, "Matrix", dialog)
    assert change.mode == "Matrix"
    assert change._lcd_flow is None
    change.cancel_template.assert_called_once_with()
    change._start_lcd_flow.assert_called_once_with("Matrix")
    dialog.destroy.assert_called_once_with()
    assert change.result.text == App.MODE_HINTS["Matrix"]

    same = object.__new__(App)
    same.mode = "Matrix"
    same._lcd_flow = {"mode": "Matrix"}
    same.cancel_template = mock.Mock()
    same.consume = mock.Mock()
    same.status_refresh = mock.Mock()
    same.result = _Result()
    same.MODE_HINTS = App.MODE_HINTS
    same._start_lcd_flow = mock.Mock()
    App.select_mode(same, "Matrix")
    assert same._lcd_flow is None
    same.cancel_template.assert_called_once_with()
    same._start_lcd_flow.assert_called_once_with("Matrix")

    blank = object.__new__(App)
    blank._lcd_flow = {"mode": "old"}
    blank.cancel_template = mock.Mock()
    blank.consume = mock.Mock()
    assert App._clear_before_interaction_transition(blank) == ""
    assert blank.history_pos == 0
    blank.cancel_template.assert_called_once_with()
    blank.consume.assert_called_once_with()


def test_option_key_uses_visible_mode_specific_commands_and_never_bypasses_lcd_flow() -> None:
    lcd = _key_app()
    lcd._lcd_flow_active = mock.Mock(return_value=True)
    lcd._lcd_options = mock.Mock()
    App.optn_key(lcd)
    lcd._lcd_options.assert_called_once_with()
    lcd.consume.assert_called_once_with()

    _Menu.instances.clear()
    calculate = _key_app()
    calculate.mode = "Calculate"
    calculate._lcd_flow_active = mock.Mock(return_value=False)
    calculate._insert_function_token = mock.Mock()
    calculate.core = SimpleNamespace(settings=SimpleNamespace(angle_unit="RAD"))
    calculate.status_refresh = mock.Mock()
    calculate.winfo_pointerx = mock.Mock(return_value=10)
    calculate.winfo_pointery = mock.Mock(return_value=20)
    with mock.patch.object(app_module.tk, "Menu", _Menu):
        App.optn_key(calculate)
    root, hyperbolic, angle, engineering = _Menu.instances
    assert root.popup_calls == [(10, 20)]
    assert root.released is True
    hyperbolic.commands["sinh"]()
    calculate._insert_function_token.assert_called_once_with("sinh(")
    angle.commands["° Degree"]()
    assert calculate.core.settings.angle_unit == "DEG"
    assert len(engineering.commands) == 11

    _Menu.instances.clear()
    complex_app = _key_app()
    complex_app.mode = "Complex"
    complex_app._lcd_flow_active = mock.Mock(return_value=False)
    complex_app.insert = mock.Mock()
    complex_app._start_lcd_flow = mock.Mock()
    complex_app.complex_to_polar = mock.Mock()
    complex_app.complex_from_polar = mock.Mock()
    complex_app.winfo_pointerx = mock.Mock(return_value=0)
    complex_app.winfo_pointery = mock.Mock(return_value=0)
    with mock.patch.object(app_module.tk, "Menu", _Menu):
        App.optn_key(complex_app)
    complex_menu = _Menu.instances[0]
    complex_menu.commands["Conj"]()
    complex_menu.commands["Calculus"]()
    complex_menu.commands["Rect→Polar"]()
    assert complex_app.insert.call_args.args == ("conjugate(",)
    complex_app._start_lcd_flow.assert_called_once_with("Complex Integral")
    complex_app.complex_to_polar.assert_called_once_with()
