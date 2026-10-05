"""Regression tests for user-visible failure boundaries found in final review."""
from __future__ import annotations

import pytest
import sympy as sp

from scientific_calculator.calculator_engine import ScientificCalculatorEngine


def test_ode_text_conditions_keep_commas_inside_safe_function_arguments():
    """`log(8,2)` is one initial-value expression, not two conditions."""
    engine = ScientificCalculatorEngine(cas_isolated=False)

    result = engine.solve_ode("dy/dx=y", initial_conditions="x0=log(8,2), y0=1")

    x = sp.Symbol("x")
    assert sp.simplify(result.rhs - sp.exp(x - 3)) == 0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("x0=(1,2); y0=1,", ["x0=(1,2)", "y0=1"]),
        (",;", []),
        (")", [")"]),
    ],
)
def test_ode_condition_splitter_only_treats_top_level_delimiters_as_separators(text, expected):
    engine = ScientificCalculatorEngine(cas_isolated=False)

    assert engine._split_ode_initial_condition_entries(text) == expected
