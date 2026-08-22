import math
import warnings

import pytest
import sympy as sp
from scipy.integrate import IntegrationWarning

import scientific_calculator.calculator_engine as engine_module
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine():
    return ScientificCalculatorEngine()


def test_calculate_precedence_product_division_ans_and_history(engine):
    assert engine.evaluate("6×7÷2") == 21
    assert engine.ans == 21
    assert engine.history[-1][0] == "6×7÷2"
    assert engine.evaluate("2+3:Ans*4") == 20
    assert len(engine.history) == 3


def test_calculate_implicit_multiplication(engine):
    assert engine.evaluate("2(3+4)+2pi") == 14 + 2 * sp.pi


@pytest.mark.parametrize("source", ["1/0", "0/0", "log(0)"])
def test_calculate_rejects_nonfinite_results_without_mutating_state(engine, source):
    engine.ans = sp.Integer(7)
    engine.history.append(("seed", "7"))
    with pytest.raises(CalculatorError, match="sonlu"):
        engine.evaluate(source)
    assert engine.ans == 7
    assert engine.history == [("seed", "7")]


def test_evaluate_with_values_rejects_nonfinite_before_memory_mutation(engine):
    engine.ans = sp.Integer(7)
    engine.memory["x"] = sp.Integer(9)
    with pytest.raises(CalculatorError):
        engine.evaluate_with_values("1/(x-x)", {"x": 2})
    assert engine.ans == 7
    assert engine.memory["x"] == 9


def test_finite_symbolic_and_complex_calculate_results_remain_supported(engine):
    symbolic = engine.evaluate("z+1")
    assert symbolic == sp.Symbol("z") + 1
    assert engine.evaluate("1+i") == 1 + sp.I


def test_large_exact_finite_integers_are_not_mistaken_for_machine_overflow(engine):
    assert engine.evaluate("10^400") == sp.Integer(10) ** 400
    assert engine.evaluate("2^10000") == sp.Integer(2) ** 10000


def test_exact_display_budget_rejects_oversized_integer_without_state_mutation(engine):
    oversized=sp.Integer(10) ** 5000
    with pytest.raises(CalculatorError, match="görüntüleme sınırını"):
        engine.format_result(oversized)

    engine.ans=sp.Integer(7)
    engine.history=[("seed","7")]
    with pytest.raises(CalculatorError, match="görüntüleme sınırını"):
        engine.evaluate("10^5000")
    assert engine.ans == 7
    assert engine.history == [("seed","7")]


def test_exact_display_budget_rejects_oversized_rational_without_string_conversion(engine):
    oversized=sp.Rational(1,sp.Integer(10) ** 5000 + 1)
    with pytest.raises(CalculatorError, match="görüntüleme sınırını"):
        engine.format_result(oversized)


def test_factorial_display_preflight_happens_before_constructing_the_integer(engine, monkeypatch):
    monkeypatch.setattr(engine_module.sp, "factorial", lambda _value: pytest.fail("factorial must not run"))

    with pytest.raises(CalculatorError, match="görüntüleme sınırını"):
        engine.evaluate("factorial(1600)")


@pytest.mark.parametrize("approximate", [False, True])
def test_decimal_output_rejects_machine_overflow_before_state_mutation(
    engine, approximate
):
    engine.settings.input_output="MathI/DecimalO"
    engine.ans=sp.Integer(7)
    engine.history=[("seed","7")]
    with pytest.raises(CalculatorError, match="görüntüleme aralığını"):
        engine.evaluate("10^5000",exact=not approximate)
    assert engine.ans == 7
    assert engine.history == [("seed","7")]


def test_equals_is_reserved_for_solve(engine):
    with pytest.raises(CalculatorError, match="SOLVE"):
        engine.evaluate("x=2")


def test_evaluate_with_values_supports_function_and_table_workflows(engine):
    assert float(engine.evaluate_with_values("2x+1", {"x": 3})) == pytest.approx(7)
    rows = [float(engine.parse("x^2+1", {"x": sp.Float(x)})) for x in (-2, 0, 2)]
    assert rows == pytest.approx([5, 1, 5])


def test_definite_and_symbolic_integrals(engine):
    assert engine.definite_integral("sin(x)", "0", "pi") == pytest.approx(2.0)
    assert engine.definite_integral("sinxcosx", "0", "pi") == pytest.approx(0.0, abs=1e-12)
    assert engine.history[-1] == ("∫0→pi sinxcosx dx", "0")
    x = sp.Symbol("x")
    assert sp.simplify(engine.symbolic_integral("2x") - x**2) == 0
    assert engine.history[-1] == ("∫ 2x dx", "x^2 + C")


def test_expression_with_unmatched_parentheses_has_a_clear_syntax_error(engine):
    with pytest.raises(CalculatorError, match="unmatched closing parenthesis"):
        engine.definite_integral("sin(x)cos(x))", "0", "pi")


@pytest.mark.parametrize("integrand", ["1e-13", "1e-15", "-1e-13", "5e-11"])
def test_definite_integral_preserves_small_nonzero_exact_results(engine, integrand):
    expected = float(integrand)
    assert engine.definite_integral(integrand, "0", "1") == pytest.approx(expected)


def test_numeric_integral_fallback_preserves_small_nonzero_result(engine, monkeypatch):
    monkeypatch.setattr(
        engine_module,
        "run_cas",
        lambda operation, payload: sp.Integral(payload["expression"], (payload["symbol"], payload["lower"], payload["upper"])),
    )
    monkeypatch.setattr(engine_module, "quad", lambda *args, **kwargs: (1e-13, 1e-16))
    assert engine.definite_integral("1e-13", "0", "1") == pytest.approx(1e-13)


def test_definite_integral_preserves_convergent_improper_and_skin_samples(engine):
    assert engine.definite_integral("1/sqrt(x)", "0", "1") == pytest.approx(2.0)
    assert engine.definite_integral(
        "(sin(x^2)*cos(x))/x", "0", "2*pi"
    ) == pytest.approx(0.53909701090742, rel=1e-10)


@pytest.mark.parametrize(
    ("expression", "lower", "upper"),
    [("1/x", "0", "1"), ("tan(x)", "0", "pi"), ("i*x", "0", "1")],
)
def test_definite_integral_rejects_divergent_or_complex_results(
    engine, expression, lower, upper
):
    with pytest.raises(CalculatorError):
        engine.definite_integral(expression, lower, upper)


def test_numeric_integral_fallback_rejects_interior_nonremovable_pole(
    engine, monkeypatch
):
    monkeypatch.setattr(
        engine_module,
        "run_cas",
        lambda operation, payload: sp.Integral(payload["expression"], (payload["symbol"], payload["lower"], payload["upper"])),
    )
    with pytest.raises(CalculatorError, match="tekilliği"):
        engine.definite_integral("1/(x-1/3)", "0", "1")


def test_numeric_integral_fallback_converts_integration_warning_to_error(
    engine, monkeypatch
):
    monkeypatch.setattr(
        engine_module,
        "run_cas",
        lambda operation, payload: sp.Integral(payload["expression"], (payload["symbol"], payload["lower"], payload["upper"])),
    )

    def warning_quad(*args, **kwargs):
        warnings.warn("forced warning", IntegrationWarning, stacklevel=2)
        return 0.0, 0.0

    monkeypatch.setattr(engine_module, "quad", warning_quad)
    with pytest.raises(CalculatorError):
        engine.definite_integral("x", "0", "1")


def test_numeric_and_symbolic_derivatives(engine):
    assert engine.derivative("x^3+2x", "2") == pytest.approx(14.0, rel=1e-6)
    x = sp.Symbol("x")
    result = engine.symbolic_derivative("x^3+2x")
    assert sp.expand(result) == 3 * x**2 + 2


def test_summation_budget_rejects_large_non_polynomial_before_worker(engine, monkeypatch):
    monkeypatch.setattr(engine_module, "run_cas", lambda *_args, **_kwargs: pytest.fail("worker must not run"))
    with pytest.raises(CalculatorError, match="hesaplama sınırını"):
        engine.summation("sin(x)", "1", str(engine_module._MAX_SUMMATION_TERMS + 1))


def test_cas_worker_failure_is_presented_as_calculator_error(engine, monkeypatch):
    monkeypatch.setattr(engine_module, "run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(engine_module.CASWorkerError("forced")))
    with pytest.raises(CalculatorError, match="sembolik integral"):
        engine.symbolic_integral("sin(x)")


@pytest.mark.parametrize("expression", ["1/x", "Abs(x)"])
def test_point_derivative_rejects_undefined_or_nonfinite_points(engine, expression):
    with pytest.raises(CalculatorError):
        engine.derivative(expression, "0")


def test_summation(engine):
    assert engine.summation("x^2", "1", "4") == 30
    with pytest.raises(CalculatorError):
        engine.summation("x", "1/2", "4")


def test_solve_equation_and_residual(engine):
    root, residual = engine.solve("x^2=2", variable="x", guess=1)
    assert root == pytest.approx(math.sqrt(2), rel=1e-12)
    assert residual == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("equation", ["1/x=0", "exp(x)=0"])
def test_solve_rejects_asymptotic_false_roots(engine, equation):
    with pytest.raises(CalculatorError, match="Cannot Solve"):
        engine.solve(equation, variable="x", guess=1)


def test_solve_with_known_values_and_missing_value_error(engine):
    root, residual = engine.solve(
        "A*x=B", variable="x", guess=0, known_values={"A": 4, "B": 10}
    )
    assert root == pytest.approx(2.5)
    assert residual == pytest.approx(0.0, abs=1e-12)
    with pytest.raises(CalculatorError, match="Bilinen değer"):
        engine.solve("A*x=B", variable="x", guess=0, known_values={"A": 4})


@pytest.mark.parametrize(
    ("equation", "known_values", "expected"),
    [
        ("Ax=B", {"A": 4, "B": 10}, 2.5),
        ("xy=6", {"y": 3}, 2.0),
    ],
)
def test_solve_discovers_approved_adjacent_single_letter_variables(
    engine, equation, known_values, expected
):
    root, residual = engine.solve(
        equation, variable="x", guess=1, known_values=known_values
    )
    assert root == pytest.approx(expected)
    assert residual == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("equation", ["xz=1", "GG=1"])
def test_solve_does_not_auto_create_unknown_adjacent_names(engine, equation):
    with pytest.raises(CalculatorError, match="Bilinmeyen ad"):
        engine.solve(equation, variable="x", guess=1)


def test_degree_angle_mode_is_preserved_for_numeric_calculate(engine):
    engine.settings.angle_unit = "DEG"
    assert float(engine.evaluate("sin(30)")) == pytest.approx(0.5)
    assert engine.derivative("sin(x)", "0") == pytest.approx(math.pi / 180, rel=1e-6)
