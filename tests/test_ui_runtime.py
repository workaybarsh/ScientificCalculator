from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import ttk

import pytest

from scientific_calculator.app import App
from scientific_calculator.calculator_engine import CONSTANTS_DATASET_LABELS


@pytest.fixture(scope="module")
def live_app(tmp_path_factory: pytest.TempPathFactory):
    # Reuse one Tcl interpreter for the module. Repeatedly creating and tearing
    # down independent Tk roots is flaky on Windows even when the desktop and
    # Tcl installation are healthy.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path_factory.mktemp("ui-runtime")))
    try:
        app = App()
    except tk.TclError as exc:
        monkeypatch.undo()
        if os.environ.get("SCICALC_REQUIRE_LIVE_UI") == "1":
            raise RuntimeError(f"Live Tk UI was required but could not start: {exc}") from exc
        pytest.skip(f"A live Tk desktop session is unavailable: {exc}")
    app.withdraw()
    app.update_idletasks()
    try:
        yield app
    finally:
        if app.winfo_exists():
            app.destroy()
        monkeypatch.undo()


def _toplevels(app: App) -> list[tk.Toplevel]:
    return [child for child in app.winfo_children() if isinstance(child, tk.Toplevel)]


def _lcd_submit(app: App, value: str | None = None) -> None:
    """Enter one LCD-form value and advance it with the calculator '=' key."""
    if value is not None:
        app.set_expr(value)
    app.equals()
    app.update_idletasks()


def _assert_embedded_lcd_mode(app: App, mode: str) -> None:
    flow = app._lcd_flow
    assert flow is not None
    assert flow["mode"] == mode
    assert app.result.cget("text")
    assert _toplevels(app) == []


def test_all_runtime_scales_preserve_reference_state_and_hotspots(live_app: App) -> None:
    live_app.set_expr("2+2")
    live_app.result.config(text="4")
    live_app.shift = True
    live_app.status_refresh()

    for percent in App.UI_SCALES:
        live_app.apply_scale(percent)
        live_app.update_idletasks()
        applied_scale = live_app._fit_ui_scale_to_display(percent)
        expected = (round(480 * applied_scale / 100), round(980 * applied_scale / 100))

        assert live_app.ui_scale == applied_scale
        assert live_app.geometry().split("+", 1)[0] == f"{expected[0]}x{expected[1]}"
        assert (live_app._skin_img.width(), live_app._skin_img.height()) == expected
        assert live_app.expr.get() == "2+2"
        assert live_app.result.cget("text") == "4"
        assert live_app.shift_status.cget("text") == "SHIFT"
        assert live_app.shift_status.cget("fg") == App.LCD_TEXT_COLOR
        assert live_app.alpha_status.cget("fg") == App.LCD_TEXT_COLOR
        assert len(live_app.skin_hotspots) == 50
        assert all(
            0 <= x1 <= x2 <= expected[0] and 0 <= y1 <= y2 <= expected[1]
            for _, x1, y1, x2, y2, _ in live_app.skin_hotspots
        )


@pytest.mark.parametrize("skin_name", App.SKINS)
def test_each_skin_rebuilds_with_the_same_runtime_contract(live_app: App, skin_name: str) -> None:
    live_app.ui_scale = 100
    live_app.skin_name = skin_name
    live_app._rebuild_scaled_ui()
    live_app.update_idletasks()

    assert live_app.skin_name == skin_name
    assert live_app.geometry().split("+", 1)[0] == "480x980"
    assert (live_app._skin_img.width(), live_app._skin_img.height()) == (480, 980)
    assert len(live_app.skin_hotspots) == 50


@pytest.mark.parametrize("percent", App.UI_SCALES)
def test_integral_template_scales_without_losing_fields(live_app: App, percent: int) -> None:
    live_app.start_integral_template()
    live_app.template_fields.update(
        {"lower": "0", "upper": "2*pi", "body": "sin(x^2)*cos(x)/x", "var": "x"}
    )
    live_app.template_cursors = {
        key: len(value) for key, value in live_app.template_fields.items()
    }
    live_app.result.config(text="integral pending")

    live_app.apply_scale(percent)
    live_app.update_idletasks()

    assert live_app.template_kind == "integral"
    assert live_app.template_fields == {
        "lower": "0",
        "upper": "2*pi",
        "body": "sin(x^2)*cos(x)/x",
        "var": "x",
    }
    assert live_app.result.cget("text") == "integral pending"
    assert live_app.template_canvas.winfo_manager() == "place"


@pytest.mark.parametrize("percent", App.UI_SCALES)
def test_derivative_template_matches_the_parenthesis_free_integral_style(
    live_app: App, percent: int
) -> None:
    live_app.start_derivative_template()
    live_app.template_fields.update({"body": "x^3+2x", "var": "x", "point": "3"})
    live_app.template_cursors = {
        key: len(value) for key, value in live_app.template_fields.items()
    }

    live_app.apply_scale(percent)
    live_app.update_idletasks()

    texts = [
        live_app.template_canvas.itemcget(item, "text")
        for item in live_app.template_canvas.find_all()
        if live_app.template_canvas.type(item) == "text"
    ]
    assert any(text.startswith("d/dx") and "(" not in text for text in texts)
    assert "| x=" in texts
    assert not any(text.startswith("d/dx") and "(" in text for text in texts)
    assert not any(text.startswith(")") for text in texts)


@pytest.mark.parametrize("percent", App.UI_SCALES)
def test_integral_differential_remains_inside_the_lcd_viewport(live_app: App, percent: int) -> None:
    live_app.start_integral_template()
    expression = "sin(x^2)*cos(x)*ln(x)/(x+1)"
    live_app.template_fields["body"] = expression
    live_app.template_cursors["body"] = 0
    live_app.apply_scale(percent)
    live_app.update_idletasks()

    differential_items = [
        item
        for item in live_app.template_canvas.find_all()
        if live_app.template_canvas.type(item) == "text"
        and live_app.template_canvas.itemcget(item, "text") in {"d", "x"}
    ]

    assert len(differential_items) == 2
    assert max(
        live_app.template_canvas.bbox(item)[2] for item in differential_items
    ) <= live_app.template_canvas.winfo_width()

    differential_start = min(
        live_app.template_canvas.bbox(item)[0] for item in differential_items
    )
    body_text, _ = live_app._template_text_view(
        expression,
        0,
        ("Consolas", live_app._fp(19)),
        (
            int(round(live_app._sp(381)))
            - live_app._sp(88)
            - live_app._sp(7)
            - live_app._sp(150)
        ),
    )
    body_item = next(
        item
        for item in live_app.template_canvas.find_all()
        if live_app.template_canvas.type(item) == "text"
        and live_app.template_canvas.itemcget(item, "text") == body_text
    )
    assert live_app.template_canvas.bbox(body_item)[2] < differential_start

    for _ in expression:
        live_app.move(1)
    live_app.update_idletasks()
    assert any(
        expression[-1] in live_app.template_canvas.itemcget(item, "text")
        for item in live_app.template_canvas.find_all()
        if live_app.template_canvas.type(item) == "text"
    )


@pytest.mark.parametrize("mode", App.MODES)
def test_every_mode_can_be_entered_from_the_runtime_app(live_app: App, mode: str) -> None:
    live_app.select_mode(mode)
    live_app.update_idletasks()

    assert live_app.mode == mode
    if mode in App.LCD_WORKSPACE_MODES:
        _assert_embedded_lcd_mode(live_app, mode)
    else:
        assert live_app._lcd_flow is None
        assert live_app.result.cget("text") == App.MODE_HINTS[mode]
    live_app.select_mode("Calculate")
    live_app.update_idletasks()


def test_switching_modes_cancels_an_active_calculus_template(live_app: App) -> None:
    live_app.start_integral_template()
    assert live_app.template_kind == "integral"

    live_app.select_mode("Complex")
    live_app.update_idletasks()

    assert live_app.template_kind is None
    assert not live_app.template_canvas.winfo_ismapped()
    live_app.select_mode("Calculate")


def test_spreadsheet_data_survives_leaving_its_workspace(live_app: App) -> None:
    live_app.sheet.delete_all()
    live_app.sheet.set("A1", "42")

    live_app.select_mode("Spreadsheet")
    live_app.update_idletasks()
    _assert_embedded_lcd_mode(live_app, "Spreadsheet")
    live_app.select_mode("Base-N")

    assert live_app.sheet.cells["A1"] == "42"
    assert live_app.sheet.cache["A1"] == 42

    live_app.sheet.delete_all()
    live_app.select_mode("Calculate")


def test_embedded_lcd_flow_survives_every_scale_without_a_workspace_window(live_app: App) -> None:
    live_app.select_mode("Ratio")
    _lcd_submit(live_app)  # default A:B = X:D form
    assert live_app._lcd_flow["stage"] == "ratio_values"
    live_app.set_expr("12")  # an unsubmitted value must also survive a rebuild
    prompt = live_app.result.cget("text")

    for percent in App.UI_SCALES:
        live_app.apply_scale(percent)
        live_app.update_idletasks()

        _assert_embedded_lcd_mode(live_app, "Ratio")
        assert live_app._lcd_flow["stage"] == "ratio_values"
        assert live_app._lcd_flow["index"] == 0
        assert live_app.expr.get() == "12"
        assert live_app.result.cget("text") == prompt

    live_app.select_mode("Calculate")
    live_app.apply_scale(100)


def test_ratio_runs_entirely_in_the_lcd(live_app: App) -> None:
    live_app.select_mode("Ratio")
    _lcd_submit(live_app)  # ratio type
    _lcd_submit(live_app, "2")  # A
    _lcd_submit(live_app, "3")  # B
    _lcd_submit(live_app, "12")  # D

    _assert_embedded_lcd_mode(live_app, "Ratio")
    assert live_app._lcd_flow["phase"] == "results"
    assert live_app.result.cget("text") == "X = 8"
    live_app.select_mode("Calculate")


def test_inequality_runs_entirely_in_the_lcd(live_app: App) -> None:
    live_app.select_mode("Inequality")
    _lcd_submit(live_app, "2")  # degree
    _lcd_submit(live_app, "1")  # x²
    _lcd_submit(live_app, "-3")  # x
    _lcd_submit(live_app, "2")  # constant
    _lcd_submit(live_app, "1")  # >

    _assert_embedded_lcd_mode(live_app, "Inequality")
    assert live_app._lcd_flow["phase"] == "results"
    assert "1" in live_app.result.cget("text")
    assert "2" in live_app.result.cget("text")
    live_app.select_mode("Calculate")


def test_equation_polynomial_runs_entirely_in_the_lcd(live_app: App) -> None:
    live_app.select_mode("Equation/Func")
    _lcd_submit(live_app)  # Polynomial
    _lcd_submit(live_app, "2")  # degree
    _lcd_submit(live_app, "1")  # x² coefficient
    _lcd_submit(live_app, "-3")  # x coefficient
    _lcd_submit(live_app, "2")  # constant

    _assert_embedded_lcd_mode(live_app, "Equation/Func")
    assert live_app._lcd_flow["phase"] == "results"
    result_lines = "\n".join(live_app._lcd_flow["result_lines"])
    assert "x1 =" in result_lines
    assert "Vertex = (1.5, -0.25)" in result_lines
    live_app.select_mode("Calculate")


def test_table_runs_entirely_in_the_lcd_and_browses_rows(live_app: App) -> None:
    live_app.core.settings.table_two_functions = False
    live_app.select_mode("Table")
    _lcd_submit(live_app, "x^2")
    _lcd_submit(live_app, "-1")
    _lcd_submit(live_app, "1")
    _lcd_submit(live_app, "1")

    _assert_embedded_lcd_mode(live_app, "Table")
    assert live_app._lcd_flow["phase"] == "results"
    assert live_app.result.cget("text") == "x=-1  f=1"
    live_app.vertical_move(1)
    assert live_app.result.cget("text") == "x=0  f=0"
    live_app.select_mode("Calculate")


def test_distribution_runs_entirely_in_the_lcd(live_app: App) -> None:
    live_app.select_mode("Distribution")
    _lcd_submit(live_app)  # Normal PD
    _lcd_submit(live_app, "0")  # x
    _lcd_submit(live_app, "1")  # sigma
    _lcd_submit(live_app, "0")  # mu

    _assert_embedded_lcd_mode(live_app, "Distribution")
    assert live_app._lcd_flow["phase"] == "results"
    assert live_app.result.cget("text").startswith("Normal PD = 0.398942")
    live_app.select_mode("Calculate")


def test_matrix_vector_and_statistics_workflows_stay_in_the_lcd(live_app: App) -> None:
    live_app.select_mode("Matrix")
    _lcd_submit(live_app)  # Define / Edit
    _lcd_submit(live_app)  # MatA
    _lcd_submit(live_app, "2")
    _lcd_submit(live_app, "2")
    for value in ("1", "2", "3", "4"):
        _lcd_submit(live_app, value)
    assert live_app._lcd_flow["phase"] == "results"
    assert live_app.result.cget("text") == "MatA r1: [1, 2]"

    live_app.optn_key()
    _lcd_submit(live_app, "5")  # det(A)
    _lcd_submit(live_app)  # MatA
    assert live_app.result.cget("text") == "det = -2"
    _assert_embedded_lcd_mode(live_app, "Matrix")

    live_app.select_mode("Vector")
    _lcd_submit(live_app)  # Define / Edit
    _lcd_submit(live_app)  # VctA
    _lcd_submit(live_app, "2")
    _lcd_submit(live_app, "3")
    _lcd_submit(live_app, "4")
    assert live_app.result.cget("text") == "VctA = [3, 4]"

    live_app.optn_key()
    _lcd_submit(live_app, "7")  # Abs
    _lcd_submit(live_app)  # VctA
    assert live_app.result.cget("text") == "abs = 5"
    _assert_embedded_lcd_mode(live_app, "Vector")

    live_app.select_mode("Statistics")
    _lcd_submit(live_app)  # 1-Variable
    _lcd_submit(live_app, "1, 2, 3")
    assert live_app.result.cget("text") == "n = 3"
    _assert_embedded_lcd_mode(live_app, "Statistics")
    live_app.select_mode("Calculate")


def test_complex_integral_template_accepts_the_standard_x_variable(live_app: App) -> None:
    """Exercise the real UI/worker path for a non-real generalized integral."""
    live_app.select_mode("Complex")
    live_app.start_integral_template()
    live_app.template_fields.update(
        {"lower": "0", "upper": "1", "body": "sqrt(ln(x))", "var": "x"}
    )
    live_app.template_cursors = {
        key: len(value) for key, value in live_app.template_fields.items()
    }

    live_app.evaluate_template()
    deadline = time.monotonic() + 15
    while live_app._calculation_busy and time.monotonic() < deadline:
        live_app.update()
        time.sleep(0.02)

    assert not live_app._calculation_busy
    assert live_app.template_kind is None
    assert live_app.result.cget("text") == "∫=-0.886i"
    live_app.select_mode("Calculate")


def test_lcd_nested_integral_stays_embedded_and_persists_history(live_app: App) -> None:
    """Run a nested-bound double integral through LCD fields and the worker."""
    live_app.select_mode("Calculate")
    history_count = len(live_app.core.history)
    live_app.set_expr("x*y")
    live_app.integral_key()
    _assert_embedded_lcd_mode(live_app, "Integral")

    _lcd_submit(live_app, "4")  # Double Integral
    _lcd_submit(live_app)  # f(x, y)
    _lcd_submit(live_app)  # outer differential x
    _lcd_submit(live_app)  # inner differential y
    _lcd_submit(live_app, "0")
    _lcd_submit(live_app, "1")
    _lcd_submit(live_app, "0")
    _lcd_submit(live_app, "x")  # inner upper bound may depend on outer x

    deadline = time.monotonic() + 15
    while live_app._calculation_busy and time.monotonic() < deadline:
        live_app.update()
        time.sleep(0.02)

    assert not live_app._calculation_busy
    _assert_embedded_lcd_mode(live_app, "Integral")
    assert live_app._lcd_flow["phase"] == "results"
    assert live_app.result.cget("text") == "∫∫ = 0.125"
    assert len(live_app.core.history) == history_count + 1
    expression, result = live_app.core.history[-1]
    assert "x*y" in expression
    assert result == "0.125"
    assert live_app._settings_store().load_history()[-1] == (expression, result)
    assert _toplevels(live_app) == []
    live_app.select_mode("Calculate")


def test_complex_double_integral_runs_through_the_embedded_lcd_flow(live_app: App) -> None:
    live_app.select_mode("Complex")
    live_app.set_expr("i*x+y")
    live_app.integral_key()
    _assert_embedded_lcd_mode(live_app, "Complex Integral")

    _lcd_submit(live_app, "3")  # Complex Double Integral
    _lcd_submit(live_app)  # f(x, y)
    _lcd_submit(live_app)  # outer differential x
    _lcd_submit(live_app)  # inner differential y
    for value in ("0", "1", "0", "1"):
        _lcd_submit(live_app, value)

    deadline = time.monotonic() + 15
    while live_app._calculation_busy and time.monotonic() < deadline:
        live_app.update()
        time.sleep(0.02)

    assert not live_app._calculation_busy
    _assert_embedded_lcd_mode(live_app, "Complex Integral")
    assert live_app._lcd_flow["phase"] == "results"
    assert live_app.result.cget("text") == "∫∫ = 0.500+0.500i"
    assert "i*x+y" in live_app.core.history[-1][0]
    assert live_app.core.history[-1][1] == "1/2+1/2i"
    assert _toplevels(live_app) == []
    live_app.select_mode("Calculate")


def test_differential_equation_runs_with_initial_conditions_in_the_embedded_lcd(live_app: App) -> None:
    """Exercise Equation/Func → ODE through the real isolated UI worker."""
    live_app.select_mode("Equation/Func")
    history_count = len(live_app.core.history)

    _lcd_submit(live_app, "3")  # Differential Equation
    _lcd_submit(live_app, "dy/dx=y")
    _lcd_submit(live_app, "2")  # dependent y
    _lcd_submit(live_app, "1")  # independent x
    _lcd_submit(live_app, "2")  # y(x0) condition
    _lcd_submit(live_app, "0")
    _lcd_submit(live_app, "1")

    deadline = time.monotonic() + 15
    while live_app._calculation_busy and time.monotonic() < deadline:
        live_app.update()
        time.sleep(0.02)

    assert not live_app._calculation_busy
    _assert_embedded_lcd_mode(live_app, "Equation/Func")
    assert live_app._lcd_flow["phase"] == "results"
    assert live_app.result.cget("text") == "y(x) = exp(x)"
    assert len(live_app.core.history) == history_count + 1
    expression, result = live_app.core.history[-1]
    assert expression.startswith("ODE dy/dx=y")
    assert result == "y(x) = exp(x)"
    assert live_app._settings_store().load_history()[-1] == (expression, result)
    assert _toplevels(live_app) == []
    live_app.select_mode("Calculate")


def test_lcd_matrix_identity_copy_and_binary_operation_paths(live_app: App) -> None:
    live_app.core.define_matrix("MatA", [[1, 2], [3, 4]])
    live_app.core.define_matrix("MatB", [[2, 0], [1, 2]])

    live_app.select_mode("Matrix")
    _lcd_submit(live_app, "4")  # A × B
    _lcd_submit(live_app, "1")
    _lcd_submit(live_app, "2")
    assert live_app.result.cget("text") == "* r1: [4, 4]"

    live_app.select_mode("Matrix")
    _lcd_submit(live_app, "11")  # Identity
    _lcd_submit(live_app, "3")
    assert live_app.result.cget("text") == "I r1: [1, 0, 0]"

    live_app.select_mode("Matrix")
    _lcd_submit(live_app, "12")  # Copy
    _lcd_submit(live_app, "1")
    _lcd_submit(live_app, "3")
    assert live_app.result.cget("text") == "MatA → MatC"
    assert live_app.core.matrices["MatC"].tolist() == [[1, 2], [3, 4]]
    live_app.select_mode("Calculate")


def test_lcd_vector_statistic_distribution_and_secondary_ratio_paths(live_app: App) -> None:
    live_app.core.define_vector("VctA", [1, 2])
    live_app.core.define_vector("VctB", [3, 4])

    live_app.select_mode("Vector")
    _lcd_submit(live_app, "4")  # Dot
    _lcd_submit(live_app, "1")
    _lcd_submit(live_app, "2")
    assert live_app.result.cget("text") == "dot = 11"

    live_app.select_mode("Vector")
    _lcd_submit(live_app, "9")  # Scalar ×
    _lcd_submit(live_app, "1")
    _lcd_submit(live_app, "3")
    assert live_app.result.cget("text") == "scale = [3, 6]"

    live_app.select_mode("Vector")
    _lcd_submit(live_app, "10")  # Copy
    _lcd_submit(live_app, "2")
    _lcd_submit(live_app, "3")
    assert live_app.result.cget("text") == "VctB → VctC"
    assert live_app.core.vectors["VctC"].tolist() == [3, 4]

    live_app.select_mode("Statistics")
    _lcd_submit(live_app, "2")  # Linear regression
    _lcd_submit(live_app, "1,2,3")
    _lcd_submit(live_app, "3,5,7")
    assert live_app.result.cget("text") == "a = 1"
    live_app.vertical_move(1)
    assert live_app.result.cget("text") == "b = 2"

    live_app.select_mode("Statistics")
    _lcd_submit(live_app, "9")  # P(t)
    _lcd_submit(live_app, "0")
    assert live_app.result.cget("text") == "P(t) = 0.5"

    live_app.select_mode("Distribution")
    _lcd_submit(live_app, "4")  # Binomial PD
    for value in ("2", "4", "0.5"):
        _lcd_submit(live_app, value)
    assert live_app.result.cget("text") == "Binomial PD = 0.375"

    live_app.select_mode("Distribution")
    _lcd_submit(live_app, "7")  # Poisson CD
    for value in ("2", "1"):
        _lcd_submit(live_app, value)
    assert live_app.result.cget("text").startswith("Poisson CD = ")

    live_app.select_mode("Ratio")
    _lcd_submit(live_app, "2")  # A:B = C:X
    for value in ("2", "3", "12"):
        _lcd_submit(live_app, value)
    assert live_app.result.cget("text") == "X = 18"
    live_app.select_mode("Calculate")


def test_lcd_table_simultaneous_and_spreadsheet_tool_paths(live_app: App) -> None:
    live_app.core.settings.table_two_functions = True
    live_app.select_mode("Table")
    for value in ("x", "x+1", "-1", "1", "1"):
        _lcd_submit(live_app, value)
    assert live_app.result.cget("text") == "x=-1  f=-1  g=0"
    live_app.core.settings.table_two_functions = False

    live_app.select_mode("Equation/Func")
    _lcd_submit(live_app, "2")  # Simultaneous
    _lcd_submit(live_app, "2")
    for value in ("1", "1", "1", "-1", "3", "1"):
        _lcd_submit(live_app, value)
    assert live_app.result.cget("text") == "x1 = 2"

    live_app.sheet.delete_all()
    live_app.sheet.set("A1", "1")
    live_app.select_mode("Spreadsheet")
    live_app.optn_key()
    _lcd_submit(live_app, "5")  # Fill value
    for value in ("2", "2", "7"):
        _lcd_submit(live_app, value)
    assert live_app.sheet.cells["B2"] == "7"

    live_app.select_mode("Spreadsheet")
    live_app.optn_key()
    _lcd_submit(live_app, "6")  # Fill formula
    for value in ("3", "1", "=2+2"):
        _lcd_submit(live_app, value)
    assert live_app.sheet.cells["C1"] == "=2+2"

    live_app.select_mode("Spreadsheet")
    live_app.optn_key()
    _lcd_submit(live_app, "4")  # Cut cell
    _lcd_submit(live_app, "4")
    _lcd_submit(live_app, "1")
    assert live_app.sheet.cells["D1"] == "=2+2"
    assert "A1" not in live_app.sheet.cells

    live_app.optn_key()
    _lcd_submit(live_app, "9")  # Free space
    assert live_app.result.cget("text").startswith("Free space = ")

    live_app.select_mode("Spreadsheet")
    live_app.optn_key()
    _lcd_submit(live_app, "10")  # Delete all
    _lcd_submit(live_app, "2")
    assert live_app.sheet.cells == {}
    live_app.select_mode("Calculate")


def test_spreadsheet_cell_navigation_edit_and_copy_stay_in_the_lcd(live_app: App) -> None:
    live_app.sheet.delete_all()
    live_app.core.settings.spreadsheet_show_cell = "Value"
    live_app.select_mode("Spreadsheet")
    live_app.set_expr("=1+1")
    _lcd_submit(live_app)
    assert live_app.sheet.cells["A1"] == "=1+1"
    assert live_app.sheet.cache["A1"] == 2
    assert live_app.result.cget("text").startswith("Saved A1 = 2")

    live_app.optn_key()
    _lcd_submit(live_app, "3")  # Copy cell
    _lcd_submit(live_app, "2")  # destination column B
    _lcd_submit(live_app, "1")  # destination row 1
    assert live_app.sheet.cells["B1"] == "=1+1"
    assert live_app.sheet.cache["B1"] == 2

    live_app.move(1)
    live_app.vertical_move(1)
    assert live_app._lcd_sheet_address() == "B2"
    _assert_embedded_lcd_mode(live_app, "Spreadsheet")
    live_app.sheet.delete_all()
    live_app.select_mode("Calculate")


def test_lcd_defaults_are_replaced_by_the_first_key_and_arrows_are_contextual(live_app: App) -> None:
    live_app.select_mode("Ratio")
    assert live_app.expr.get() == "1"
    live_app.num_key("2")
    assert live_app.expr.get() == "2"  # never append to the default as "12"

    live_app.select_mode("Distribution")
    assert live_app.expr.get() == "1"
    assert live_app._entry_horizontal_key(1) == "break"
    assert live_app.expr.get() == "2"
    _lcd_submit(live_app)
    assert live_app._lcd_flow["stage"] == "distribution_run"
    assert live_app._lcd_flow["index"] == 0
    assert live_app._entry_vertical_key(1) == "break"
    assert live_app._lcd_flow["index"] == 1
    live_app.select_mode("Calculate")


def test_setup_remains_a_separate_settings_window(live_app: App) -> None:
    assert _toplevels(live_app) == []
    live_app.setup_dialog()
    windows = _toplevels(live_app)
    assert len(windows) == 1
    assert windows[0].title() == "SETUP"
    widgets=[]

    def collect(widget):
        for child in widget.winfo_children():
            widgets.append(child)
            collect(child)

    collect(windows[0])
    combobox_values=[tuple(widget.cget("values")) for widget in widgets if isinstance(widget, ttk.Combobox)]
    assert CONSTANTS_DATASET_LABELS in combobox_values
    assert "Clear History" in {widget.cget("text") for widget in widgets if isinstance(widget, ttk.Button)}
    windows[0].destroy()
