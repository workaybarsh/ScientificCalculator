"""LCD result-viewport, history, and rebuild state transitions.

These tests deliberately exercise the same controller paths that keyboard and
skin-button input use.  They keep the assertions at the public LCD-state
boundary so result text, history records, and calculus actions remain
inspectable without a live Tk display.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest

from scientific_calculator.app import App
from scientific_calculator.calculator_engine import CalculatorError
from scientific_calculator.history import CalculationHistoryEntry


class _Entry:
    def __init__(self, text: str = "", cursor: int = 0) -> None:
        self.text = text
        self.cursor = cursor

    def get(self) -> str:
        return self.text

    def index(self, _where: object) -> int:
        return self.cursor

    def icursor(self, index: int) -> None:
        self.cursor = index

    def delete(self, _first: object, _last: object | None = None) -> None:
        self.text = ""

    def insert(self, _where: object, text: object) -> None:
        self.text = str(text)

    def selection_range(self, _first: object, _last: object) -> None:
        pass

    def focus_set(self) -> None:
        pass


class _Result:
    def __init__(self, width: int = 30, text: str = "0") -> None:
        self.width = width
        self.text = text
        self.config_calls: list[dict[str, object]] = []

    def winfo_width(self) -> int:
        return self.width

    def cget(self, key: str) -> str:
        if key == "text":
            return self.text
        # A missing Tk root makes App's measured-font fallback the active,
        # deterministic rendering path in these headless tests.
        raise AttributeError(key)

    def config(self, **options: object) -> None:
        self.config_calls.append(options)
        if "text" in options:
            self.text = str(options["text"])


def _app(*, width: int = 30, flow: dict[str, object] | None = None) -> App:
    app = object.__new__(App)
    app.expr = _Entry()
    app.result = _Result(width)
    app._lcd_flow = flow
    app._sp = lambda value: value
    return app


def test_completed_result_viewport_scrolls_without_losing_the_full_value() -> None:
    app = _app(width=30)

    first = App._show_completed_result(app, "ABCDEFGHI")
    assert first.text == "ABC"
    assert app._completed_result_text == "ABCDEFGHI"
    assert App._scroll_completed_result(app, 1) is True
    assert app._completed_result_offset == 1
    assert app.result.text == "BCD"

    # Re-rendering after a scale/layout rebuild retains the prior scroll
    # position instead of resetting an in-progress inspection to the start.
    retained = App._show_completed_result(app, "ABCDEFGHI", reset=False)
    assert retained.offset == 1
    assert retained.text == "BCD"

    short = _app(width=30)
    App._show_completed_result(short, "ok")
    assert App._scroll_completed_result(short, 1) is False
    assert App._scroll_completed_result(_app(width=30), 1) is False


def test_lcd_width_and_labels_fall_back_safely_without_a_live_widget_font() -> None:
    app = _app(width=0)

    # A widget can transiently report zero while Tk lays out a scaled skin.
    # The controller must use its known LCD width rather than render nothing.
    assert App._lcd_content_width(app) == 381
    assert App._lcd_measure_text(app, "abc") == 30

    App._set_lcd_label(app, "Differential Equation")
    assert "…" not in app.result.text
    assert app.result.text.replace("\n", " ") == "Differential Equation"

    # A just-placed widget may report one pixel until Tk processes idle layout.
    # That transient value must use the same fallback instead of clipping a
    # previously completed result to a single character.
    app.result.width = 1
    assert App._lcd_content_width(app) == 381


def test_result_flow_arrows_pan_only_overflow_and_keep_row_offset_at_edges() -> None:
    app = _app(
        width=30,
        flow={
            "mode": "History",
            "phase": "results",
            "title": "HISTORY",
            "result_lines": ["ABCDEFGHI"],
            "result_index": 0,
            "result_offset": 2,
        },
    )

    assert App._lcd_move(app, 1) is True
    assert app._lcd_flow["result_offset"] == 3
    assert app.result.text == "DEF"

    # ▲/▼ at a one-row boundary must not reset its horizontal inspection
    # offset.  Moving to another row is the only event that resets it.
    assert App._lcd_vertical_move(app, 1) is True
    assert app._lcd_flow["result_index"] == 0
    assert app._lcd_flow["result_offset"] == 3

    # Moving between rows deliberately starts the next row at its left edge.
    app._lcd_flow["result_lines"].append("JKLMNOPQ")
    assert App._lcd_vertical_move(app, 1) is True
    assert app._lcd_flow["result_index"] == 1
    assert app._lcd_flow["result_offset"] == 0

    empty = _app(flow={"mode": "History", "phase": "results", "result_lines": []})
    assert App._lcd_move(empty, 1) is False
    fixed = _app(
        width=30,
        flow={"mode": "History", "phase": "results", "result_lines": ["ok"], "result_index": 0},
    )
    assert App._lcd_move(fixed, 1) is False


def test_history_lcd_uses_full_newest_first_records_and_equals_recalls_raw_entry() -> None:
    app = _app(flow=None)
    app.core = SimpleNamespace(history=[("x", "1"), ("very_long_expression", "123456789")])
    app._lcd_show_results = mock.Mock()

    App._lcd_start_history(app)

    assert app._lcd_flow["history_entries"] == [
        ("very_long_expression", "123456789"),
        ("x", "1"),
    ]
    app._lcd_show_results.assert_called_once_with(
        "HISTORY", ["very_long_expression = 123456789", "x = 1"]
    )

    # An already-initialized flow retains its mapping while its newest-first
    # records are refreshed.
    app._lcd_flow = {"mode": "History", "existing": True}
    app._lcd_show_results.reset_mock()
    App._lcd_start_history(app)
    assert app._lcd_flow["existing"] is True
    app._lcd_show_results.assert_called_once()

    # = on the results list recalls the raw expression/result pair; it
    # intentionally does not re-evaluate a historic operation.
    app._lcd_flow = {
        "mode": "History",
        "phase": "results",
        "history_entries": [("integral(x)", "custom result")],
        "result_index": 0,
    }
    app._reset_lcd_flow = mock.Mock()
    app.set_expr = mock.Mock()
    app._show_completed_result = mock.Mock()
    app._reset_history_browsing = mock.Mock()
    app._calculation_busy = False
    app._history_lcd_active = mock.Mock(return_value=True)
    app.consume = mock.Mock()
    App.equals(app)

    app._reset_lcd_flow.assert_called_once_with()
    app.set_expr.assert_called_once_with("integral(x)")
    app._show_completed_result.assert_called_once_with("custom result")
    app._reset_history_browsing.assert_called_once_with()
    app.consume.assert_called_once_with()


def test_history_recall_empty_state_and_history_position_fallback_are_safe() -> None:
    app = _app(flow={"mode": "History", "phase": "results", "history_entries": [], "result_index": 0})
    App._lcd_recall_history_entry(app)
    assert app.result.text.replace("\n", " ") == "History is empty"

    app._lcd_flow = None
    App._lcd_recall_history_entry(app)

    app._history_entries = mock.Mock(side_effect=TypeError("unavailable"))
    App._reset_history_browsing(app)
    assert app.history_pos == 0


def test_form_initialization_replaces_non_mapping_flow_and_clears_result_navigation() -> None:
    app = _app(flow="stale")
    app._completed_result_text = "previous"
    app._completed_result_offset = 4
    app._lcd_render_field = mock.Mock()

    App._lcd_begin_form(app, "Matrix", [{"key": "size", "label": "Size"}], "size")

    assert app._completed_result_text is None
    assert app._completed_result_offset == 0
    assert app._pre_equals_recall_available is False
    assert app._lcd_flow["phase"] == "form"
    assert app._lcd_flow["fields"] == [{"key": "size", "label": "Size"}]
    app._lcd_render_field.assert_called_once_with()

    # A normal existing flow is updated in place, preserving mode metadata.
    app._lcd_flow = {"mode": "Matrix", "values": {"old": 1}}
    app._lcd_render_field.reset_mock()
    App._lcd_begin_form(app, "Matrix", [{"key": "count"}], "count")
    assert app._lcd_flow["mode"] == "Matrix"
    assert app._lcd_flow["stage"] == "count"
    app._lcd_render_field.assert_called_once_with()


def test_removed_improper_integral_action_is_rejected() -> None:
    app = _app(
        flow={
            "mode": "Integral",
            "source_expression": "1/x",
            "values": {"calculus_action": "improper"},
        }
    )
    with pytest.raises(CalculatorError, match="unsupported calculus operation"):
        App._lcd_choose_calculus_action(app)


def test_scaled_rebuild_restores_full_result_and_scroll_offset_after_recreating_skin() -> None:
    app = _app()
    app.expr = _Entry("sin(x)", cursor=3)
    app._completed_result_text = "ABCDEFGHI"
    app._completed_result_offset = 2
    app.template_kind = None
    app.winfo_children = mock.Mock(return_value=[])
    app.resizable = mock.Mock()
    app.geometry = mock.Mock()
    app._ui = mock.Mock()
    app.set_expr = mock.Mock()
    app._show_completed_result = mock.Mock()
    app.status_refresh = mock.Mock()

    App._rebuild_scaled_ui(app)

    app.set_expr.assert_called_once_with("sin(x)")
    app._show_completed_result.assert_called_once_with("ABCDEFGHI", reset=False)
    assert app._completed_result_offset == 2
    assert app.resizable.call_args_list == [mock.call(True, True), mock.call(False, False)]


def test_browsing_past_an_integral_clears_its_template_from_the_lcd() -> None:
    """A previous entry's integral must not stay drawn over the next result.

    History renders a calculus entry through the template canvas. Moving to an
    entry that has no template used to leave that canvas in place, so the old
    integral sat above an unrelated result.
    """
    integral = CalculationHistoryEntry(
        "int", "2", "integral_single",
        {"integrand": "sin(x)/x", "variables": ["x"], "bounds": ({"lower": "0", "upper": "1"},)},
    )
    plain = CalculationHistoryEntry("5-1", "4")
    app = _app(flow={
        "mode": "History", "phase": "results",
        "result_lines": ["int = 2", "5-1 = 4"],
        "history_entries": [integral, plain],
        "result_index": 0,
    })
    app._hide_template_canvas = mock.Mock()
    app._show_completed_result = mock.Mock()
    app._render_history_integral_preview = mock.Mock(side_effect=lambda entry: entry is integral)

    App._lcd_render_result(app)
    app._hide_template_canvas.assert_not_called()

    app._lcd_flow["result_index"] = 1
    App._lcd_render_result(app)

    app._hide_template_canvas.assert_called_once_with()
