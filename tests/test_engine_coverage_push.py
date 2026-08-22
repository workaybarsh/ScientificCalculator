"""Focused behavioural coverage for calculator-engine safety boundaries.

The cases here exercise public calculator modes and the parser guards that
protect them.  They intentionally use real malformed or extreme inputs rather
than coverage-only stubs, so the checks remain useful release regressions.
"""
from __future__ import annotations

import ast
import math
import tokenize
from fractions import Fraction

import numpy as np
import pytest
import sympy as sp

import scientific_calculator.calculator_engine as engine_module
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine
from scientific_calculator.cas_worker import CASWorkerError


@pytest.fixture
def engine() -> ScientificCalculatorEngine:
    return ScientificCalculatorEngine(cas_isolated=False)


class _IntegerLike(sp.Atom):
    """A third-party exact numeric atom accepted by the parser's guards."""

    is_finite = True
    is_integer = True

    @property
    def free_symbols(self):
        return set()

    def __int__(self) -> int:
        return 7


class _BrokenInteger(sp.Atom):
    """An extension atom whose conversion failure must not escape the guard."""

    is_finite = True
    is_integer = True

    @property
    def free_symbols(self):
        return set()

    def __int__(self) -> int:
        raise ValueError("cannot convert")


class _BrokenFloat(float):
    """A numeric extension whose conversion may overflow at an API boundary."""

    def __float__(self) -> float:
        raise OverflowError("cannot convert")


class _BrokenFloatType(float):
    """A numeric extension with an invalid float conversion implementation."""

    def __float__(self) -> float:
        raise TypeError("cannot convert")


class _NonfiniteNumeric(sp.AtomicExpr):
    is_number = True

    @property
    def free_symbols(self):
        return set()

    def _eval_evalf(self, _precision: int):
        return sp.oo


class _HugeComplexNumeric(sp.AtomicExpr):
    is_number = True

    @property
    def free_symbols(self):
        return set()

    def _eval_evalf(self, _precision: int):
        return sp.Float("1e10000") + sp.I


class _BrokenComplexNumeric(sp.AtomicExpr):
    is_finite = None
    is_number = True
    is_real = False

    @property
    def free_symbols(self):
        return set()

    def __complex__(self) -> complex:
        raise OverflowError("cannot convert")


class _BrokenComplexTypeNumeric(sp.AtomicExpr):
    is_finite = None
    is_number = True
    is_real = False

    @property
    def free_symbols(self):
        return set()

    def __complex__(self) -> complex:
        raise TypeError("cannot convert")


def test_parser_budget_helpers_handle_valid_and_rejected_numeric_shapes() -> None:
    engine_module._require_exact_digit_budget(7, "unused")
    assert engine_module._estimated_factorial_digits(0) == 1
    assert engine_module._exact_nonnegative_integer(True) is None
    assert engine_module._exact_nonnegative_integer(sp.Rational(7, 2)) is None
    assert engine_module._exact_nonnegative_integer(_IntegerLike()) == 7
    assert engine_module._exact_nonnegative_integer(_BrokenInteger()) is None


def test_parser_numeric_helper_boundaries_are_fail_closed() -> None:
    """Numeric preflights accept ordinary calculator values but reject unsafe forms."""
    engine_module._preflight_power(Fraction(3, 5), -4)
    engine_module._preflight_power(3, 2)

    assert engine_module._constant_numeric_approx(ast.parse("Rational(1, 2)", mode="eval").body) == 0.5
    assert engine_module._constant_numeric_approx(ast.parse("factorial(3)", mode="eval").body) == 6.0
    assert engine_module._constant_numeric_approx(ast.parse("nPr(5, 2)", mode="eval").body) == 20.0
    assert engine_module._constant_numeric_approx(ast.parse("1 / 0", mode="eval").body) == math.inf
    assert engine_module._constant_numeric_approx(ast.parse("True", mode="eval").body) is None
    assert engine_module._constant_numeric_approx(ast.parse("'not-a-number'", mode="eval").body) is None
    assert engine_module._constant_numeric_approx(ast.parse("Rational(x, 1)", mode="eval").body) is None
    assert engine_module._constant_numeric_approx(ast.parse("nCr(-1, 2)", mode="eval").body) is None
    assert engine_module._evaluated_numeric_approx(sp.Function("f")()) is None

    with pytest.raises(CalculatorError, match="integer"):
        engine_module._finite_exact_integer(2.5, "integer")
    with pytest.raises(CalculatorError, match="integer"):
        engine_module._finite_exact_integer(sp.Rational(7, 2), "integer")


def test_numeric_preflights_handle_extension_conversion_and_overflow_safely() -> None:
    """Boundary helpers must contain invalid third-party numeric conversions."""
    with pytest.raises(CalculatorError, match="Math ERROR"):
        engine_module._preflight_power(2, 10**400)

    assert engine_module._constant_numeric_approx(ast.Constant(value=_BrokenFloatType(1))) is None
    assert engine_module._evaluated_numeric_approx(_BrokenFloat(1)) == math.inf
    assert engine_module._evaluated_numeric_approx(_NonfiniteNumeric()) == math.inf
    assert engine_module._evaluated_numeric_approx(_HugeComplexNumeric()) == math.inf
    assert engine_module._evaluated_numeric_approx(_BrokenComplexNumeric()) == math.inf
    assert engine_module._evaluated_numeric_approx(_BrokenComplexTypeNumeric()) is None


def test_parser_rejects_deep_or_malformed_syntax_before_evaluation(engine, monkeypatch) -> None:
    """Untrusted expressions cannot bypass the AST depth and lexer guards."""
    restricted = engine_module._RestrictedExpression({})
    deeply_nested = ast.parse("+".join("1" for _ in range(70)), mode="eval")
    with pytest.raises(CalculatorError, match="çok karmaşık"):
        restricted.validate(deeply_nested)

    with pytest.raises(CalculatorError, match="Geçersiz ifade"):
        engine.parse("1//2")
    assert engine.evaluate("((1))%") == pytest.approx(0.01)
    with pytest.raises(CalculatorError, match="metin"):
        engine.normalize(None)  # type: ignore[arg-type]

    def broken_tokens(_reader):
        raise tokenize.TokenError("unterminated", (1, 0))

    monkeypatch.setattr(engine_module.tokenize, "generate_tokens", broken_tokens)
    with pytest.raises(CalculatorError, match="Geçersiz ifade"):
        engine.parse("x")
    assert engine.equation_symbols("x+1=0") == ["x"]


def test_parser_normalizes_primitive_results_and_wraps_internal_parser_failures(engine, monkeypatch) -> None:
    """Parser integration defects cannot leak non-mathematical values to callers."""
    with monkeypatch.context() as patch:
        patch.setattr(engine_module._RestrictedExpression, "evaluate", lambda *_args: 4)
        assert engine.parse("1+3") == 4

    with monkeypatch.context() as patch:
        patch.setattr(engine_module._RestrictedExpression, "evaluate", lambda *_args: 4)
        patch.setattr(engine_module.sp, "sympify", lambda _value: object())
        with pytest.raises(CalculatorError, match="Matematiksel ifade"):
            engine.parse("1+3")

    with monkeypatch.context() as patch:
        patch.setattr(
            engine_module,
            "stringify_expr",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid transformed input")),
        )
        with pytest.raises(CalculatorError, match="Syntax ERROR"):
            engine.parse("1+3")


def test_equation_symbol_discovery_and_empty_batch_inputs_are_safe(engine) -> None:
    assert engine.equation_symbols("x=", adjacent_letters=[None]) == ["x"]
    with pytest.raises(CalculatorError, match="Syntax ERROR"):
        engine.evaluate("::")


def test_equation_root_validation_rejects_stationary_nonroot(engine, monkeypatch) -> None:
    """A backend answer is not accepted until its residual has been validated."""
    def fake_cas(operation: str, _payload: dict[str, object]):
        if operation == "nsolve":
            return sp.Integer(0)
        if operation == "differentiate_at_point":
            return sp.Integer(0)
        raise AssertionError(f"unexpected operation: {operation}")

    monkeypatch.setattr(engine, "_run_cas", fake_cas)
    with pytest.raises(CalculatorError, match="kök doğrulanamadı"):
        engine.solve("x+1=0", guess=0)


def test_numeric_derivative_reports_nonconvergence_and_unexpected_backend_failure(engine, monkeypatch) -> None:
    """The fallback differentiator has bounded convergence and clear failures."""
    monkeypatch.setattr(
        engine,
        "_run_cas",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CASWorkerError("unavailable")),
    )
    monkeypatch.setattr(
        engine_module.sp,
        "lambdify",
        lambda *_args, **_kwargs: lambda value: 0.0 if value == 0 else (1.0 if value > 0 else -1.0),
    )
    with pytest.raises(CalculatorError, match="yakınsamadı"):
        engine.derivative("x", "0", tol=1e-10)

    monkeypatch.setattr(
        engine_module.sp,
        "lambdify",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("backend unavailable")),
    )
    with pytest.raises(CalculatorError, match="derivative could not be evaluated"):
        engine.derivative("x", "0")


def test_numeric_derivative_falls_back_when_cas_returns_a_symbolic_value(engine, monkeypatch) -> None:
    """A non-numeric CAS answer falls through to the bounded numeric method."""
    marker = sp.Symbol("unresolved")

    def symbolic_cas(operation: str, _payload: dict[str, object]):
        if operation in {"differentiate_at_point", "simplify"}:
            return marker
        raise AssertionError(f"unexpected operation: {operation}")

    monkeypatch.setattr(engine, "_run_cas", symbolic_cas)
    assert engine.derivative("x^2", "2") == pytest.approx(4, rel=1e-7)


def test_auxiliary_numeric_modes_cover_nondefault_angle_complex_and_base_paths(engine) -> None:
    engine.settings.angle_unit = "GRA"
    assert engine.pol(0, 1) == pytest.approx((1, 100))
    assert engine.rec(1, 100) == pytest.approx((0, 1), abs=1e-12)
    assert engine.from_polar(1, 100) == pytest.approx(1j)

    engine.settings.angle_unit = "RAD"
    assert engine.from_polar(1, math.pi / 2) == pytest.approx(1j)
    assert engine._rad_to_angle(math.pi / 2) == math.pi / 2
    assert engine.pol(0, 1) == pytest.approx((1, math.pi / 2))
    assert engine.rec(1, math.pi / 2) == pytest.approx((0, 1), abs=1e-12)
    assert complex(engine.complex_eval("1+i")) == pytest.approx(complex(1, 1))
    assert sp.simplify(engine.ans - (1 + sp.I)) == 0

    engine.settings.angle_unit = "DEG"
    assert engine._rad_to_angle(sp.pi / 2) == 90
    assert engine.pol(0, 1) == pytest.approx((1, 90))
    assert engine.rec(1, 90) == pytest.approx((0, 1), abs=1e-12)
    assert engine.from_polar(1, 90) == pytest.approx(1j)

    assert engine.base_operation(1, 2, "or") == 3
    assert engine.format_base(10, 10) == "10"
    assert engine.format_base(10, 8) == "12"
    assert engine.format_base(10, 2) == "1010"
    with pytest.raises(CalculatorError, match="Syntax ERROR"):
        engine.evaluate_base(" ", 10)
    with pytest.raises(CalculatorError, match="Base-N"):
        engine.evaluate_base("1+", 10)


def test_matrix_and_vector_modes_reject_missing_nonfinite_and_overflowed_results(engine, monkeypatch) -> None:
    engine.define_matrix("MatA", [[1, -2], [3, -4]])
    np.testing.assert_allclose(engine.matrix_op("trn", "MatA"), [[1, 3], [-2, -4]])
    np.testing.assert_allclose(engine.matrix_op("square", "MatA"), [[-5, 6], [-9, 10]])
    np.testing.assert_allclose(engine.matrix_op("cube", "MatA"), [[13, -14], [21, -22]])
    np.testing.assert_allclose(engine.matrix_op("abs", "MatA"), [[1, 2], [3, 4]])
    with pytest.raises(CalculatorError, match="matris verileri"):
        engine.matrix_op("abs", [[math.nan]])
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.identity(0)

    monkeypatch.setattr(engine_module.np.linalg, "det", lambda _matrix: math.inf)
    with pytest.raises(CalculatorError, match="matris sonucu"):
        engine.matrix_op("det", "MatA")

    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.vector_op("abs", "VctA")
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.define_vector("VctA", [1])
    with pytest.raises(CalculatorError, match="vektör verisi"):
        engine.vector_op("abs", object())
    with pytest.raises(CalculatorError, match="vektör verileri"):
        engine.vector_op("abs", [math.nan, 0])
    with pytest.raises(CalculatorError, match="açısı"):
        engine.vector_op("angle", [1, 0], [math.nan, 0])
    with np.errstate(over="ignore"):
        with pytest.raises(CalculatorError, match="vektör sonucu"):
            engine.vector_op("dot", [1e308, 1e308], [1e308, 1e308])
        with pytest.raises(CalculatorError, match="vektör sonucu"):
            engine.vector_op("abs", [1e308, 1e308])
    with pytest.raises(CalculatorError, match="Math ERROR"):
        engine.vector_op("unit", [0, 0])

    monkeypatch.setattr(
        engine_module.np,
        "cross",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("backend failed")),
    )
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.vector_op("cross", [1, 0], [0, 1])


def test_statistics_and_regression_validate_empty_malformed_and_transformed_inputs(engine, monkeypatch) -> None:
    with pytest.raises(CalculatorError, match="veri yok"):
        engine.one_var_stats([])
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.one_var_stats([[1, 2]])
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.one_var_stats([1, 2], freq=[1])

    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.regression([1], [2])
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.regression([1, 2], [3, 4], "unsupported")
    with pytest.raises(CalculatorError, match="Math ERROR"):
        engine.regression([0, 1], [1, 2], "log")
    with pytest.raises(CalculatorError, match="Math ERROR"):
        engine.regression([0, 1], [1, 2], "inverse")
    with pytest.raises(CalculatorError, match="Math ERROR"):
        engine.regression([1, 2], [0, 2], "exp_e")
    with pytest.raises(CalculatorError, match="dönüştürülmüş"):
        engine.regression([1e-320, 1], [1, 2], "inverse")

    monkeypatch.setattr(engine_module.np, "polyfit", lambda *_args, **_kwargs: np.array([math.inf, 0.0]))
    with pytest.raises(CalculatorError, match="katsayıları"):
        engine.regression([1, 2], [3, 4])

    monkeypatch.setattr(
        engine_module.np,
        "polyfit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(np.linalg.LinAlgError("failed fit")),
    )
    with pytest.raises(CalculatorError, match="regresyon hesaplanamadı"):
        engine.regression([1, 2], [3, 4])

    monkeypatch.setattr(engine_module.np, "polyfit", lambda *_args, **_kwargs: np.array([0.0, 1000.0]))
    with np.errstate(over="ignore"), pytest.raises(CalculatorError, match="katsayıları"):
        engine.regression([1, 2], [3, 4], "exp_e")


def test_distribution_equation_and_formatting_boundaries_fail_safely(engine, monkeypatch) -> None:
    assert engine.normal_R(0) == pytest.approx(0.5)
    with pytest.raises(CalculatorError, match="ERROR"):
        engine.simultaneous([object()], [1])
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.inequality([object(), 1], ">")

    engine.settings.equation_complex = False
    assert engine.polynomial_roots([1, 0, 1]).size == 0
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.polynomial_roots([1, 2])

    monkeypatch.setattr(engine_module.stats.norm, "pdf", lambda *_args, **_kwargs: math.inf)
    with pytest.raises(CalculatorError, match="dağılım sonucu"):
        engine.distribution("Normal PD", x=0, mu=0, sigma=1)

    monkeypatch.setattr(
        engine_module.stats.norm,
        "pdf",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("backend unavailable")),
    )
    with pytest.raises(CalculatorError, match="Math ERROR"):
        engine.distribution("Normal PD", x=0, mu=0, sigma=1)

    with pytest.raises(CalculatorError, match="görüntüleme"):
        engine.format_result(math.inf)
    with pytest.raises(CalculatorError, match="görüntüleme"):
        engine.format_result(complex(math.inf, 1))
    hidden_zero_imag = sp.Add(sp.Integer(2), sp.Mul(sp.I, sp.Integer(0), evaluate=False), evaluate=False)
    assert hidden_zero_imag.has(sp.I)
    assert engine.format_result(hidden_zero_imag) == "2"
    unknown = object()
    assert engine.format_result(unknown) == str(unknown)


def test_numeric_display_formats_keep_unsigned_grouped_output(engine) -> None:
    """The compact formatter still covers normal, scientific, and small values."""
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 2
    engine.settings.digit_separator = True
    assert engine.format_result(1234.5) == "1,234.50"
    assert engine.format_result(-1234.5) == "-1,234.50"
    assert engine.format_result(5e-11, approximate=True) == "0.00000000005"

    engine.settings.number_format = "Sci"
    assert engine.format_result(1234.5) == "1.2e+03"
