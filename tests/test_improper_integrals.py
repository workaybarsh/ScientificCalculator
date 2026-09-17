"""Mathematical regression tests for the typed real improper-integral path."""
from __future__ import annotations

import pytest
import sympy as sp

from scientific_calculator.calculation_result import CalculationResult, ResultStatus
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine() -> ScientificCalculatorEngine:
    return ScientificCalculatorEngine(cas_isolated=False)


@pytest.mark.parametrize(
    ("expression", "lower", "upper", "expected"),
    [
        ("1/(sqrt(x)*(1+x))", "0", "inf", sp.pi),
        ("1/x^2", "1", "inf", sp.Integer(1)),
        ("1/(1+x^2)", "-inf", "inf", sp.pi),
        ("1/sqrt(1-x^2)", "-1", "1", sp.pi),
        ("1/sqrt(x-x^2)", "0", "1", sp.pi),
        ("sin(x)/x", "-inf", "inf", sp.pi),
        ("1/sqrt(abs(x))", "-1", "1", sp.Integer(4)),
    ],
)
def test_improper_integral_components_converge_independently(engine, expression, lower, upper, expected) -> None:
    result = engine.definite_integral_result(expression, lower, upper)

    assert result.status is ResultStatus.INTEGRAL_EXISTS
    assert result.metadata["kind"] == "improper"
    assert sp.simplify(result.value - expected) == 0
    assert result.exact_value == expected


@pytest.mark.parametrize(
    ("expression", "lower", "upper"),
    [
        ("1/x", "-1", "1"),
        ("x/(1+x^2)", "-inf", "inf"),
        ("tan(x)", "0", "pi"),
        ("1/x", "1", "inf"),
    ],
)
def test_principal_value_traps_are_semantic_divergences(engine, expression, lower, upper) -> None:
    result = engine.definite_integral_result(expression, lower, upper)

    assert result.status is ResultStatus.INTEGRAL_DIVERGES
    assert result.value is None
    assert engine.ans == 0
    assert engine.history == []


def test_real_domain_gap_is_not_silently_promoted_to_a_complex_integral(engine) -> None:
    result = engine.definite_integral_result("1/sqrt(x)", "-1", "1")

    assert result.status is ResultStatus.INTEGRAL_UNDEFINED
    assert result.metadata["reasons"] == ("outside_real_domain",)


def test_calculator_unicode_minus_in_infinite_bounds_is_accepted(engine) -> None:
    result = engine.definite_integral_result("sin(x)/x", "−∞", "∞", "x")

    assert result.status is ResultStatus.INTEGRAL_EXISTS
    assert sp.simplify(result.value - sp.pi) == 0


def test_calculus_uses_natural_logarithms_and_radian_trigonometry(engine) -> None:
    engine.settings.angle_unit = "DEG"

    logarithmic = engine.definite_integral_result("log(1+x^2)/x^2", "0", "inf", "x")
    trigonometric = engine.definite_integral_result("sin(x)", "0", "pi", "x")

    assert logarithmic.status is ResultStatus.INTEGRAL_EXISTS
    assert sp.simplify(logarithmic.value - sp.pi) == 0
    assert trigonometric.status is ResultStatus.INTEGRAL_EXISTS
    assert sp.simplify(trigonometric.value - 2) == 0


def test_integral_parser_accepts_allowlisted_exact_numeric_constructors(engine) -> None:
    result = engine.definite_integral_result("1/Abs(x-1)**Rational(2,3)", "0", "2", "x")

    assert result.status is ResultStatus.INTEGRAL_EXISTS
    assert result.metadata["kind"] == "improper"
    assert sp.simplify(result.value - 6) == 0


@pytest.mark.parametrize(
    ("expression", "lower", "upper", "expected_status", "expected_kind"),
    [
        ("x^2", "0", "1", ResultStatus.INTEGRAL_EXISTS, "proper"),
        # A finite removable endpoint is not an improper integral.
        ("sin(x)/x", "0", "1", ResultStatus.INTEGRAL_EXISTS, "proper"),
        # The supplied stress suite's two common genuinely improper shapes.
        ("1/(sqrt(x)*(1+x))", "0", "inf", ResultStatus.INTEGRAL_EXISTS, "improper"),
        ("1/Abs(x-1)**Rational(2,3)", "0", "2", ResultStatus.INTEGRAL_EXISTS, "improper"),
        # A principal-value candidate is still divergent as a standard integral.
        ("1/(x-1)", "0", "2", ResultStatus.INTEGRAL_DIVERGES, "improper"),
        # A real-domain gap takes precedence over an improper-integral route.
        ("1/sqrt(x)", "-1", "1", ResultStatus.INTEGRAL_UNDEFINED, "unknown"),
    ],
)
def test_integral_type_detection_routes_each_mathematical_case_safely(
    engine, expression, lower, upper, expected_status, expected_kind
) -> None:
    """Regression matrix for the routing decision, not merely the final value."""
    result = engine.definite_integral_result(expression, lower, upper)

    assert result.status is expected_status
    assert result.metadata["kind"] == expected_kind


@pytest.mark.parametrize(
    ("expression", "lower", "upper", "expected"),
    [("1/x^2", "inf", "1", -1), ("1/sqrt(x)", "1", "0", -2)],
)
def test_improper_orientation_is_preserved(engine, expression, lower, upper, expected) -> None:
    result = engine.definite_integral_result(expression, lower, upper)

    assert result.status is ResultStatus.INTEGRAL_EXISTS
    assert sp.simplify(result.value - expected) == 0


def test_failed_singularity_analysis_is_never_treated_as_a_proper_integral(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    original = engine._run_cas

    def fail_singularities(operation, payload):
        if operation == "singularities":
            raise RuntimeError("CAS unavailable")
        return original(operation, payload)

    monkeypatch.setattr(engine, "_run_cas", fail_singularities)

    result = engine.definite_integral_result("sin(x)", "0", "1")

    assert result.status is ResultStatus.INTEGRAL_UNDETERMINED
    assert result.metadata["analysis_complete"] is False


def test_improper_analysis_helper_conservatively_handles_reversed_and_nonfinite_sets(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    x = sp.Symbol("x")
    assert engine._integral_bound_float(sp.oo) == float("inf")
    assert engine._integral_bound_float(-sp.oo) == float("-inf")
    assert engine._improper_split_point(-sp.oo, sp.oo) == 0
    assert engine._improper_split_point(-sp.oo, sp.Integer(3)) == 2
    assert engine._improper_split_point(sp.Integer(3), sp.oo) == 4
    assert engine._improper_split_point(sp.Integer(2), sp.Integer(4)) == 3

    original = engine._run_cas
    monkeypatch.setattr(
        engine,
        "_run_cas",
        lambda operation, payload: sp.Interval(0, 1) if operation == "singularities" else original(operation, payload),
    )
    analysis = engine._analyze_integral_domain(x, x, sp.Integer(1), sp.Integer(0))
    assert analysis.kind.name == "UNKNOWN"


def test_improper_component_fallbacks_report_divergence_unknown_and_exact_value(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    x = sp.Symbol("x")

    divergence_calls = {"count": 0}

    def direct_failure_then_divergent(operation, _payload):
        if operation == "definite_integral":
            divergence_calls["count"] += 1
            if divergence_calls["count"] == 1:
                raise RuntimeError("no direct answer")
            return sp.Symbol("t")
        if operation == "limit":
            return sp.oo
        raise AssertionError(operation)

    monkeypatch.setattr(engine, "_run_cas", direct_failure_then_divergent)
    diverges = engine._evaluate_improper_component(x, x, sp.Integer(0), sp.oo, lower_problem=False, upper_problem=True)
    assert diverges.status is ResultStatus.INTEGRAL_DIVERGES

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    unknown = engine._evaluate_improper_component(x, x, sp.Integer(0), sp.oo, lower_problem=False, upper_problem=True)
    assert unknown.status is ResultStatus.INTEGRAL_UNDETERMINED

    calls = {"count": 0}

    def direct_failure_then_exact(operation, _payload):
        if operation == "definite_integral":
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("no direct answer")
            return sp.Symbol("t")
        if operation == "limit":
            return sp.Integer(2)
        raise AssertionError(operation)

    monkeypatch.setattr(engine, "_run_cas", direct_failure_then_exact)
    exists = engine._evaluate_improper_component(x, x, sp.Integer(0), sp.oo, lower_problem=False, upper_problem=True)
    assert exists.status is ResultStatus.INTEGRAL_EXISTS
    assert exists.value == 2

    finite_upper_limit_payloads: list[dict[str, object]] = []
    finite_upper_calls = {"count": 0}

    def finite_upper_fallback(operation, payload):
        if operation == "definite_integral":
            finite_upper_calls["count"] += 1
            if finite_upper_calls["count"] == 1:
                raise RuntimeError("force one-sided limit path")
            return sp.Symbol("t")
        if operation == "limit":
            finite_upper_limit_payloads.append(payload)
            return sp.Integer(2)
        raise AssertionError(operation)

    monkeypatch.setattr(engine, "_run_cas", finite_upper_fallback)
    finite_upper = engine._evaluate_improper_component(
        x, x, sp.Integer(0), sp.Integer(1), lower_problem=False, upper_problem=True
    )
    assert finite_upper.status is ResultStatus.INTEGRAL_EXISTS
    assert finite_upper_limit_payloads[0]["dir"] == "+"

    direct_divergence_calls = {"count": 0}

    def direct_oo_then_finite_limit(operation, _payload):
        if operation == "definite_integral":
            direct_divergence_calls["count"] += 1
            return sp.oo if direct_divergence_calls["count"] == 1 else sp.Symbol("t")
        if operation == "limit":
            return sp.Integer(3)
        raise AssertionError(operation)

    monkeypatch.setattr(engine, "_run_cas", direct_oo_then_finite_limit)
    recovered = engine._evaluate_improper_component(
        x, x, sp.Integer(0), sp.oo, lower_problem=False, upper_problem=True
    )
    assert recovered.status is ResultStatus.INTEGRAL_EXISTS
    assert recovered.value == 3


def test_certified_absolute_tail_numeric_fallback_is_explicitly_approximate(
    engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    x = sp.Symbol("x")
    cas_calls: list[dict[str, object]] = []

    def unresolved_integral_with_bounded_tail(operation, payload):
        if operation == "definite_integral":
            return sp.Integral(x, (x, payload["lower"], payload["upper"]))
        if operation == "limit":
            cas_calls.append(payload)
            return sp.Integer(0)
        raise AssertionError(operation)

    monkeypatch.setattr(engine, "_run_cas", unresolved_integral_with_bounded_tail)
    monkeypatch.setattr(engine, "_numeric_integral", lambda *_args, **_kwargs: 1.25)

    upper_tail = engine._evaluate_improper_component(
        x, x, sp.Integer(0), sp.oo, lower_problem=False, upper_problem=True
    )
    lower_tail = engine._certified_improper_numeric_fallback(
        x, x, -sp.oo, sp.Integer(0), lower_problem=True, upper_problem=False, tol=1e-9
    )
    finite_interval = engine._certified_improper_numeric_fallback(
        x, x, sp.Integer(0), sp.Integer(1), lower_problem=False, upper_problem=False, tol=1e-9
    )

    assert upper_tail.status is ResultStatus.INTEGRAL_EXISTS
    assert upper_tail.approx_value == 1.25
    assert upper_tail.exact_value is None
    assert lower_tail is not None
    assert lower_tail.approx_value == 1.25
    assert finite_interval is None
    assert not engine._has_absolute_tail_certificate(x, x, sp.Integer(0), sp.Integer(1))
    assert {payload["point"] for payload in cas_calls} == {sp.oo, -sp.oo}

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: sp.oo)
    assert not engine._has_absolute_tail_certificate(x, x, sp.Integer(0), sp.oo)

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("CAS down")))
    assert not engine._has_absolute_tail_certificate(x, x, sp.Integer(0), sp.oo)


def test_proper_integral_fallback_and_typed_unknown_paths(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    x = sp.Symbol("x")
    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(engine, "_numeric_integral", lambda *_args, **_kwargs: 0.5)
    result = engine._evaluate_proper_integral(x, x, sp.Integer(0), sp.Integer(1), tol=1e-9)
    assert result.approx_value == 0.5

    monkeypatch.setattr(engine, "_numeric_integral", lambda *_args, **_kwargs: (_ for _ in ()).throw(CalculatorError("bad")))
    unknown = engine._evaluate_proper_integral(x, x, sp.Integer(0), sp.Integer(1), tol=1e-9)
    assert unknown.status is ResultStatus.INTEGRAL_UNDETERMINED


def test_integral_analysis_failure_branches_remain_conservative(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    x = sp.Symbol("x")
    assert engine._is_finite_real_expression(object()) is False

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    assert engine._boundary_is_problematic(1 / x, x, sp.Integer(0), "+") is None
    analysis = engine._analyze_integral_domain(x, x, sp.Integer(0), sp.Integer(1))
    assert analysis.analysis_complete is False

    original = engine._run_cas
    monkeypatch.setattr(engine, "_run_cas", lambda operation, _payload: sp.Interval(0, 1) if operation == "singularities" else original(operation, _payload))
    nonfinite = engine._analyze_integral_domain(x, x, sp.Integer(0), sp.Integer(1))
    assert nonfinite.analysis_complete is False

    values = iter(((sp.I,), ()))
    monkeypatch.setattr(engine, "_finite_set_points", lambda _value: next(values))
    monkeypatch.setattr(engine, "_run_cas", lambda operation, payload: sp.S.Reals if operation == "continuous_domain" else sp.S.EmptySet)
    nonreal = engine._analyze_integral_domain(x, x, sp.Integer(0), sp.Integer(1))
    assert nonreal.analysis_complete is False

    monkeypatch.setattr(engine, "_finite_set_points", lambda _value: (sp.Rational(1, 2),) if _value != sp.S.Reals else ())
    monkeypatch.setattr(engine, "_boundary_is_problematic", lambda *_args: None)
    unknown_limit = engine._analyze_integral_domain(x, x, sp.Integer(0), sp.Integer(1))
    assert unknown_limit.analysis_complete is False

    monkeypatch.setattr(engine, "_finite_set_points", lambda _value: ())
    endpoint_unknown = engine._analyze_integral_domain(x, x, sp.Integer(0), sp.Integer(1))
    assert endpoint_unknown.analysis_complete is False


def test_improper_two_sided_and_legacy_complex_integral_fallback_branches(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    x = sp.Symbol("x")
    original = engine._evaluate_improper_component
    responses = iter((
        CalculationResult(ResultStatus.INTEGRAL_UNDETERMINED),
        CalculationResult(ResultStatus.INTEGRAL_UNDETERMINED),
    ))
    monkeypatch.setattr(
        engine,
        "_evaluate_improper_component",
        lambda *_args, **_kwargs: next(responses),
    )
    split_unknown = original(x, x, -sp.oo, sp.oo, lower_problem=True, upper_problem=True)
    assert split_unknown.status is ResultStatus.INTEGRAL_UNDETERMINED


def test_legacy_complex_integral_fallback_paths_are_still_guarded(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    x, q = sp.symbols("x q")
    with pytest.raises(CalculatorError):
        engine._definite_integral_expression(x + q, sp.Integer(0), sp.Integer(1), x, tol=1e-8, allow_complex=False)

    class BrokenExpression:
        def subs(self, *_args):
            raise RuntimeError("substitution failed")

    monkeypatch.setattr(engine, "_run_cas", lambda operation, _payload: sp.Integer(1) if operation == "limit" else sp.S.EmptySet)
    assert engine._boundary_is_problematic(BrokenExpression(), x, sp.Integer(0), "+") is False
    monkeypatch.setattr(engine, "_run_cas", lambda operation, _payload: sp.Limit(x, x, 0) if operation == "limit" else sp.S.EmptySet)
    assert engine._boundary_is_problematic(1 / x, x, sp.Integer(0), "+") is None

    unresolved = sp.Integral(x, (x, 0, 1))
    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: unresolved)
    monkeypatch.setattr(engine, "_numeric_integral", lambda *_args, **_kwargs: 0.5)
    numeric, approximate = engine._definite_integral_expression(x, sp.Integer(0), sp.Integer(1), x, tol=1e-8, allow_complex=False)
    assert (numeric, approximate) == (0.5, True)

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: sp.Integer(2))
    exact, approximate = engine._definite_integral_expression(x, sp.Integer(0), sp.Integer(1), x, tol=1e-8, allow_complex=False)
    assert (exact, approximate) == (2.0, True)

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: sp.Integer(2))
    monkeypatch.setattr(engine, "_numeric_integral", lambda *_args, **_kwargs: (_ for _ in ()).throw(CalculatorError("bad")))
    preserved, approximate = engine._definite_integral_expression(x, sp.Integer(0), sp.Integer(1), x, tol=1e-8, allow_complex=True)
    assert (preserved, approximate) == (sp.Integer(2), False)

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: unresolved)
    monkeypatch.setattr(engine, "_numeric_integral", lambda *_args, **_kwargs: 0.75)
    numeric, approximate = engine._definite_integral_expression(x, sp.Integer(0), sp.Integer(1), x, tol=1e-8, allow_complex=False)
    assert (numeric, approximate) == (0.75, True)

    monkeypatch.setattr(engine, "_integral_segments", lambda *_args: ([(sp.Integer(0), sp.Integer(1))], True))
    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(CalculatorError("bad exact")))
    with pytest.raises(CalculatorError, match="iç tekilliği"):
        engine._definite_integral_expression(x, sp.Integer(0), sp.Integer(1), x, tol=1e-8, allow_complex=False)

    monkeypatch.setattr(engine, "_integral_segments", lambda *_args: ([(sp.Integer(0), sp.Integer(1))], False))
    with pytest.raises(CalculatorError, match="bad exact"):
        engine._definite_integral_expression(x, sp.Integer(0), sp.Integer(1), x, tol=1e-8, allow_complex=False)

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("miss")))
    monkeypatch.setattr(engine, "_numeric_integral", lambda *_args, **_kwargs: (_ for _ in ()).throw(CalculatorError("bad numeric")))
    with pytest.raises(CalculatorError, match="bad numeric"):
        engine._definite_integral_expression(x, sp.Integer(0), sp.Integer(1), x, tol=1e-8, allow_complex=False)

    monkeypatch.setattr(engine, "_integral_segments", lambda *_args: ([(sp.Integer(0), sp.Integer(1))], True))
    with pytest.raises(CalculatorError, match="iç tekilliği"):
        engine._definite_integral_expression(x, sp.Integer(0), sp.Integer(1), x, tol=1e-8, allow_complex=False)
