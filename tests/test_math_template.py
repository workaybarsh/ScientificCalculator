from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scientific_calculator.math_template import MathTemplate, NavigationDirection, TemplateSlot


def test_linear_template_moves_only_between_real_slots_and_edits_active_value() -> None:
    template = MathTemplate.linear(("integrand", "lower", "upper", "variable"), values={"integrand": "x"})

    assert template.active_slot == "integrand"
    assert not template.move(NavigationDirection.LEFT)
    assert template.move(NavigationDirection.RIGHT)
    assert template.active_slot == "lower"
    template.set_active_value("0")
    assert template.backspace()
    assert template.active_value == ""
    assert template.backspace()
    assert template.active_slot == "integrand"
    assert template.active_value == "x"


def test_template_uses_explicit_vertical_geometry() -> None:
    template = MathTemplate(
        (
            TemplateSlot("integrand", down="lower"),
            TemplateSlot("lower", up="integrand", right="upper"),
            TemplateSlot("upper", left="lower"),
        ),
        active_slot="integrand",
    )

    assert template.move(NavigationDirection.DOWN)
    assert template.active_slot == "lower"
    assert template.move(NavigationDirection.RIGHT)
    assert template.active_slot == "upper"
    assert not template.move(NavigationDirection.DOWN)


@pytest.mark.parametrize(
    "slots, active_slot, values",
    [
        ((), "", {}),
        ((TemplateSlot("x"), TemplateSlot("x")), "x", {}),
        ((TemplateSlot("x"),), "missing", {}),
        ((TemplateSlot("x", right="missing"),), "x", {}),
        ((TemplateSlot("x"),), "x", {"missing": "1"}),
    ],
)
def test_template_rejects_invalid_graph_state(slots, active_slot, values) -> None:
    with pytest.raises(ValueError):
        MathTemplate(slots, active_slot, values)


@given(st.lists(st.sampled_from(list(NavigationDirection)), min_size=1, max_size=80))
def test_navigation_sequences_never_leave_the_declared_graph(directions: list[NavigationDirection]) -> None:
    template = MathTemplate(
        (
            TemplateSlot("integrand", right="lower", down="variable"),
            TemplateSlot("lower", left="integrand", right="upper"),
            TemplateSlot("upper", left="lower", down="variable"),
            TemplateSlot("variable", up="integrand"),
        ),
        active_slot="integrand",
    )

    for direction in directions:
        template.move(direction)
        assert template.active_slot in {"integrand", "lower", "upper", "variable"}
