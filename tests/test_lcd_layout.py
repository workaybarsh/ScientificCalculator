"""Behavioural tests for the widget-independent LCD layout primitives."""

from __future__ import annotations

import pytest

import scientific_calculator.lcd_layout as lcd_layout
from scientific_calculator.lcd_layout import normalize_label, result_viewport, scroll_result, wrap_label


def _variable_measure(text: str) -> int:
    """A deliberately non-monospaced stand-in for Tk font measurement."""
    widths = {"W": 5, "i": 1, " ": 1}
    return sum(widths.get(character, 2) for character in text)


def _monospace_measure(text: str) -> int:
    return len(text)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Differential\n\tEquation  ", "Differential Equation"),
        ("\n \t ", ""),
        (42, "42"),
    ],
)
def test_normalize_label_keeps_semantic_text_on_one_clean_line(raw: object, expected: str) -> None:
    assert normalize_label(raw) == expected


def test_wrap_label_uses_measured_width_not_character_count() -> None:
    # Seven characters fit inside a character-count limit of 16, but the
    # leading wide glyphs make the actual measured text too wide.
    rendered = wrap_label("WWW iii", 16, _variable_measure)

    assert rendered == "WWW\niii"
    assert "…" not in rendered
    assert rendered.replace("\n", " ") == "WWW iii"


@pytest.mark.parametrize(
    ("available_width", "max_lines", "expected"),
    [
        (100, 2, "Differential Equation"),
        (0, 2, "Differential Equation"),
        (-1, 2, "Differential Equation"),
        (5, 1, "Differential Equation"),
    ],
)
def test_wrap_label_leaves_labels_intact_when_wrapping_is_not_viable(
    available_width: int, max_lines: int, expected: str
) -> None:
    assert wrap_label("Differential Equation", available_width, _monospace_measure, max_lines=max_lines) == expected


def test_wrap_label_never_splits_or_ellipsizes_an_overwide_single_word() -> None:
    label = "Nonhomogeneous"

    rendered = wrap_label(label, 3, _monospace_measure)

    assert rendered == label
    assert "…" not in rendered


def test_wrap_label_handles_a_defensive_empty_word_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    """The final append guard remains safe for an unusual token provider."""

    class EmptyTokenLabel(str):
        def split(self, separator: str | None = None, maxsplit: int = -1) -> list[str]:
            assert separator == " "
            assert maxsplit == -1
            return [""]

    monkeypatch.setattr(lcd_layout, "normalize_label", lambda _text: EmptyTokenLabel("present"))

    assert wrap_label("ignored", 1, _monospace_measure) == ""


def test_result_viewport_uses_measured_width_and_preserves_full_text() -> None:
    viewport = result_viewport("WiWi", 0, 6, _variable_measure)

    assert viewport.full_text == "WiWi"
    assert viewport.text == "Wi"
    assert _variable_measure(viewport.text) <= 6
    assert not viewport.can_scroll_left
    assert viewport.can_scroll_right


def test_result_viewport_clamps_offsets_without_mutating_the_value() -> None:
    left = result_viewport("abcdef", -99, 3, _monospace_measure)
    right = result_viewport("abcdef", 999, 3, _monospace_measure)

    assert (left.offset, left.text, left.full_text) == (0, "abc", "abcdef")
    assert (right.offset, right.text, right.full_text) == (3, "def", "abcdef")
    assert right.can_scroll_left
    assert not right.can_scroll_right


def test_scroll_result_moves_one_step_and_clamps_at_both_ends_without_wrapping() -> None:
    text = "abcdef"
    current = result_viewport(text, 0, 3, _monospace_measure)
    offsets = [current.offset]
    for _ in range(10):
        current = scroll_result(text, current.offset, 1, 3, _monospace_measure)
        offsets.append(current.offset)
        assert current.full_text == text

    assert offsets == [0, 1, 2, 3, 3, 3, 3, 3, 3, 3, 3]
    assert current.text == "def"

    for _ in range(10):
        current = scroll_result(text, current.offset, -1, 3, _monospace_measure)
        assert current.full_text == text

    assert current.offset == 0
    assert current.text == "abc"


def test_scroll_result_with_zero_direction_keeps_the_existing_viewport() -> None:
    before = result_viewport("abcdef", 2, 3, _monospace_measure)
    after = scroll_result("abcdef", before.offset, 0, 3, _monospace_measure)

    assert after == before


def test_empty_and_zero_width_viewports_are_safe_and_keep_underlying_text() -> None:
    empty = result_viewport("", 99, 3, _monospace_measure)
    narrow = result_viewport("abc", 0, 0, _monospace_measure)
    after_scroll = scroll_result("abc", narrow.offset, 1, 0, _monospace_measure)

    assert (empty.full_text, empty.offset, empty.end, empty.text) == ("", 0, 0, "")
    assert narrow.full_text == "abc"
    # A transient zero-width widget is normalized to a one-glyph viewport so
    # that its state remains inspectable rather than becoming an empty screen.
    assert (narrow.offset, narrow.end, narrow.text) == (0, 1, "a")
    assert after_scroll.offset == 1
    assert after_scroll.full_text == "abc"


def test_visible_end_defensively_exposes_one_character_at_nonpositive_width() -> None:
    assert lcd_layout._visible_end("abc", 1, 0, _monospace_measure) == 2


def test_an_overwide_glyph_never_scrolls_into_an_empty_viewport() -> None:
    # A positive but smaller-than-one-glyph width is possible transiently while
    # Tk is laying out/rebuilding the scaled calculator.  It must still expose
    # the glyph and clamp at the final meaningful character, not at len(text).
    first = result_viewport("WW", 0, 1, _variable_measure)
    second = scroll_result("WW", first.offset, 1, 1, _variable_measure)
    final = scroll_result("WW", second.offset, 1, 1, _variable_measure)

    assert (first.offset, first.text) == (0, "W")
    assert (second.offset, second.text) == (1, "W")
    assert final == second
