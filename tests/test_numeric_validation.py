from __future__ import annotations

import math

import pytest
import sympy as sp

from scientific_calculator.calculator_engine import CalculatorError
from scientific_calculator.numeric_validation import finite_complex, finite_real_float, require_finite_math_result


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (sp.Rational(3, 2), 1.5),
        (complex(2, 0), 2.0),
        (4, 4.0),
    ],
)
def test_finite_real_float_accepts_concrete_real_values(value, expected):
    assert finite_real_float(value, "bad") == expected


@pytest.mark.parametrize("value", [sp.Symbol("x"), 1j, True, math.inf, "not-a-number"])
def test_finite_real_float_rejects_symbolic_complex_or_nonfinite_values(value):
    with pytest.raises(CalculatorError, match="bad"):
        finite_real_float(value, "bad")


def test_finite_complex_preserves_imaginary_component_and_rejects_nonfinite_values():
    assert finite_complex(sp.Integer(2) + sp.I, "bad") == complex(2, 1)
    for value in (sp.Symbol("z"), True, complex(math.inf, 0)):
        with pytest.raises(CalculatorError, match="bad"):
            finite_complex(value, "bad")


@pytest.mark.parametrize("value", [sp.oo, float("nan"), complex(0, math.inf)])
def test_require_finite_math_result_rejects_known_nonfinite_values(value):
    with pytest.raises(CalculatorError, match="bad"):
        require_finite_math_result(value, "bad")
