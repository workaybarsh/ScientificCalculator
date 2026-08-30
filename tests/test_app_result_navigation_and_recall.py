"""Result panning and expression recall around the equals boundary.

After a result is shown, arrows pan the completed value before they move the
entry cursor, and the pending expression is recalled ahead of stored history.
These tests hold that ordering, including its empty and edge states.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from scientific_calculator.app import App


class _Entry:
    """Minimal Entry double for explicit LCD interaction contracts."""

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.moves: list[int] = []

    def delete(self, _start: object, _end: object = None) -> None:
        self.text = ""

    def insert(self, _index: object, value: object) -> None:
        self.text = str(value)

    def get(self) -> str:
        return self.text

    def index(self, _index: object) -> int:
        return len(self.text)

    def icursor(self, index: int) -> None:
        self.moves.append(index)


class _Result:
    def __init__(self) -> None:
        self.text = ""

    def config(self, **options: object) -> None:
        self.text = str(options.get("text", self.text))


def test_differential_equation_opens_the_automatic_coefficient_template() -> None:
    app = object.__new__(App)
    app._lcd_flow = {"values": {"equation_kind": "ode"}}
    app.start_ode_template = mock.Mock()

    App._lcd_choose_equation_kind(app)

    app.start_ode_template.assert_called_once_with()


def test_set_expr_can_preserve_result_or_start_an_independent_edit() -> None:
    app = object.__new__(App)
    app._template_rendering = True
    app._lcd_flow = {"phase": "form", "field_armed": True}
    app.expr = _Entry("old")
    app._begin_independent_edit = mock.Mock()

    App.set_expr(app, "recalled", preserve_completed_result=True)

    assert app.expr.text == "recalled"
    assert app._lcd_flow["field_armed"] is False
    app._begin_independent_edit.assert_not_called()

    App.set_expr(app, "fresh")

    assert app.expr.text == "fresh"
    app._begin_independent_edit.assert_called_once_with()


def test_horizontal_move_pans_a_completed_result_before_moving_the_entry_cursor() -> None:
    app = object.__new__(App)
    app._lcd_flow = None
    app.template_kind = None
    app._completed_result_text = "abcdef"
    app._completed_result_offset = 0
    app._lcd_content_width = lambda: 3
    app._lcd_measure_text = len
    app.result = _Result()
    app.expr = _Entry("entry")

    App.move(app, 1)

    assert app._completed_result_offset > 0
    assert app.result.text != "abcdef"
    assert app.expr.moves == []


def test_up_after_equals_recalls_the_pending_expression_before_history() -> None:
    app = object.__new__(App)
    app._lcd_flow = None
    app.template_kind = None
    app._pre_equals_recall_available = True
    app._last_submitted_expression = "sin(x)"
    app.set_expr = mock.Mock()
    app._set_lcd_label = mock.Mock()
    app.history_move = mock.Mock()

    App.vertical_move(app, -1)

    app.set_expr.assert_called_once_with("sin(x)")
    app._set_lcd_label.assert_called_once_with("Edit recalled expression")
    assert app._pre_equals_recall_available is False
    app.history_move.assert_not_called()


def test_empty_pre_equals_snapshot_falls_through_to_history_navigation() -> None:
    app = object.__new__(App)
    app._lcd_flow = None
    app.template_kind = None
    app._pre_equals_recall_available = True
    app._last_submitted_expression = ""
    app.history_move = mock.Mock()

    App.vertical_move(app, -1)

    app.history_move.assert_called_once_with(-1)


def test_history_sentinel_handles_newest_recall_and_downward_edges() -> None:
    app = object.__new__(App)
    app.core = SimpleNamespace(history=[("old", "1"), ("new", "2")])
    app.history_pos = 2
    app.set_expr = mock.Mock()
    app._show_completed_result = mock.Mock()

    App.history_move(app, -1)

    assert app.history_pos == 1
    app.set_expr.assert_called_once_with("new")
    app._show_completed_result.assert_called_once_with("2")

    app.set_expr.reset_mock()
    app._show_completed_result.reset_mock()
    app.history_pos = 2
    App.history_move(app, 1)
    assert app.history_pos == 2
    app.set_expr.assert_not_called()

    app.history_pos = 1
    App.history_move(app, 1)
    assert app.history_pos == 2
    app.set_expr.assert_not_called()
    app._show_completed_result.assert_not_called()


def test_shift_optn_inserts_visible_infinity_without_opening_a_menu() -> None:
    app = object.__new__(App)
    app.shift = True
    app.insert = mock.Mock()
    app.consume = mock.Mock()

    App.optn_key(app)

    app.insert.assert_called_once_with("∞")
    app.consume.assert_called_once_with()
