"""Small, width-aware LCD layout primitives.

The calculator's LCD needs two deliberately separate behaviours: interface
labels may wrap so their meaning is not lost, while mathematical results must
remain one continuous value that can be inspected through a horizontal
viewport.  Keeping those rules free of Tk widgets makes their state and edge
cases straightforward to test.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

TextMeasure = Callable[[str], int]


def normalize_label(text: object) -> str:
    """Return a single-line semantic label without discarding any words."""
    return " ".join(str(text).replace("\n", " ").split())


def wrap_label(text: object, available_width: int, measure: TextMeasure, *, max_lines: int = 2) -> str:
    """Wrap a UI label by measured width instead of character count.

    Labels never receive an ellipsis here.  If a single word is wider than the
    available area it remains intact; callers can then supply a documented
    concise canonical label instead of silently changing its meaning.
    """
    label = normalize_label(text)
    if not label or available_width <= 0 or max_lines < 2 or measure(label) <= available_width:
        return label

    words = label.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if current and measure(candidate) > available_width and len(lines) < max_lines - 1:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return "\n".join(lines)


def _last_view_offset(text: str, available_width: int, measure: TextMeasure) -> int:
    """Find the earliest character position that reveals the complete suffix."""
    if not text:
        return 0
    start = len(text)
    while start > 0 and measure(text[start - 1 :]) <= available_width:
        start -= 1
    # A very wide glyph still needs a non-empty final viewport.  In that case
    # the complete suffix cannot fit, so reveal its final glyph instead.
    return len(text) - 1 if start == len(text) else start


def _visible_end(text: str, offset: int, available_width: int, measure: TextMeasure) -> int:
    """Return the exclusive endpoint of the largest measured viewport slice."""
    if offset >= len(text):
        return offset
    if available_width <= 0:
        return offset + 1
    end = offset
    while end < len(text) and measure(text[offset : end + 1]) <= available_width:
        end += 1
    # A glyph wider than a pathological display width is still shown rather
    # than producing an empty viewport.
    return end if end > offset else offset + 1


@dataclass(frozen=True)
class ResultViewport:
    """The visible portion of a complete, immutable result string."""

    full_text: str
    offset: int
    end: int

    @property
    def text(self) -> str:
        return self.full_text[self.offset : self.end]

    @property
    def can_scroll_left(self) -> bool:
        return self.offset > 0

    @property
    def can_scroll_right(self) -> bool:
        return self.end < len(self.full_text)


def result_viewport(text: object, offset: int, available_width: int, measure: TextMeasure) -> ResultViewport:
    """Create a clamped, full-text-preserving horizontal result viewport."""
    full_text = str(text)
    usable_width=max(1,int(available_width))
    last = _last_view_offset(full_text, usable_width, measure)
    clamped = max(0, min(int(offset), last))
    return ResultViewport(full_text, clamped, _visible_end(full_text, clamped, usable_width, measure))


def scroll_result(text: object, offset: int, direction: int, available_width: int, measure: TextMeasure) -> ResultViewport:
    """Move a result viewport one readable character step without wrapping."""
    current = result_viewport(text, offset, available_width, measure)
    if direction < 0:
        target = current.offset - 1
    elif direction > 0:
        target = current.offset + 1
    else:
        target = current.offset
    return result_viewport(current.full_text, target, available_width, measure)


def caret_text_view(
    text: object, cursor: int, available_width: int | None, measure: TextMeasure, empty_placeholder: str = "□"
) -> tuple[str, int]:
    """Return a one-line slice of *text* that keeps the caret visible.

    Used by constrained template slots, which reserve a fixed pixel budget.
    That budget is measured against a font the host may not have, so the view
    must stay correct when a substituted font is wider than the layout assumed.
    """
    text = str(text) if text else ""
    cursor = max(0, min(len(text), cursor))
    if not text:
        return empty_placeholder, 0
    if available_width is None or measure(text) <= available_width:
        return text, measure(text[:cursor])

    ellipsis = "…"
    # Keep the caret just to the right of centre where possible, then use the
    # remaining width for the expression after it.
    start = 0
    before_budget = max(1, int(available_width * 0.55))
    while start < cursor and measure((ellipsis if start else "") + text[start:cursor]) > before_budget:
        start += 1
    end = len(text)

    def display_width() -> int:
        return measure((ellipsis if start else "") + text[start:end] + (ellipsis if end < len(text) else ""))

    while end > cursor and display_width() > available_width:
        end -= 1
    while start < cursor and display_width() > available_width:
        start += 1
    # A budget too narrow for even one glyph must still show a character. Both
    # loops can meet, leaving an ellipsis that hides the value entirely.
    if end <= start:
        start = min(cursor, len(text) - 1)
        end = start + 1
    prefix = ellipsis if start else ""
    suffix = ellipsis if end < len(text) else ""
    return prefix + text[start:end] + suffix, measure(prefix + text[start:cursor])
