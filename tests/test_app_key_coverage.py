from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from scientific_calculator import app as app_module
from scientific_calculator.app import App
from scientific_calculator.calculator_engine import CalculatorError


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

    app._history_lcd_active.return_value = False
    app.template_kind = "integral"
    app.template_order = ["body"]
    app.template_index = 0
    app.template_fields = {"body": "abc"}
    app.template_cursors = {"body": 1}
    app.render_template = mock.Mock()
    App.move(app, -5)
    App.move(app, 99)
    assert app.template_cursors["body"] == 3
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


def test_vertical_navigation_uses_integral_and_derivative_geometry_before_history() -> None:
    app = _key_app()
    app.render_template = mock.Mock()
    app.history_move = mock.Mock()

    app.template_kind = "integral"
    app.template_order = ["body", "upper", "lower", "var"]
    app.template_index = 1
    App.vertical_move(app, 1)
    assert app.template_order[app.template_index] == "body"
    App.vertical_move(app, 1)
    assert app.template_order[app.template_index] == "lower"
    App.vertical_move(app, -1)
    assert app.template_order[app.template_index] == "body"

    app.template_kind = "derivative"
    app.template_order = ["body", "point"]
    app.template_index = 0
    App.vertical_move(app, 1)
    assert app.template_order[app.template_index] == "point"
    App.vertical_move(app, -1)
    assert app.template_order[app.template_index] == "body"

    app.template_kind = None
    App.vertical_move(app, -1)
    app.history_move.assert_called_once_with(-1)


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
    assert starter.template_order == ["body", "point"]
    assert starter.result.text.startswith("d/dx")

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
    same.cancel_template.assert_not_called()
    same._start_lcd_flow.assert_called_once_with("Matrix")


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
    root, hyperbolic, angle = _Menu.instances
    assert root.popup_calls == [(10, 20)]
    assert root.released is True
    hyperbolic.commands["sinh"]()
    calculate._insert_function_token.assert_called_once_with("sinh(")
    angle.commands["° Degree"]()
    assert calculate.core.settings.angle_unit == "DEG"

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
    complex_menu.commands["Conjugate"]()
    complex_menu.commands["Complex Calculus"]()
    complex_menu.commands["→r∠θ"]()
    assert complex_app.insert.call_args.args == ("conjugate(",)
    complex_app._start_lcd_flow.assert_called_once_with("Complex Integral")
    complex_app.complex_to_polar.assert_called_once_with()
