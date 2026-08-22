"""Focused behavioural coverage for the remaining LCD application branches.

These tests exercise actual choices that are available from the calculator's
LCD menus.  They deliberately use small collaborators instead of a Tk window:
the behaviour under test is the routing/validation contract, not Tk itself.
"""

from __future__ import annotations

import math
import runpy
import sys
import warnings
from types import SimpleNamespace
from unittest import mock

import pytest
import sympy as sp

from scientific_calculator import app as app_module
from scientific_calculator import calculator_engine as calculator_engine_module
from scientific_calculator.app import App
from scientific_calculator.calculator_engine import CalculatorError


class _Result:
    def __init__(self) -> None:
        self.text = ""

    def config(self, **options: object) -> None:
        if "text" in options:
            self.text = str(options["text"])


class _Entry:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def get(self) -> str:
        return self.text


class _FocusEntry(_Entry):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.focused = False

    def focus_set(self) -> None:
        self.focused = True


class _Menu:
    instances: list[_Menu] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.commands: dict[str, object] = {}
        self.released = False
        self.__class__.instances.append(self)

    def add_command(self, *, label: str, command: object) -> None:
        self.commands[label] = command

    def add_separator(self) -> None:
        pass

    def tk_popup(self, *_args: object) -> None:
        pass

    def grab_release(self) -> None:
        self.released = True


def _lcd_app() -> App:
    """Build the non-visual state shared by LCD flow contract tests."""
    app = object.__new__(App)
    app._lcd_flow = {}
    app._lcd_begin_form = mock.Mock()
    app._lcd_show_results = mock.Mock()
    app._run_background_calculation = mock.Mock()
    app._reset_lcd_flow = mock.Mock()
    app._lcd_sheet_return = mock.Mock()
    app._lcd_sheet_address = mock.Mock(return_value="A1")
    app._lcd_render_sheet = mock.Mock()
    app._set_lcd_expression = mock.Mock()
    app._lcd_clip = lambda text, _limit=28: str(text)
    app.set_expr = mock.Mock()
    app.start_integral_template = mock.Mock()
    app.result = _Result()
    app.expr = _Entry()
    app.history_pos = 0
    app.core = SimpleNamespace(
        history=[("1+1", "2")],
        format_result=mock.Mock(return_value="formatted"),
        settings=SimpleNamespace(statistics_freq=False),
        matrices={},
        vectors={},
        mat_ans=None,
        vct_ans=None,
        memory={},
    )
    return app


@pytest.mark.parametrize(
    ("mode", "action", "expected_keys"),
    [
        ("Integral", "Indefinite Integral", {"calculus_expression", "calculus_variable"}),
        ("Complex Integral", "Complex Indefinite Integral", {"calculus_expression", "calculus_variable"}),
        ("Integral", "Indefinite Derivative", {"calculus_expression", "calculus_variable"}),
        (
            "Integral",
            "Double Integral",
            {"calculus_expression", "outer_variable", "inner_variable", "outer_lower", "outer_upper", "inner_lower", "inner_upper"},
        ),
        (
            "Integral",
            "Triple Integral",
            {"calculus_expression", "outer_variable", "middle_variable", "inner_variable", "outer_lower", "outer_upper", "middle_lower", "middle_upper", "inner_lower", "inner_upper"},
        ),
        (
            "Complex Integral",
            "Complex Double Integral",
            {"calculus_expression", "outer_variable", "inner_variable", "outer_lower", "outer_upper", "inner_lower", "inner_upper"},
        ),
        (
            "Integral",
            "Line Integral (f ds)",
            {"calculus_expression", "path_x", "path_y", "parameter", "path_lower", "path_upper"},
        ),
        (
            "Integral",
            "Line Integral (P dx + Q dy)",
            {"component_x", "component_y", "path_x", "path_y", "parameter", "path_lower", "path_upper"},
        ),
        (
            "Integral",
            "Surface Integral (f dS)",
            {"calculus_expression", "surface_x", "surface_y", "surface_z", "outer_variable", "inner_variable", "outer_lower", "outer_upper", "inner_lower", "inner_upper"},
        ),
        (
            "Integral",
            "Surface Flux Integral",
            {"component_x", "component_y", "component_z", "surface_x", "surface_y", "surface_z", "outer_variable", "inner_variable", "outer_lower", "outer_upper", "inner_lower", "inner_upper", "flux_orientation"},
        ),
        (
            "Complex Integral",
            "Contour Integral",
            {"calculus_expression", "contour_path", "complex_variable", "parameter", "path_lower", "path_upper"},
        ),
    ],
)
def test_lcd_calculus_menu_exposes_the_fields_required_by_every_supported_operation(
    mode: str, action: str, expected_keys: set[str]
) -> None:
    app = _lcd_app()
    app._lcd_flow = {
        "mode": mode,
        "source_expression": "",
        "values": {"calculus_action": action},
    }

    App._lcd_choose_calculus_action(app)

    title, fields, stage = app._lcd_begin_form.call_args.args
    assert title == ("CPLX INT" if mode == "Complex Integral" else "INTEGRAL")
    assert stage == "calculus_run"
    assert {field["key"] for field in fields} == expected_keys


def test_lcd_definite_integral_choices_open_the_editable_template_and_invalid_choice_is_rejected() -> None:
    app = _lcd_app()
    app._lcd_flow = {
        "mode": "Complex Integral",
        "source_expression": "sqrt(ln(x))",
        "values": {"calculus_action": "Complex Definite Integral"},
    }

    App._lcd_choose_calculus_action(app)

    app._reset_lcd_flow.assert_called_once_with()
    app.set_expr.assert_called_once_with("sqrt(ln(x))")
    app.start_integral_template.assert_called_once_with()

    app._lcd_flow = {"mode": "Integral", "values": {"calculus_action": "not a calculus action"}}
    with pytest.raises(CalculatorError, match="unsupported calculus operation"):
        App._lcd_choose_calculus_action(app)


@pytest.mark.parametrize(
    ("action", "values", "expected_method", "expected_args", "prefix", "has_constant"),
    [
        (
            "Indefinite Integral",
            {"calculus_expression": "x^2", "calculus_variable": "x"},
            "symbolic_integral",
            ("x^2", "x"),
            "∫ dx",
            True,
        ),
        (
            "Complex Indefinite Integral",
            {"calculus_expression": "z^2", "calculus_variable": "z"},
            "symbolic_integral",
            ("z^2", "z"),
            "∫ dz",
            True,
        ),
        (
            "Indefinite Derivative",
            {"calculus_expression": "x^3", "calculus_variable": "x"},
            "symbolic_derivative",
            ("x^3", "x"),
            "d/dx",
            False,
        ),
        (
            "Double Integral",
            {"calculus_expression": "x+y", "outer_lower": "0", "outer_upper": "1", "inner_lower": "0", "inner_upper": "1", "outer_variable": "x", "inner_variable": "y"},
            "double_integral",
            ("x+y", "0", "1", "0", "1", "x", "y"),
            "∫∫",
            False,
        ),
        (
            "Complex Double Integral",
            {"calculus_expression": "i*x+y", "outer_lower": "0", "outer_upper": "1", "inner_lower": "0", "inner_upper": "1", "outer_variable": "x", "inner_variable": "y"},
            "complex_double_integral",
            ("i*x+y", "0", "1", "0", "1", "x", "y"),
            "∫∫",
            False,
        ),
        (
            "Triple Integral",
            {"calculus_expression": "x+y+z", "outer_lower": "0", "outer_upper": "1", "middle_lower": "0", "middle_upper": "1", "inner_lower": "0", "inner_upper": "1", "outer_variable": "x", "middle_variable": "y", "inner_variable": "z"},
            "triple_integral",
            ("x+y+z", "0", "1", "0", "1", "0", "1", "x", "y", "z"),
            "∫∫∫",
            False,
        ),
        (
            "Line Integral (f ds)",
            {"calculus_expression": "x+y", "path_x": "t", "path_y": "t^2", "path_lower": "0", "path_upper": "1", "parameter": "t"},
            "line_integral",
            ("x+y", "t", "t^2", "0", "1", "t"),
            "∫C",
            False,
        ),
        (
            "Line Integral (P dx + Q dy)",
            {"component_x": "y", "component_y": "x", "path_x": "t", "path_y": "t^2", "path_lower": "0", "path_upper": "1", "parameter": "t"},
            "vector_line_integral",
            ("y", "x", "t", "t^2", "0", "1", "t"),
            "∫C",
            False,
        ),
        (
            "Surface Integral (f dS)",
            {"calculus_expression": "1", "surface_x": "u", "surface_y": "v", "surface_z": "0", "outer_lower": "0", "outer_upper": "1", "inner_lower": "0", "inner_upper": "1", "outer_variable": "u", "inner_variable": "v"},
            "surface_integral",
            ("1", "u", "v", "0", "0", "1", "0", "1", "u", "v"),
            "∫∫S",
            False,
        ),
        (
            "Surface Flux Integral",
            {"component_x": "0", "component_y": "0", "component_z": "1", "surface_x": "u", "surface_y": "v", "surface_z": "0", "outer_lower": "0", "outer_upper": "1", "inner_lower": "0", "inner_upper": "1", "outer_variable": "u", "inner_variable": "v", "flux_orientation": "reverse"},
            "surface_flux_integral",
            ("0", "0", "1", "u", "v", "0", "0", "1", "0", "1", "u", "v", True),
            "Φ",
            False,
        ),
        (
            "Contour Integral",
            {"calculus_expression": "1/z", "contour_path": "exp(i*t)", "path_lower": "0", "path_upper": "2*pi", "complex_variable": "z", "parameter": "t"},
            "contour_integral",
            ("1/z", "exp(i*t)", "0", "2*pi", "z", "t"),
            "∫γ",
            False,
        ),
    ],
)
def test_lcd_calculus_execution_routes_each_menu_operation_to_its_engine_contract(
    action: str,
    values: dict[str, object],
    expected_method: str,
    expected_args: tuple[object, ...],
    prefix: str,
    has_constant: bool,
) -> None:
    app = _lcd_app()
    app._lcd_flow = {"values": {"calculus_action": action, **values}}

    App._lcd_run_calculus_operation(app)

    method, args, success = app._run_background_calculation.call_args.args
    assert (method, args) == (expected_method, expected_args)
    success(sp.Symbol("answer"))
    title, lines = app._lcd_show_results.call_args.args
    assert prefix in lines[0]
    assert (" + C" in lines[0]) is has_constant
    assert title in {"INTEGRAL", "CPLX INT", "DERIVATIVE", "LINE", "SURFACE", "FLUX"}


def test_lcd_calculus_execution_rejects_an_unknown_operation() -> None:
    app = _lcd_app()
    app._lcd_flow = {"values": {"calculus_action": "not a calculus action"}}

    with pytest.raises(CalculatorError, match="unsupported calculus operation"):
        App._lcd_run_calculus_operation(app)


def test_lcd_validation_reports_malformed_numeric_and_function_fields_as_calculator_errors() -> None:
    app = _lcd_app()
    app.core.parse = mock.Mock(side_effect=ValueError("bad number"))
    with pytest.raises(CalculatorError, match="Argument ERROR: bound"):
        App._lcd_real(app, "not-a-number", "bound")

    with pytest.raises(CalculatorError, match="Argument ERROR: result"):
        App._lcd_real_expression(object(), "result")

    app.core.parse = mock.Mock(side_effect=CalculatorError("Syntax ERROR: parser"))
    with pytest.raises(CalculatorError, match="Syntax ERROR: parser"):
        App._lcd_function(app, "bad", "function")

    app.core.parse = mock.Mock(side_effect=ValueError("bad function"))
    with pytest.raises(CalculatorError, match="Syntax ERROR: function"):
        App._lcd_function(app, "bad", "function")


def test_lcd_workspace_validation_covers_unconfigured_copy_statistics_and_ratio_error_paths() -> None:
    app = _lcd_app()
    app._lcd_flow = {"stage": "missing-handler"}
    with pytest.raises(CalculatorError, match="unsupported LCD workflow"):
        App._lcd_complete_flow(app)

    app._lcd_flow = {"values": {"matrix_source": "MatA", "matrix_destination": "MatB"}}
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        App._lcd_run_matrix_copy(app)

    app._lcd_flow = {"values": {"vector_source": "VctA", "vector_destination": "VctB"}}
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        App._lcd_run_vector_copy(app)

    app.core.settings.statistics_freq = True
    app._lcd_flow = {"values": {"analysis": "1-Variable"}}
    App._lcd_choose_statistics_action(app)
    fields = app._lcd_begin_form.call_args.args[1]
    assert [field["key"] for field in fields] == ["stat_x", "stat_frequency"]

    app._lcd_begin_form.reset_mock()
    app._lcd_flow = {"values": {"analysis": "x→t"}}
    App._lcd_choose_statistics_action(app)
    fields = app._lcd_begin_form.call_args.args[1]
    assert [field["key"] for field in fields] == ["stat_x", "stat_frequency", "stat_target"]

    app.core.one_var_stats = mock.Mock(return_value={"x̄": 2.0, "σx": 0.0})
    app._lcd_flow = {"values": {"analysis": "x→t", "stat_x": [2.0], "stat_target": 3.0}}
    with pytest.raises(CalculatorError, match="standard deviation is zero"):
        App._lcd_run_statistics(app)

    app.core.ratio = mock.Mock(return_value=math.inf)
    app._lcd_flow = {"values": {"ratio_kind": "A:B = X:D", "ratio_A": 1.0, "ratio_B": 2.0, "ratio_D": 3.0}}
    with pytest.raises(CalculatorError, match="ratio result must be finite"):
        App._lcd_run_ratio(app)


def test_lcd_ode_supports_general_and_initial_condition_routes_and_formats_non_equality_results() -> None:
    app = _lcd_app()
    app._lcd_run_differential_equation = mock.Mock()
    app._lcd_flow = {
        "values": {
            "ode_dependent_variable": "y",
            "ode_independent_variable": "x",
            "ode_condition_mode": "General",
        }
    }
    App._lcd_expand_ode_conditions(app)
    app._lcd_run_differential_equation.assert_called_once_with()

    app._lcd_run_differential_equation.reset_mock()
    app._lcd_flow["values"]["ode_condition_mode"] = "y(x0), y'(x0)"
    App._lcd_expand_ode_conditions(app)
    _title, fields, stage = app._lcd_begin_form.call_args.args
    assert stage == "equation_ode_run"
    assert [field["key"] for field in fields] == ["ode_initial_point", "ode_initial_value", "ode_initial_derivative"]

    app._lcd_flow["values"]["ode_independent_variable"] = "y"
    with pytest.raises(CalculatorError, match="must differ"):
        App._lcd_expand_ode_conditions(app)

    app = _lcd_app()
    app._lcd_flow = {
        "values": {
            "ode_equation": "dy/dx=y",
            "ode_dependent_variable": "y",
            "ode_independent_variable": "x",
            "ode_condition_mode": "General",
        }
    }
    App._lcd_run_differential_equation(app)
    method, args, success = app._run_background_calculation.call_args.args
    assert (method, args) == ("solve_ode", ("dy/dx=y", "y", "x", None))
    success("backend text")
    assert app._lcd_show_results.call_args.args == ("DIFF EQ", ["formatted"])


@pytest.mark.parametrize(
    "tool",
    [
        "Edit cell",
        "Delete cell",
        "Copy cell",
        "Cut cell",
        "Insert reference",
        "Fill value",
        "Fill formula",
        "Recalculate",
        "Free space",
        "Delete all",
    ],
)
def test_lcd_spreadsheet_tool_choices_remain_available_without_a_popup(tool: str) -> None:
    app = _lcd_app()
    app.sheet = SimpleNamespace(
        cells={"A1": "=1"},
        delete=mock.Mock(),
        recalculate=mock.Mock(return_value=["A1", "B1"]),
        free_space=mock.Mock(return_value=42),
    )
    app._lcd_flow = {"values": {"sheet_tool": tool}}

    App._lcd_choose_sheet_tool(app)

    if tool == "Edit cell":
        assert app._lcd_flow["editing"] is True
        app._set_lcd_expression.assert_called_once_with("=1")
    elif tool == "Delete cell":
        app.sheet.delete.assert_called_once_with("A1")
        app._lcd_sheet_return.assert_called_once_with("Deleted A1")
    elif tool in {"Copy cell", "Cut cell"}:
        assert app._lcd_begin_form.call_args.args[2] == ("sheet_copy" if tool == "Copy cell" else "sheet_cut")
    elif tool == "Insert reference":
        assert app._lcd_begin_form.call_args.args[2] == "sheet_grab"
        assert app._lcd_begin_form.call_args.args[0] == "SHEET insert A1"
    elif tool in {"Fill value", "Fill formula"}:
        assert app._lcd_begin_form.call_args.args[2] == ("sheet_fill_value" if tool == "Fill value" else "sheet_fill_formula")
    elif tool == "Recalculate":
        app.sheet.recalculate.assert_called_once_with()
        app._lcd_sheet_return.assert_called_once_with("Recalculated 2 cells")
    elif tool == "Free space":
        assert app._lcd_show_results.call_args.args == ("SHEET", ["Free space = 42 bytes"])
    else:
        assert app._lcd_begin_form.call_args.args[2] == "sheet_delete_all"


def test_lcd_spreadsheet_editing_and_tool_validation_protect_the_active_cell() -> None:
    app = _lcd_app()
    app.sheet = SimpleNamespace(cells={"A1": "=1"}, set=mock.Mock(), delete_all=mock.Mock())
    app.expr = _Entry("=1")
    app._lcd_flow = {"phase": "sheet", "editing": False, "sheet_column": 0, "sheet_row": 0}

    App._lcd_submit_sheet(app)
    assert app._lcd_flow["editing"] is True
    assert app.result.text == "Edit A1  = save  AC"

    app._lcd_flow = {"values": {"sheet_target_column": "A", "sheet_target_row": 1, "sheet_reference_prefix": "="}}
    with pytest.raises(CalculatorError, match="must be different"):
        App._lcd_run_sheet_grab(app)

    app._lcd_flow = {"values": {"sheet_target_column": "B", "sheet_target_row": 1, "sheet_reference_prefix": "A+"}}
    with pytest.raises(CalculatorError, match="must start with ="):
        App._lcd_run_sheet_grab(app)

    app._lcd_flow = {"values": {"sheet_target_column": "B", "sheet_target_row": 1, "sheet_fill_text": "A1"}}
    with pytest.raises(CalculatorError, match="formula must start with ="):
        App._lcd_run_sheet_fill_formula(app)

    app._lcd_flow = {"values": {"sheet_confirm": "Cancel"}}
    App._lcd_run_sheet_delete_all(app)
    app.sheet.delete_all.assert_not_called()
    app._lcd_sheet_return.assert_called_with("Delete all cancelled")


def test_lcd_sheet_navigation_refuses_to_move_outside_the_browse_state() -> None:
    app = _lcd_app()
    app._lcd_flow = None
    assert App._lcd_move_sheet_column(app, 1) is False
    assert App._lcd_move_sheet_row(app, 1) is False

    app._lcd_flow = {"phase": "sheet", "editing": True}
    assert App._lcd_move_sheet_column(app, 1) is False
    assert App._lcd_move_sheet_row(app, 1) is True


def test_small_lcd_helpers_cover_range_validation_result_formatting_and_keyboard_edges() -> None:
    with pytest.raises(CalculatorError, match="Range ERROR"):
        App._table_row_count("start", 1, 1)

    app = _lcd_app()
    app._scale_factor = mock.Mock(return_value=1.5)
    assert App._fs(app, 10) == 15

    app.shift = True
    app.alpha = False
    app.shift_status = SimpleNamespace(config=mock.Mock(side_effect=app_module.tk.TclError("gone")))
    App._refresh_modifier_status(app)  # Teardown of a status label is harmless.

    assert App._lcd_complex_text(1 + 2j) == "1+2i"

    keyboard = _lcd_app()
    keyboard._calculation_busy = False
    keyboard.template_kind = "integral"
    assert App._physical_keypress(keyboard, SimpleNamespace(keysym="x", char="x", state=0)) is None

    keyboard.template_kind = None
    keyboard.ac_key = mock.Mock()
    keyboard.vertical_move = mock.Mock()
    assert App._physical_keypress(keyboard, SimpleNamespace(keysym="Escape", char="", state=0)) == "break"
    assert App._physical_keypress(keyboard, SimpleNamespace(keysym="Down", char="", state=0)) == "break"
    keyboard.ac_key.assert_called_once_with()
    keyboard.vertical_move.assert_called_once_with(1)

    keyboard.template_kind = "integral"
    assert App._template_keypress(keyboard, SimpleNamespace(keysym="F2", char="", state=0)) == "break"


def test_lcd_statistics_and_sheet_rendering_cover_successful_secondary_routes() -> None:
    app = _lcd_app()
    app.core.one_var_stats = mock.Mock(return_value={"x̄": 2.0, "σx": 0.5})
    app._lcd_flow = {"values": {"analysis": "x→t", "stat_x": [1.0, 3.0], "stat_target": 3.0}}
    App._lcd_run_statistics(app)
    assert app._lcd_show_results.call_args.args == ("STAT", ["t = 2"])

    app = _lcd_app()
    app.expr = _FocusEntry()
    app.sheet = SimpleNamespace(cells={"A1": "=1"})
    app._spreadsheet_display_value = mock.Mock(return_value="1")
    app._lcd_flow = None
    App._lcd_render_sheet(app)
    app._lcd_flow = {"phase": "sheet", "editing": True}
    App._lcd_render_sheet(app)
    assert app.result.text == "Edit A1  = save  AC"
    assert app.expr.focused is True


def test_error_clearing_resets_the_current_form_or_template_field_without_losing_mode_state() -> None:
    form = _lcd_app()
    form._lcd_flow = {"phase": "form", "draft": {}, "field_armed": True}
    form._lcd_current_spec = mock.Mock(return_value={"key": "outer_lower"})
    App._clear_active_input_for_error(form)
    assert form._lcd_flow["draft"]["outer_lower"] == ""
    assert form._lcd_flow["field_armed"] is False
    form.set_expr.assert_called_once_with("")

    template = _lcd_app()
    template._lcd_flow = None
    template.template_kind = "integral"
    template.template_fields = {"body": "bad"}
    template.template_cursors = {"body": 3}
    template._active_template_field = mock.Mock(return_value="body")
    template.render_template = mock.Mock()
    App._clear_active_input_for_error(template)
    assert template.template_fields["body"] == ""
    assert template.template_cursors["body"] == 0
    template.render_template.assert_called_once_with()
    template.set_expr.assert_not_called()


def test_template_editing_helpers_keep_calculus_text_and_variables_editable() -> None:
    app = _lcd_app()
    app.template_kind = "integral"
    app.template_order = ["body", "var"]
    app.template_index = 0
    app.template_fields = {"body": "x", "var": "x"}
    app.template_cursors = {"body": 1, "var": 1}
    app.render_template = mock.Mock()

    App.template_move(app, 1)
    assert app.template_index == 1
    App.template_insert(app, "z")
    assert app.template_fields["var"] == "z"
    App.template_backspace(app)
    assert app.template_fields["var"] == "x"

    app.template_index = 0
    app.template_cursors["body"] = 1
    App.template_insert(app, "+1")
    assert app.template_fields["body"] == "x+1"
    app.template_cursors["body"] = 1
    App.template_backspace(app, delete_forward=True)
    assert app.template_fields["body"] == "x1"
    assert app.render_template.call_count >= 5

    app.template_kind = None
    App.template_move(app, 1)
    App.template_insert(app, "x")
    App.template_backspace(app)


def test_derivative_template_execution_history_and_ac_reset_follow_visible_calculator_rules() -> None:
    derivative = _lcd_app()
    derivative.template_kind = "derivative"
    derivative.template_fields = {"body": "x^2", "var": "x", "point": ""}
    derivative._calculation_busy = False
    derivative.cancel_template = mock.Mock()
    App.evaluate_template(derivative)
    method, args, callback = derivative._run_background_calculation.call_args.args
    assert (method, args) == ("symbolic_derivative", ("x^2", "x"))
    callback(sp.Symbol("x"))
    derivative.cancel_template.assert_called()

    history = _lcd_app()
    history._start_lcd_flow = mock.Mock()
    history.consume = mock.Mock()
    App.show_history(history)
    history._start_lcd_flow.assert_called_once_with("History")
    history.consume.assert_called_once_with()

    reset = _lcd_app()
    reset.cancel_template = mock.Mock()
    reset._reset_lcd_flow = mock.Mock()
    reset.set_expr = mock.Mock()
    reset.consume = mock.Mock()
    reset.mode = "Matrix"
    reset._start_lcd_flow = mock.Mock()
    App._reset_active_mode_after_ac(reset)
    reset._start_lcd_flow.assert_called_once_with("Matrix")

    reset._calculation_busy = False
    reset.shift = False
    reset._lcd_flow = {"phase": "form"}
    reset._reset_active_mode_after_ac = mock.Mock()
    App.ac_key(reset)
    reset._reset_active_mode_after_ac.assert_called_once_with()


def test_integral_shortcuts_and_option_menus_reach_visible_mode_specific_actions() -> None:
    integral = _lcd_app()
    integral._history_lcd_active = mock.Mock(return_value=False)
    integral.alpha = False
    integral.shift = True
    integral.consume = mock.Mock()
    integral.start_derivative_template = mock.Mock()
    App.integral_key(integral)
    integral.start_derivative_template.assert_called_once_with()

    integral.shift = False
    integral.mode = "Matrix"
    integral.start_integral_template = mock.Mock()
    App.integral_key(integral)
    integral.start_integral_template.assert_called_once_with()

    _Menu.instances.clear()
    base = _lcd_app()
    base.mode = "Base-N"
    base.shift = False
    base._lcd_flow_active = mock.Mock(return_value=False)
    base.winfo_pointerx = mock.Mock(return_value=1)
    base.winfo_pointery = mock.Mock(return_value=2)
    base.consume = mock.Mock()
    base.base_logic_dialog = mock.Mock()
    with mock.patch.object(app_module.tk, "Menu", _Menu):
        App.optn_key(base)
    base_menu = _Menu.instances[0]
    base_menu.commands["xor"]()
    base.base_logic_dialog.assert_called_once_with("xor")

    _Menu.instances.clear()
    workspace = _lcd_app()
    workspace.mode = "Matrix"
    workspace.shift = False
    workspace._lcd_flow_active = mock.Mock(return_value=False)
    workspace.winfo_pointerx = mock.Mock(return_value=1)
    workspace.winfo_pointery = mock.Mock(return_value=2)
    workspace.consume = mock.Mock()
    workspace.mode_workspace = mock.Mock()
    with mock.patch.object(app_module.tk, "Menu", _Menu):
        App.optn_key(workspace)
    _Menu.instances[0].commands["Open Matrix workspace"]()
    workspace.mode_workspace.assert_called_once_with("Matrix")


def test_lcd_empty_state_helpers_and_settings_reset_recover_without_a_visible_widget_tree() -> None:
    app = _lcd_app()
    app._lcd_flow = None
    App._lcd_render_field(app)
    App._lcd_render_result(app)
    App._lcd_submit(app)
    assert App._lcd_keypress(app, SimpleNamespace(keysym="F1", char="")) is None

    reset = _lcd_app()
    reset._settings_store = mock.Mock(return_value=SimpleNamespace(reset_defaults=mock.Mock()))
    reset.core = SimpleNamespace(settings=SimpleNamespace(), history=None)
    reset._log_settings_issue = mock.Mock()
    reset._rebuild_scaled_ui = mock.Mock()
    reset._lcd_message = mock.Mock()
    assert App.reset_app_settings(reset) is True
    assert reset.ui_scale == 100
    assert reset.skin_name == "Graphite"
    reset._rebuild_scaled_ui.assert_called_once_with()


def test_template_canvas_helpers_support_font_fallback_and_non_skin_derivative_rendering() -> None:
    app = _lcd_app()
    with mock.patch.object(app_module.tkfont, "Font", return_value=SimpleNamespace(measure=lambda text: len(text) * 4)):
        assert App._canvas_caret_x(app, "abcd", 2, ("Consolas", 10), 5) == 13
        shown, offset = App._template_text_view(app, "abcdefghij", 9, ("Consolas", 10), 20)
    assert shown.startswith("…")
    assert offset <= 20

    with mock.patch.object(app_module.tkfont, "Font", side_effect=RuntimeError("font unavailable")):
        assert App._canvas_caret_x(app, "abcd", 3, ("Consolas", 10), 5) == 35
        shown, _offset = App._template_text_view(app, "abcdefgh", 5, ("Consolas", 10), 20)
    assert shown

    class Canvas:
        def __init__(self) -> None:
            self.rectangles: list[tuple[object, ...]] = []
            self.packs = 0
            self.mapped = False

        def pack_forget(self) -> None:
            pass

        def winfo_ismapped(self) -> bool:
            return self.mapped

        def pack(self, **_kwargs: object) -> None:
            self.packs += 1

        def delete(self, _tag: object) -> None:
            pass

        def config(self, **_kwargs: object) -> None:
            pass

        def create_text(self, *_args: object, **_kwargs: object) -> None:
            pass

        def create_rectangle(self, *args: object, **_kwargs: object) -> None:
            self.rectangles.append(args)

        def create_line(self, *_args: object, **_kwargs: object) -> None:
            pass

        def focus_set(self) -> None:
            pass

        def winfo_width(self) -> int:
            return 480

    class Expression:
        def pack_forget(self) -> None:
            pass

    render = _lcd_app()
    render.template_kind = None
    App.render_template(render)

    canvas = Canvas()
    render.template_kind = "derivative"
    render.template_fields = {"body": "x^2", "var": "x", "point": "0"}
    render.template_order = ["body", "point", "var"]
    render.template_index = 2
    render.template_cursors = {"body": 3, "var": 1, "point": 1}
    render.template_canvas = canvas
    render.expr = Expression()
    render.skin_mode = False
    render._sp = lambda value: value
    render._fp = lambda value: value
    render._draw_edit_text = mock.Mock()
    App.render_template(render)
    assert canvas.packs == 1
    assert canvas.rectangles  # Active d-variable receives a visible focus box.

    canvas.mapped = True
    App.render_template(render)
    assert canvas.packs == 1


def test_template_and_ac_paths_handle_backspace_history_and_non_workspace_mode_resets() -> None:
    app = _lcd_app()
    app.template_kind = "integral"
    app.template_order = ["body"]
    app.template_index = 0
    app.template_fields = {"body": "abc"}
    app.template_cursors = {"body": 2}
    app.render_template = mock.Mock()
    App.template_backspace(app)
    assert app.template_fields["body"] == "ac"
    assert app.template_cursors["body"] == 1

    history = _lcd_app()
    history._history_lcd_active = mock.Mock(return_value=True)
    history.consume = mock.Mock()
    App.del_key(history)
    history.consume.assert_called_once_with()

    calculate = _lcd_app()
    calculate.cancel_template = mock.Mock()
    calculate._reset_lcd_flow = mock.Mock()
    calculate.set_expr = mock.Mock()
    calculate.consume = mock.Mock()
    calculate.mode = "Calculate"
    App._reset_active_mode_after_ac(calculate)
    assert calculate.result.text == "0"

    base = _lcd_app()
    base.cancel_template = mock.Mock()
    base._reset_lcd_flow = mock.Mock()
    base.set_expr = mock.Mock()
    base.consume = mock.Mock()
    base.mode = "Base-N"
    base.MODE_HINTS = App.MODE_HINTS
    App._reset_active_mode_after_ac(base)
    assert base.result.text == "Select base, enter value, ="

    no_flow = _lcd_app()
    no_flow._calculation_busy = False
    no_flow.shift = False
    no_flow._lcd_flow = None
    no_flow._reset_active_mode_after_ac = mock.Mock()
    App.ac_key(no_flow)
    no_flow._reset_active_mode_after_ac.assert_called_once_with()


def test_startup_and_scale_rebuild_recover_when_tk_state_is_not_yet_available() -> None:
    """Startup must retain a deterministic DPI fallback and rebuild safely."""

    def load_settings(app: App) -> None:
        app.ui_scale = 100
        app.skin_name = "Graphite"
        app.saved_config = {}

    with (
        mock.patch.object(
            app_module.tk.Tk,
            "__init__",
            lambda app: setattr(app, "tk", SimpleNamespace(call=mock.Mock(side_effect=RuntimeError("no scale")))),
            create=True,
        ),
        mock.patch.object(App, "title", lambda *_args: None),
        mock.patch.object(App, "geometry", lambda *_args: None),
        mock.patch.object(App, "resizable", lambda *_args: None),
        mock.patch.object(App, "configure", lambda *_args, **_kwargs: None),
        mock.patch.object(App, "load_settings_file", load_settings),
        mock.patch.object(App, "_fit_ui_scale_to_display", lambda _app, value: value),
        mock.patch.object(App, "_sp", lambda _app, value: value),
        mock.patch.object(App, "apply_saved_engine_settings", lambda *_args: None),
        mock.patch.object(App, "load_calculation_history", lambda *_args: None),
        mock.patch.object(App, "_ui", lambda *_args: None),
        mock.patch.object(App, "status_refresh", lambda *_args: None),
        mock.patch.object(App, "protocol", lambda *_args: None),
        mock.patch.object(
            app_module,
            "ScientificCalculatorEngine",
            return_value=SimpleNamespace(history=[], settings=SimpleNamespace()),
        ),
        mock.patch.object(app_module, "SpreadsheetModel", return_value=object()),
        mock.patch.object(app_module, "CalculationController", return_value=object()),
    ):
        startup = App()
    assert startup._tk_pixels_per_point == pytest.approx(96.0 / 72.0)
    assert startup.mode == "Calculate"

    class RootChild:
        def __init__(self) -> None:
            self.destroyed = False

        def destroy(self) -> None:
            self.destroyed = True

    class AuxiliaryWindow:
        def __init__(self) -> None:
            self.destroyed = False

        def destroy(self) -> None:
            self.destroyed = True

    root_child = RootChild()
    auxiliary = AuxiliaryWindow()
    rebuild = object.__new__(App)
    rebuild.expr = SimpleNamespace(
        get=mock.Mock(side_effect=AttributeError("entry not built")),
        icursor=mock.Mock(),
    )
    rebuild.result = SimpleNamespace(config=mock.Mock())
    rebuild.template_kind = None
    rebuild.winfo_children = mock.Mock(return_value=[root_child, auxiliary])
    rebuild.resizable = mock.Mock()
    rebuild.geometry = mock.Mock()
    rebuild._sp = lambda value: value
    rebuild._ui = mock.Mock()
    rebuild.set_expr = mock.Mock()
    rebuild.status_refresh = mock.Mock()
    with mock.patch.object(app_module.tk, "Toplevel", AuxiliaryWindow):
        App._rebuild_scaled_ui(rebuild)
    assert root_child.destroyed is True
    assert auxiliary.destroyed is False
    rebuild.set_expr.assert_called_once_with("")


def test_lcd_edge_states_keep_invalid_selection_navigation_and_empty_tools_safe() -> None:
    app = _lcd_app()
    choice = {"key": "mode", "type": "choice", "choices": {1: "x"}, "default": "invalid"}
    assert App._lcd_field_text(app, {"values": {"mode": "unknown"}}, choice) == "unknown"
    assert App._lcd_field_text(app, {"values": {}}, {**choice, "default": "x"}) == "1"
    assert App._lcd_field_text(app, {"values": {}}, choice) == "invalid"

    app._lcd_flow = None
    App._lcd_capture_draft(app)

    app._lcd_flow = {"phase": "form"}
    app._lcd_current_spec = mock.Mock(return_value=None)
    App._lcd_submit(app)

    app._lcd_flow = {"phase": "results", "result_lines": []}
    assert App._lcd_vertical_move(app, 1) is True
    assert App._lcd_keypress(app, SimpleNamespace(keysym="F1", char="")) is None

    app.core.settings.statistics_freq = False
    app._lcd_flow = {"values": {"analysis": "x→t"}}
    App._lcd_choose_statistics_action(app)
    fields = app._lcd_begin_form.call_args.args[1]
    assert [field["key"] for field in fields] == ["stat_x", "stat_target"]

    app._lcd_flow = {"values": {"polynomial_degree": 3, "polynomial_0": 1, "polynomial_1": 0, "polynomial_2": 0, "polynomial_3": -1}}
    app.core.polynomial_roots = mock.Mock(return_value=[1, complex(-0.5, 0.866), complex(-0.5, -0.866)])
    App._lcd_run_polynomial(app)
    assert not any("Vertex" in line for line in app._lcd_show_results.call_args.args[1])

    app._lcd_render_sheet = mock.Mock()
    app.result = _Result()
    app._lcd_flow = {}
    App._lcd_sheet_return(app)
    app._lcd_render_sheet.assert_called_once_with()

    app.core.format_result = mock.Mock(return_value="5")
    App.show(app, 5)
    assert app.result.text == "5"


def test_template_cleanup_and_error_fallback_survive_non_skin_widget_failures() -> None:
    class Canvas:
        def __init__(self) -> None:
            self.hidden = False

        def pack_forget(self) -> None:
            self.hidden = True

    class Expression:
        def __init__(self, *, broken_selection: bool = False) -> None:
            self.packed = False
            self.selection_cleared = False
            self.broken_selection = broken_selection

        def winfo_ismapped(self) -> bool:
            return False

        def pack(self, **_kwargs: object) -> None:
            self.packed = True

        def selection_clear(self) -> None:
            if self.broken_selection:
                raise RuntimeError("widget already destroyed")
            self.selection_cleared = True

    cleanup = object.__new__(App)
    cleanup.skin_mode = False
    cleanup.template_kind = "integral"
    cleanup.template_canvas = Canvas()
    cleanup.expr = Expression()
    cleanup.result = _Result()
    App.cancel_template(cleanup)
    assert cleanup.template_kind is None
    assert cleanup.template_canvas.hidden is True
    assert cleanup.expr.packed is True
    assert cleanup.expr.selection_cleared is True

    failing_cleanup = object.__new__(App)
    failing_cleanup.skin_mode = False
    failing_cleanup.template_kind = "derivative"
    failing_cleanup.template_canvas = Canvas()
    failing_cleanup.expr = Expression(broken_selection=True)
    failing_cleanup.result = _Result()
    App.cancel_template(failing_cleanup)  # Closing an already destroyed widget is intentionally harmless.

    fallback = _lcd_app()
    fallback._lcd_flow = None
    fallback.template_kind = "integral"
    fallback.template_fields = {}
    fallback.template_cursors = {}
    fallback._active_template_field = mock.Mock(return_value="body")
    fallback.render_template = mock.Mock(side_effect=KeyError("canvas unavailable"))
    App._clear_active_input_for_error(fallback)
    fallback.set_expr.assert_called_once_with("")


def test_template_viewport_handles_wide_glyphs_and_editing_boundary_decisions() -> None:
    class WideEllipsisFont:
        @staticmethod
        def measure(text: str) -> int:
            return 50 * text.count("…") + 4 * (len(text) - text.count("…"))

    app = _lcd_app()
    with mock.patch.object(app_module.tkfont, "Font", return_value=WideEllipsisFont()):
        shown, offset = App._template_text_view(app, "a" * 40, 20, ("Consolas", 10), 100)
    assert shown == "……"
    assert offset == 50

    app.template_kind = "integral"
    app.template_order = ["var"]
    app.template_index = 0
    app.template_fields = {"var": "x"}
    app.template_cursors = {"var": 1}
    app.render_template = mock.Mock()
    App.template_insert(app, "1")
    assert app.template_fields["var"] == "x"

    app.template_order = ["body"]
    app.template_fields = {"body": "x"}
    app.template_cursors = {"body": 0}
    App.template_backspace(app)
    assert app.template_fields["body"] == "x"


def test_remaining_calculator_shortcuts_preserve_cancel_and_template_behaviour() -> None:
    app = _lcd_app()
    app._active_template_field = mock.Mock()
    app.template_kind = None
    assert App._active_template_field(app) is None
    assert App._template_keypress(app, SimpleNamespace(keysym="x", char="x", state=0)) is None

    app._left_context = mock.Mock(return_value="")
    app.insert = mock.Mock()
    App._insert_function_token(app, "sin(")
    app.insert.assert_called_once_with("sin(")

    app._restart_application = mock.Mock()
    App.on_key(app)
    app._restart_application.assert_called_once_with()

    solve = _lcd_app()
    solve.mode = "Calculate"
    solve.template_kind = None
    solve.expr = _Entry("x+y=2")
    solve.core.memory = {}
    solve.core.equation_symbols = mock.Mock(return_value=["x", "y"])
    with mock.patch.object(app_module.simpledialog, "askstring", return_value=None):
        App.solve_dialog(solve)

    solve._run_background_calculation = mock.Mock()
    with (
        mock.patch.object(app_module.simpledialog, "askstring", return_value="x"),
        mock.patch.object(app_module.simpledialog, "askfloat", side_effect=[0.0, None]),
    ):
        App.solve_dialog(solve)
    solve._run_background_calculation.assert_not_called()

    integral = _lcd_app()
    integral._history_lcd_active = mock.Mock(return_value=False)
    integral.alpha = True
    integral.insert = mock.Mock()
    App.integral_key(integral)
    integral.insert.assert_called_once_with(":")

    polar = _lcd_app()
    polar.core.pol = mock.Mock()
    polar.core.rec = mock.Mock()
    with mock.patch.object(app_module.simpledialog, "askfloat", side_effect=[None, 2.0]):
        App.pol_dialog(polar)
    with mock.patch.object(app_module.simpledialog, "askfloat", side_effect=[1.0, None]):
        App.rec_dialog(polar)
    polar.core.pol.assert_not_called()
    polar.core.rec.assert_not_called()


def test_conversion_errors_and_packaged_smoke_guards_fail_closed_when_runtime_checks_fail() -> None:
    class Pack:
        def pack(self, **_kwargs: object) -> None:
            pass

    class Window(Pack):
        def title(self, _text: str) -> None:
            pass

        def destroy(self) -> None:
            pass

    class StringVar:
        def __init__(self, value: object = "") -> None:
            self.value = str(value)

        def get(self) -> str:
            return self.value

    class Listbox(Pack):
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def curselection(self) -> tuple[int, ...]:
            return (0,)

        def insert(self, *_args: object) -> None:
            pass

    class Button(Pack):
        created: list[Button] = []

        def __init__(self, _parent: object, *, command: object, **_kwargs: object) -> None:
            self.command = command
            self.__class__.created.append(self)

    conversion = _lcd_app()
    conversion.core.ans = 1
    conversion.core.convert = mock.Mock(side_effect=ValueError("unavailable conversion"))
    conversion.err = mock.Mock()
    Button.created.clear()
    with (
        mock.patch.object(app_module.tk, "Toplevel", return_value=Window()),
        mock.patch.object(app_module.tk, "StringVar", StringVar),
        mock.patch.object(app_module.tk, "Listbox", Listbox),
        mock.patch.object(app_module.ttk, "Entry", return_value=Pack()),
        mock.patch.object(app_module.ttk, "Button", Button),
    ):
        App.conversions_dialog(conversion)
        Button.created[0].command()
    conversion.err.assert_called_once()

    class Skin:
        def __init__(self, size: tuple[int, int]) -> None:
            self.size = size

        def __enter__(self) -> Skin:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

    def smoke_patches(skin: Skin):
        return (
            mock.patch.object(app_module.os.path, "isfile", return_value=True),
            mock.patch.object(app_module.Image, "open", return_value=skin),
        )

    patches = smoke_patches(Skin((1, 1)))
    with patches[0], patches[1], pytest.raises(RuntimeError, match="unexpected size"):
        app_module.run_smoke_test()

    patches = smoke_patches(Skin((480, 980)))
    with (
        patches[0],
        patches[1],
        mock.patch.object(app_module.np.random, "default_rng", return_value=SimpleNamespace(integers=lambda _n: 1)),
        pytest.raises(RuntimeError, match="NumPy random"),
    ):
        app_module.run_smoke_test()

    fake_sparse = SimpleNamespace(csr_matrix=lambda _rows: SimpleNamespace(nnz=0))
    fake_scipy = SimpleNamespace(sparse=fake_sparse)
    patches = smoke_patches(Skin((480, 980)))
    with (
        patches[0],
        patches[1],
        mock.patch.object(app_module.np.random, "default_rng", return_value=SimpleNamespace(integers=lambda _n: app_module.np.int64(1))),
        mock.patch.object(app_module, "ScientificCalculatorEngine", return_value=SimpleNamespace(evaluate=mock.Mock(return_value=4))),
        mock.patch.dict(app_module.sys.modules, {"scipy": fake_scipy}),
        pytest.raises(RuntimeError, match="SciPy sparse"),
    ):
        app_module.run_smoke_test()

    fake_sparse = SimpleNamespace(csr_matrix=lambda _rows: SimpleNamespace(nnz=1))
    patches = smoke_patches(Skin((480, 980)))
    with (
        patches[0],
        patches[1],
        mock.patch.object(app_module.np.random, "default_rng", return_value=SimpleNamespace(integers=lambda _n: app_module.np.int64(1))),
        mock.patch.object(app_module, "ScientificCalculatorEngine", return_value=SimpleNamespace(evaluate=mock.Mock(return_value=3))),
        mock.patch.dict(app_module.sys.modules, {"scipy": SimpleNamespace(sparse=fake_sparse)}),
        pytest.raises(RuntimeError, match="Calculation engine"),
    ):
        app_module.run_smoke_test()


def test_remaining_lcd_error_and_template_branches_follow_user_visible_fallbacks() -> None:
    app = _lcd_app()
    calls: list[str] = []
    app.skin_hotspots = [
        ("first", 0, 0, 10, 10, lambda: calls.append("first")),
        ("second", 20, 20, 30, 30, lambda: calls.append("second")),
    ]
    app._calculation_busy = False
    assert App._skin_click(app, SimpleNamespace(x=100, y=100)) is None
    assert calls == []

    form = _lcd_app()
    form._lcd_flow = {"phase": "form", "draft": {}, "field_armed": True}
    form._lcd_current_spec = mock.Mock(return_value=None)
    App._clear_active_input_for_error(form)
    form.set_expr.assert_called_once_with("")

    class Canvas:
        def pack_forget(self) -> None:
            pass

    class MappedExpression:
        def __init__(self) -> None:
            self.pack_called = False
            self.selection_cleared = False

        @staticmethod
        def winfo_ismapped() -> bool:
            return True

        def pack(self, **_kwargs: object) -> None:
            self.pack_called = True

        def selection_clear(self) -> None:
            self.selection_cleared = True

    mapped = object.__new__(App)
    mapped.skin_mode = False
    mapped.template_kind = "integral"
    mapped.template_canvas = Canvas()
    mapped.expr = MappedExpression()
    mapped.result = _Result()
    App.cancel_template(mapped)
    assert mapped.expr.pack_called is False
    assert mapped.expr.selection_cleared is True

    integral = _lcd_app()
    integral.template_kind = "integral"
    integral.template_fields = {"body": "", "var": "x", "lower": "", "upper": ""}
    integral.template_cursors = {"body": 0}
    with pytest.raises(CalculatorError, match="Integral function is empty"):
        App.evaluate_template(integral)

    derivative = _lcd_app()
    derivative.template_kind = "derivative"
    derivative.template_fields = {"body": "", "var": "x", "point": ""}
    derivative.template_cursors = {}
    with pytest.raises(CalculatorError, match="Derivative function is empty"):
        App.evaluate_template(derivative)

    unsupported = _lcd_app()
    unsupported.template_kind = "unknown"
    unsupported.template_fields = {}
    unsupported._calculation_busy = False
    unsupported.cancel_template = mock.Mock()
    App.evaluate_template(unsupported)
    unsupported.cancel_template.assert_called_once_with()


def test_frozen_module_entrypoint_runs_the_real_smoke_mode_without_opening_tk() -> None:
    """The executable's ``__main__`` guard must route --smoke-test to its checker."""
    engine = SimpleNamespace(evaluate=mock.Mock(return_value=4))
    original_argv = sys.argv
    try:
        with mock.patch.object(calculator_engine_module, "ScientificCalculatorEngine", return_value=engine):
            sys.argv = ["scientific_calculator.app", "--smoke-test"]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                runpy.run_module("scientific_calculator.app", run_name="__main__")
    finally:
        sys.argv = original_argv
    engine.evaluate.assert_called_once_with("2+2")
