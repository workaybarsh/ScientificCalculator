from __future__ import annotations

import math

import pytest
import sympy as sp

import scientific_calculator.calculus as calculus_module
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine() -> ScientificCalculatorEngine:
    return ScientificCalculatorEngine(cas_isolated=False)


def test_double_integral_supports_outer_dependent_inner_bounds_and_history(engine):
    result = engine.double_integral("x*y", "0", "1", "0", "x")

    assert result == pytest.approx(1 / 8)
    assert engine.history[-1] == ("∫0→1 ∫0→x x*y dy dx", "0.125")


def test_triple_integral_supports_nested_bounds(engine):
    result = engine.triple_integral("1", "0", "1", "0", "x", "0", "y")

    assert result == pytest.approx(1 / 6)
    assert engine.history[-1][0] == "∫0→1 ∫0→x ∫0→y 1 dz dy dx"


def test_double_integral_has_a_numeric_fallback(engine, monkeypatch):
    monkeypatch.setattr(engine, "_try_exact_nested_integral", lambda *_args: None)

    assert engine.double_integral("x+y", "0", "1", "0", "1") == pytest.approx(1.0)


def test_complex_double_integral_preserves_exact_complex_results_and_supports_numeric_fallback(engine, monkeypatch):
    exact = engine.complex_double_integral("i*x+y", "0", "1", "0", "1")

    assert exact == sp.Rational(1, 2) + sp.I / 2
    assert engine.history[-1] == ("∫0→1 ∫0→1 i*x+y dy dx", "1/2+1/2i")

    monkeypatch.setattr(engine, "_try_exact_nested_integral", lambda *_args, **_kwargs: None)
    numeric = engine.complex_double_integral("i*x+y", "0", "1", "0", "1")

    assert numeric == pytest.approx(0.5 + 0.5j)
    assert engine.history[-1][1] == "0.500+0.500i"


def test_complex_double_integral_supports_outer_dependent_inner_bounds(engine):
    assert engine.complex_double_integral("i", "0", "1", "0", "x") == sp.I / 2


def test_triple_integral_has_a_numeric_fallback(engine, monkeypatch):
    monkeypatch.setattr(engine, "_try_exact_nested_integral", lambda *_args: None)

    assert engine.triple_integral("x+y+z", "0", "1", "0", "1", "0", "1") == pytest.approx(1.5)


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("double_integral", ("x+y", "0", "inf", "0", "1")),
        ("double_integral", ("x+y", "0", "1", "0", "z")),
        ("triple_integral", ("x+y+z", "0", "1", "0", "1", "0", "inf")),
    ],
)
def test_multivariate_integrals_reject_nonfinite_or_out_of_scope_bounds(engine, method, args):
    with pytest.raises(CalculatorError):
        getattr(engine, method)(*args)


def test_scalar_and_vector_line_integrals_use_parameterized_paths(engine):
    scalar = engine.line_integral("x+y", "t", "t^2", "0", "1")
    vector = engine.vector_line_integral("y", "x", "t", "t^2", "0", "1")

    assert scalar == pytest.approx(1.454698971663726)
    assert vector == pytest.approx(1.0)
    assert engine.history[-1][0].startswith("∫C (y)dx+(x)dy")


def test_line_integral_rejects_a_path_with_an_unexpected_variable(engine):
    engine.memory["x"] = 42
    with pytest.raises(CalculatorError, match="yalnız parametre"):
        engine.line_integral("1", "x", "t", "0", "1")


def test_scalar_surface_integral_and_oriented_surface_flux(engine):
    surface = engine.surface_integral("1", "u", "v", "0", "0", "1", "0", "1")
    flux = engine.surface_flux_integral("0", "0", "1", "u", "v", "0", "0", "1", "0", "1")
    reverse_flux = engine.surface_flux_integral("0", "0", "1", "u", "v", "0", "0", "1", "0", "1", "u", "v", True)

    assert surface == pytest.approx(1.0)
    assert flux == pytest.approx(1.0)
    assert reverse_flux == pytest.approx(-1.0)
    assert "normal=reverse" in engine.history[-1][0]


def test_surface_integral_supports_a_curved_parameterization(engine):
    result = engine.surface_integral(
        "1", "sin(u)*cos(v)", "sin(u)*sin(v)", "cos(u)", "0", "pi", "0", "2*pi"
    )

    assert result == pytest.approx(4 * math.pi)
    assert engine.history[-1][0].startswith("∫∫S 1 dS")


def test_symbolic_integral_and_derivative_reject_invalid_variable_names(engine):
    with pytest.raises(CalculatorError, match="tek harf"):
        engine.symbolic_integral("x", "xy")
    with pytest.raises(CalculatorError, match="tek harf"):
        engine.symbolic_derivative("x", "xy")


def test_calculus_bound_and_symbol_helpers_reject_invalid_inputs(engine):
    with pytest.raises(CalculatorError, match="tek harf"):
        engine._validate_calculus_variable("xy")
    with pytest.raises(CalculatorError, match="metin"):
        engine._parse_integral_bound(1)
    with pytest.raises(CalculatorError, match="sayısal"):
        engine._parse_integral_bound("q")
    with pytest.raises(CalculatorError, match="sonlu"):
        engine._parse_finite_multivariate_bound("∞")
    with pytest.raises(CalculatorError, match="dış integral"):
        engine._parse_finite_multivariate_bound("q")

    locals_ = engine._calculus_symbol_locals({"t": sp.Symbol("t")})
    assert locals_["t"] == sp.Symbol("t")
    assert locals_["x"] == sp.Symbol("x")
    assert "e" not in locals_ and "i" not in locals_


def test_integral_segment_and_exact_helpers_handle_fallback_cases(engine, monkeypatch):
    x = sp.Symbol("x")
    monkeypatch.setattr(
        engine, "_run_cas", lambda *_args, **_kwargs: sp.FiniteSet(sp.Rational(1, 2), sp.oo)
    )
    segments, has_pole = engine._integral_segments(1 / (x - sp.Rational(1, 2)), x, sp.Integer(1), sp.Integer(0))
    assert has_pole is True
    assert segments == [(sp.Integer(1), sp.Rational(1, 2)), (sp.Rational(1, 2), sp.Integer(0))]

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("CAS down")))
    assert engine._integral_segments(x, x, sp.Integer(0), sp.Integer(1)) == ([(sp.Integer(0), sp.Integer(1))], False)
    assert engine._exact_integral_value(sp.Integral(x, x), allow_complex=False) is None
    with pytest.raises(CalculatorError, match="sayısal sonuç"):
        engine._exact_integral_value(x, allow_complex=False)
    assert engine._exact_integral_value(sp.I, allow_complex=True) == sp.I


def test_numeric_integral_validation_and_complex_path(engine, monkeypatch):
    x, y = sp.symbols("x y")
    with pytest.raises(CalculatorError, match="bilinmeyen"):
        engine._numeric_integral(x + y, x, [(sp.Integer(0), sp.Integer(1))], tol=1e-6, allow_complex=False)
    with pytest.raises(CalculatorError, match="toleransı"):
        engine._numeric_integral(x, x, [(sp.Integer(0), sp.Integer(1))], tol=0, allow_complex=False)
    assert engine._numeric_integral(sp.I * x, x, [(sp.Integer(0), sp.Integer(1))], tol=1e-8, allow_complex=True) == pytest.approx(0.5j)

    monkeypatch.setattr(calculus_module, "quad", lambda *_args, **_kwargs: (1.0, math.inf))
    with pytest.raises(CalculatorError, match="hata tahmini"):
        engine._numeric_integral(x, x, [(sp.Integer(0), sp.Integer(1))], tol=1e-8, allow_complex=False)


def test_multivariate_numeric_helper_errors_are_reported(engine, monkeypatch):
    x = sp.Symbol("x")
    callback = engine._numeric_real_callable(x, (x,), label="test")
    assert callback(2.0) == 2.0
    with pytest.raises(CalculatorError, match="geçersiz"):
        engine._finish_numeric_multivariate(1, -1)

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: sp.Integral(x, x))
    assert engine._try_exact_nested_integral(x, ((x, sp.Integer(0), sp.Integer(1)),)) is None
    with pytest.raises(CalculatorError, match="toleransı"):
        engine._numeric_double_integral(x, x, sp.Symbol("y"), sp.Integer(0), sp.Integer(1), sp.Integer(0), sp.Integer(1), tol=0)
    with pytest.raises(CalculatorError, match="toleransı"):
        engine._numeric_triple_integral(
            x, x, sp.Symbol("y"), sp.Symbol("z"),
            sp.Integer(0), sp.Integer(1), sp.Integer(0), sp.Integer(1), sp.Integer(0), sp.Integer(1), tol=0,
        )


def test_contour_and_transformation_errors_leave_history_unchanged(engine, monkeypatch):
    with pytest.raises(CalculatorError, match="farklı"):
        engine.contour_integral("z", "t", "0", "1", complex_variable="t", parameter="t")
    with pytest.raises(CalculatorError, match="sonlu"):
        engine.contour_integral("z", "t", "0", "inf")

    assert engine.contour_integral("1/z", "exp(i*t)", "0", "2*pi", "z", "t") == 2 * sp.pi * sp.I

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("CAS down")))
    with pytest.raises(CalculatorError, match="çizgisel integral hazırlanamadı"):
        engine.line_integral("1", "t", "t", "0", "1")
    with pytest.raises(CalculatorError, match="yüzey türevleri"):
        engine.surface_integral("1", "u", "v", "0", "0", "1", "0", "1")
