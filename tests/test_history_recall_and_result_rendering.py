"""History recall and the rendering of completed results.

Recalling a record must restore its structured template payload rather than
reparsing display text, and results must render their non-finite and empty
states honestly instead of implying a value.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import numpy as np
import pytest

from scientific_calculator.app import App
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine
from scientific_calculator.history import CalculationHistoryEntry
from scientific_calculator.lcd_layout import ResultViewport


def _bare_app() -> App:
    app = object.__new__(App)
    app.mode = "Calculate"
    app.template_kind = None
    app._template_rendering = False
    app._lcd_flow = None
    app._set_lcd_label = mock.Mock()
    app.render_template = mock.Mock()
    app._reset_lcd_flow = mock.Mock()
    app._reset_history_browsing = mock.Mock()
    return app


def test_history_header_uses_equals_navigation_without_a_stale_optn_hint() -> None:
    app = _bare_app()
    app._lcd_flow = {
        "mode": "History",
        "phase": "results",
        "title": "HISTORY",
        "result_lines": ["1 + 1 = 2"],
        "result_index": 0,
        "result_offset": 0,
    }
    expressions: list[str] = []
    app._set_lcd_expression = expressions.append
    app._result_viewport = lambda text, offset: ResultViewport(text, offset, len(text))
    app.result = SimpleNamespace(config=mock.Mock())
    app.expr = SimpleNamespace(focus_set=mock.Mock())

    App._lcd_render_result(app)

    assert expressions == ["HISTORY   ▲▼"]


def test_history_horizontal_arrows_reach_the_result_viewport() -> None:
    app = _bare_app()
    app._lcd_flow = {"mode": "History", "phase": "results"}
    app._lcd_move = mock.Mock(return_value=True)

    App.move(app, 1)

    app._lcd_move.assert_called_once_with(1)


def test_history_lcd_move_prefers_a_structured_integrand_viewport() -> None:
    app = _bare_app()
    app._lcd_flow = {"mode": "History", "phase": "results", "result_lines": ["long"], "result_index": 0}
    app._scroll_history_integral_preview = mock.Mock(return_value=True)

    assert App._lcd_move(app, 1) is True

    app._scroll_history_integral_preview.assert_called_once_with(1)


def test_equals_recalls_structured_history_with_its_template_payload() -> None:
    app = _bare_app()
    entry = CalculationHistoryEntry("∫0→1 x dx", "1/2", kind="integral_single", metadata={"integrand": "x"})
    app._lcd_flow = {"mode": "History", "history_entries": [entry], "result_index": 0}
    app._recall_structured_history = mock.Mock(return_value=True)

    App._lcd_recall_history_entry(app)

    app._recall_structured_history.assert_called_once_with(entry)


def test_history_integral_preview_reuses_the_math_template_without_an_edit_caret() -> None:
    app = _bare_app()
    entry = CalculationHistoryEntry(
        "∫0→1 x^2 dx",
        "1/3",
        kind="integral_single",
        metadata={
            "integrand": "x^2",
            "variables": ["x"],
            "bounds": [{"lower": "0", "upper": "1"}],
        },
    )
    app._lcd_flow = {"mode": "History", "history_body_cursor": 0}
    captured: dict[str, object] = {}

    def record_render() -> None:
        captured["kind"] = app.template_kind
        captured["fields"] = dict(app.template_fields)
        captured["read_only"] = app._template_read_only

    app.render_template = record_render

    assert App._render_history_integral_preview(app, entry) is True
    assert captured == {
        "kind": "integral",
        "fields": {"body": "x^2", "lower": "0", "upper": "1", "var": "x"},
        "read_only": True,
    }
    assert app.template_kind is None


def test_integral_history_fields_are_complete_when_first_frame_is_rendered() -> None:
    app = _bare_app()
    app.expr = SimpleNamespace(get=lambda: "")

    App.start_integral_template(
        app,
        "x^2",
        restored_fields={"lower": "0", "upper": "1", "var": "x"},
    )

    assert app.template_fields == {"lower": "0", "upper": "1", "body": "x^2", "var": "x"}
    app.render_template.assert_called_once_with()


def test_multiple_integral_history_fields_are_complete_when_first_frame_is_rendered() -> None:
    app = _bare_app()
    app.expr = SimpleNamespace(get=lambda: "")

    App.start_multiple_integral_template(
        app,
        "double",
        restored_fields={
            "body": "x+y",
            "outer_lower": "0",
            "outer_upper": "1",
            "outer_var": "x",
            "inner_lower": "0",
            "inner_upper": "x",
            "inner_var": "y",
        },
    )

    assert app.template_fields["body"] == "x+y"
    assert app.template_fields["inner_upper"] == "x"
    app.render_template.assert_called_once_with()


def test_statistics_results_render_none_and_nonfinite_values_as_na() -> None:
    app = _bare_app()

    assert App._lcd_result_number_text(app, None) == "n/a"
    assert App._lcd_result_number_text(app, float("nan")) == "n/a"
    assert App._lcd_result_number_text(app, object()) == "n/a"


def test_vector_angle_rejects_nonfinite_data_without_claiming_it_is_zero() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)

    with pytest.raises(CalculatorError, match="vektör verileri geçersiz"):
        engine.vector_op("angle", np.array([np.nan, 1.0]), np.array([1.0, 0.0]))


def test_vector_operation_translates_unexpected_shape_type_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)
    monkeypatch.setattr(np, "cross", lambda *_args: (_ for _ in ()).throw(TypeError("bad vector")))

    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.vector_op("cross", [1, 0], [0, 1])


def test_linear_inequality_and_quartic_polynomial_are_available_in_the_lcd() -> None:
    app = _bare_app()
    app._lcd_begin_form = mock.Mock()

    App._lcd_start_inequality(app)
    inequality_field = app._lcd_begin_form.call_args.args[1][0]
    assert inequality_field["minimum"] == 1
    assert inequality_field["maximum"] == 4

    App.start_polynomial_template(app, 4)
    assert app.template_order == [f"polynomial_{index}" for index in range(5)]


def test_quartic_real_result_includes_all_real_roots() -> None:
    app = _bare_app()
    app.core = ScientificCalculatorEngine(cas_isolated=False)
    app.core.settings.equation_complex = False

    lines = App._polynomial_result_lines(app, 4, [1, 0, -5, 0, 4])

    assert {line.split(" = ")[1] for line in lines} == {"-2", "-1", "1", "2"}


def test_real_only_polynomial_says_when_no_real_roots_exist() -> None:
    app = _bare_app()
    app.core = ScientificCalculatorEngine(cas_isolated=False)
    app.core.settings.equation_complex = False

    assert App._polynomial_result_lines(app, 2, [1, 0, 1]) == ["No real roots", "Vertex = (0, 1)"]


def test_quartic_template_uses_a_readable_two_row_layout() -> None:
    app = _bare_app()
    app.template_kind = "polynomial"
    app.template_fields = {"degree": 4, **{f"polynomial_{index}": "" for index in range(5)}}
    app.template_order = [f"polynomial_{index}" for index in range(5)]
    app.template_index = 0
    app.template_cursors = {key: 0 for key in app.template_order}
    app.skin_mode = False
    app._sp = lambda value: value
    app._fp = lambda value: value
    app.expr = SimpleNamespace(pack_forget=mock.Mock())
    app.result = SimpleNamespace()
    app._draw_edit_text = mock.Mock()
    app.template_canvas = SimpleNamespace(
        winfo_ismapped=lambda: True,
        winfo_width=lambda: 480,
        pack=mock.Mock(),
        delete=mock.Mock(),
        config=mock.Mock(),
        create_rectangle=mock.Mock(),
        create_text=mock.Mock(),
        focus_set=mock.Mock(),
    )

    App.render_template(app)

    assert app._draw_edit_text.call_count == 5
    assert any(call.kwargs.get("text") == "= 0" for call in app.template_canvas.create_text.call_args_list)


@pytest.mark.parametrize(
    ("decimal_mark", "separator", "value", "expected"),
    [
        ("Dot", False, 1234.5, "1234.50"),
        ("Dot", True, 1234.5, "1,234.50"),
        ("Comma", False, 1234.5, "1234,50"),
        ("Comma", True, 1234.5, "1.234,50"),
    ],
)
def test_fixed_numeric_formatting_has_an_unambiguous_locale_policy(
    decimal_mark: str, separator: bool, value: float, expected: str
) -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 2
    engine.settings.decimal_mark = decimal_mark
    engine.settings.digit_separator = separator

    assert engine.format_result(value, approximate=True) == expected


def test_engineering_symbol_display_preserves_exact_results_but_scales_approximations() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)
    engine.settings.engineer_symbol = True
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 2

    assert engine.format_result(0.9, approximate=True) == "900.00m"
    assert engine.format_result(1_024_000, approximate=True) == "1.02M"
    assert engine.format_result(engine.parse("1/1000")) == "1/1000"


def test_engineering_symbol_handles_sci_mode_rounding_promotion_and_out_of_range_values() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)
    engine.settings.engineer_symbol = True
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 2

    assert engine.format_result(999_999, approximate=True) == "1.00M"
    assert engine.format_result(1e-16, approximate=True) == "0.0000000000000001"

    engine.settings.number_format = "Sci"
    assert "e" not in engine.format_result(1_000, approximate=True).lower()


def test_decimal_comma_arrays_use_semicolons_and_complex_double_integrals_keep_structure() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)
    engine.settings.decimal_mark = "Comma"

    assert engine.format_result(np.array([1.5, 2.0])) == "[1,500; 2,000]"

    engine.complex_double_integral("x + I*y", "0", "1", "0", "1")
    entry = engine.history[-1]
    assert entry.kind == "complex_calculus"
    assert entry.metadata["operation"] == "double_integral"


def test_structured_history_previews_cover_multiple_and_complex_integrals() -> None:
    multiple = CalculationHistoryEntry(
        "double", "2", kind="integral_double", metadata={
            "integrand": "x+y",
            "bounds": [
                {"variable": "x", "lower": "0", "upper": "1"},
                {"variable": "y", "lower": "0", "upper": "x"},
            ],
        },
    )
    triple = CalculationHistoryEntry(
        "triple", "3", kind="integral_triple", metadata={
            "integrand": "x+y+z",
            "bounds": [
                {"variable": "x", "lower": "0", "upper": "1"},
                {"variable": "y", "lower": "0", "upper": "x"},
                {"variable": "z", "lower": "0", "upper": "y"},
            ],
        },
    )
    complex_entry = CalculationHistoryEntry(
        "complex", "i", kind="complex_calculus", metadata={
            "operation": "double_integral",
            "integrand": "x+I*y",
            "bounds": [
                {"variable": "x", "lower": "0", "upper": "1"},
                {"variable": "y", "lower": "0", "upper": "x"},
            ],
        },
    )

    assert App._history_integral_preview(multiple)[1]["inner_upper"] == "x"
    assert App._history_integral_preview(triple)[1]["middle_var"] == "y"
    assert App._history_integral_preview(complex_entry)[0] == "multiple_integral"
    assert App._history_integral_preview(CalculationHistoryEntry("x", "1")) is None

    malformed_multiple = CalculationHistoryEntry(
        "double", "0", kind="integral_double", metadata={"integrand": "0", "bounds": [None, None]},
    )
    malformed_complex = CalculationHistoryEntry(
        "complex", "0", kind="complex_calculus", metadata={"operation": "double_integral", "bounds": [None, None]},
    )
    assert App._history_integral_preview(malformed_multiple)[1]["inner_var"] == ""
    assert App._history_integral_preview(malformed_complex)[1]["inner_var"] == ""


def test_history_preview_renderer_and_scroller_use_only_the_integrand_viewport() -> None:
    app = _bare_app()
    entry = CalculationHistoryEntry(
        "∫", "1/2", kind="integral_single", metadata={"integrand": "x" * 100},
    )
    app._lcd_flow = {
        "mode": "History",
        "phase": "results",
        "title": "HISTORY",
        "history_entries": [entry],
        "result_lines": ["ignored"],
        "result_index": 0,
        "result_offset": 0,
    }
    app._set_lcd_expression = mock.Mock()
    app._show_completed_result = mock.Mock()
    app.expr = SimpleNamespace(focus_set=mock.Mock())
    app.result = SimpleNamespace(config=mock.Mock())

    App._lcd_render_result(app)

    app._show_completed_result.assert_called_once_with("1/2")

    app._lcd_content_width = lambda: 300
    app._sp = lambda value: value
    app._fp = lambda value: value
    app._template_text_view = lambda *_args, **_kwargs: ("…", 0)
    app._lcd_render_result = mock.Mock()
    assert App._scroll_history_integral_preview(app, 1) is True
    assert app._lcd_flow["history_body_cursor"] == 1
    assert App._scroll_history_integral_preview(app, -1) is True
    assert App._scroll_history_integral_preview(app, -1) is False

    app._lcd_flow["history_entries"] = [CalculationHistoryEntry("ordinary", "1")]
    assert App._scroll_history_integral_preview(app, 1) is False
    app._lcd_flow["history_entries"] = [CalculationHistoryEntry("∫", "1", kind="integral_single", metadata={"integrand": "x"})]
    app._template_text_view = lambda *_args, **_kwargs: ("x", 0)
    assert App._scroll_history_integral_preview(app, 1) is False
    app._lcd_flow = None
    assert App._scroll_history_integral_preview(app, 1) is False


def test_non_integral_history_does_not_invoke_the_template_preview_renderer() -> None:
    app = _bare_app()
    app._lcd_flow = {"mode": "History"}

    assert App._render_history_integral_preview(app, CalculationHistoryEntry("ordinary", "1")) is False


def test_real_history_recall_uses_the_hydrated_starter_path() -> None:
    app = _bare_app()
    app.expr = SimpleNamespace(get=lambda: "")
    app._show_completed_result = mock.Mock()
    integral = CalculationHistoryEntry(
        "∫", "1/2", kind="integral_single", metadata={
            "integrand": "x", "variables": ["x"], "bounds": [{"lower": "0", "upper": "1"}],
        },
    )
    multiple = CalculationHistoryEntry(
        "∫∫", "1", kind="integral_double", metadata={
            "integrand": "x+y",
            "bounds": [
                {"variable": "x", "lower": "0", "upper": "1"},
                {"variable": "y", "lower": "0", "upper": "x"},
            ],
        },
    )

    assert App._recall_structured_history(app, integral) is True
    assert app.template_fields["upper"] == "1"
    app.template_kind = None
    assert App._recall_structured_history(app, multiple) is True
    assert app.template_fields["inner_upper"] == "x"
