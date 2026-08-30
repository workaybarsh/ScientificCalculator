from __future__ import annotations

import pytest
import sympy as sp

from scientific_calculator.calculation_result import CalculationResult, ResultStatus
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


def test_result_existence_distinguishes_mathematical_results_from_failures() -> None:
    assert CalculationResult(ResultStatus.LIMIT_EXISTS, 0).exists
    assert CalculationResult(ResultStatus.DERIVATIVE_EXISTS, 1).exists
    assert CalculationResult(ResultStatus.INTEGRAL_NO_ELEMENTARY_FORM).exists
    assert not CalculationResult(ResultStatus.LIMIT_DOES_NOT_EXIST).exists
    assert not CalculationResult(ResultStatus.TIMEOUT).exists


def test_complex_derivative_recognizes_holomorphic_functions_and_non_holomorphic_forms() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)
    z = sp.Symbol("z")

    square = engine.complex_derivative_result("z^2")
    assert square.status is ResultStatus.DERIVATIVE_EXISTS
    assert square.value == 2 * z
    assert square.metadata == {"holomorphic": True}
    assert engine.history[-1] == ("d/dz z^2", "2*z")

    assert engine.complex_derivative_result("exp(z)").value == sp.exp(z)
    assert engine.complex_derivative_result("sin(z)").value == sp.cos(z)
    reciprocal = engine.complex_derivative_result("1/z")
    assert reciprocal.status is ResultStatus.DERIVATIVE_EXISTS
    assert reciprocal.value == -1 / z**2

    for expression in ("conjugate(z)", "Abs(z)^2", "re(z)", "im(z)"):
        result = engine.complex_derivative_result(expression)
        assert result.status is ResultStatus.DERIVATIVE_DOES_NOT_EXIST
        assert result.metadata["holomorphic"] is False


def test_complex_derivative_checks_the_requested_point_and_undefined_points() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)

    at_zero = engine.complex_derivative_result("Abs(z)^2", point="0")
    assert at_zero.status is ResultStatus.DERIVATIVE_EXISTS
    assert at_zero.value == 0
    assert at_zero.metadata == {"point": 0}
    assert engine.history[-1] == ("d/dz Abs(z)^2 | z=0", "0")

    non_holomorphic = engine.complex_derivative_result("conjugate(z)", point="1+i")
    assert non_holomorphic.status is ResultStatus.DERIVATIVE_DOES_NOT_EXIST
    assert non_holomorphic.metadata["point"] == 1 + sp.I
    assert engine.history[-1][0] == "d/dz conjugate(z) | z=1+i"
    assert engine.history[-1][1] == "COMPLEX DERIVATIVE DOES NOT EXIST"

    undefined = engine.complex_derivative_result("1/z", point="0")
    assert undefined.status is ResultStatus.DERIVATIVE_UNDEFINED_AT_POINT


def test_complex_limit_checks_multiple_paths_and_reports_semantic_statuses() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)

    exists = engine.complex_limit_result("z^2", "0")
    assert exists.status is ResultStatus.LIMIT_EXISTS
    assert exists.value == 0

    no_limit = engine.complex_limit_result("conjugate(z)/z", "0")
    assert no_limit.status is ResultStatus.LIMIT_DOES_NOT_EXIST
    assert len(no_limit.metadata["paths"]) == 3

    undetermined = engine.complex_limit_result("sin(1/z)", "0")
    assert undetermined.status in {ResultStatus.LIMIT_DOES_NOT_EXIST, ResultStatus.LIMIT_UNDETERMINED}


def test_complex_limit_does_not_treat_three_agreeing_sample_paths_as_a_proof() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)
    expression = "(z/conjugate(z)-1)*(z/conjugate(z)+1)*(z/conjugate(z)-i)"

    result = engine.complex_limit_result(expression, "0")

    assert result.status is ResultStatus.LIMIT_UNDETERMINED


def test_complex_calculus_rejects_free_symbols_and_classifies_unavailable_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)

    with pytest.raises(CalculatorError):
        engine.complex_derivative_result("z+w")
    with pytest.raises(CalculatorError):
        engine.complex_derivative_result("z", point="a")
    with pytest.raises(CalculatorError):
        engine.complex_limit_result("z+w", "0")

    monkeypatch.setattr(sp, "limit", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("no path limit")))
    assert engine.complex_limit_result("z", "0").status is ResultStatus.LIMIT_UNDETERMINED


def test_complex_limit_rejects_direction_dependent_infinities_and_marks_indeterminate_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)

    result = engine.complex_limit_result("1/z", "0")
    assert result.status is ResultStatus.LIMIT_DOES_NOT_EXIST

    monkeypatch.setattr(sp, "limit", lambda *_args, **_kwargs: sp.zoo)
    assert engine.complex_limit_result("z", "0").status is ResultStatus.LIMIT_UNDETERMINED
