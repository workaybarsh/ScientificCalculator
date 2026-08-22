"""Focused behavioural coverage for the calculus mixin's guarded paths.

These tests intentionally use the engine's public operations wherever
possible.  The small number of helper checks exercise explicit numerical
adapter boundaries (SciPy/lambdify/CAS failures) that a user can encounter
through those operations, without adding coverage exclusions or changing
production behaviour.
"""
from __future__ import annotations

import math
import warnings

import pytest
import sympy as sp

import scientific_calculator.calculus as calculus_module
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine() -> ScientificCalculatorEngine:
    return ScientificCalculatorEngine(cas_isolated=False)


def test_definite_integral_recovers_from_a_symbolic_worker_failure(engine, monkeypatch):
    """A CAS miss must safely fall back to the bounded numerical evaluator."""
    original_run_cas = engine._run_cas

    def fail_only_exact_integrals(operation, payload):
        if operation == "definite_integral":
            raise RuntimeError("symbolic backend unavailable")
        return original_run_cas(operation, payload)

    monkeypatch.setattr(engine, "_run_cas", fail_only_exact_integrals)

    assert engine.definite_integral("x", "0", "1") == pytest.approx(0.5)


@pytest.mark.parametrize(
    "operation",
    [
        lambda engine: engine.definite_integral("x+q", "0", "1"),
        lambda engine: engine.double_integral("x+q", "0", "1", "0", "1"),
        lambda engine: engine.complex_double_integral("x+q", "0", "1", "0", "1"),
        lambda engine: engine.triple_integral("x+y+q", "0", "1", "0", "1", "0", "1"),
        lambda engine: engine.line_integral("q", "t", "0", "0", "1"),
        lambda engine: engine.vector_line_integral("q", "x", "t", "0", "0", "1"),
        lambda engine: engine.surface_integral("q", "u", "v", "0", "0", "1", "0", "1"),
        lambda engine: engine.surface_flux_integral("q", "0", "0", "u", "v", "0", "0", "1", "0", "1"),
    ],
)
def test_public_integral_operations_reject_out_of_scope_symbols(engine, operation):
    with pytest.raises(CalculatorError):
        operation(engine)


def test_integral_parameter_validation_covers_distinct_variables_bounds_and_orientation(engine):
    with pytest.raises(CalculatorError):
        engine.double_integral("x+y", "0", "1", "0", "1", "x", "x")
    with pytest.raises(CalculatorError):
        engine.double_integral("x+y", 0, "1", "0", "1")
    with pytest.raises(CalculatorError):
        engine.double_integral("x+y", "0", "1/0", "0", "1")
    with pytest.raises(CalculatorError):
        engine.surface_flux_integral(
            "0", "0", "1", "u", "v", "0", "0", "1", "0", "1", reverse_orientation="up"
        )


def test_contour_integral_validates_the_path_scope_and_translates_setup_failure(engine, monkeypatch):
    with pytest.raises(CalculatorError):
        engine.contour_integral("w", "t", "0", "1")

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(CalculatorError):
        engine.contour_integral("z", "t", "0", "1")


@pytest.mark.parametrize(
    "operation",
    [
        lambda engine: engine.double_integral("x+y", "0", "1", "0", "1", tol="bad"),
        lambda engine: engine.complex_double_integral("i*x+y", "0", "1", "0", "1", tol=math.inf),
        lambda engine: engine.triple_integral("x+y+z", "0", "1", "0", "1", "0", "1", tol="bad"),
    ],
)
def test_numeric_multivariate_fallback_rejects_invalid_tolerances(engine, monkeypatch, operation):
    monkeypatch.setattr(engine, "_try_exact_nested_integral", lambda *_args, **_kwargs: None)

    with pytest.raises(CalculatorError):
        operation(engine)


def test_public_multivariate_integrals_translate_numeric_backend_failures(engine, monkeypatch):
    monkeypatch.setattr(engine, "_try_exact_nested_integral", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calculus_module, "dblquad", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")))

    with pytest.raises(CalculatorError):
        engine.double_integral("x+y", "0", "1", "0", "1")
    with pytest.raises(CalculatorError):
        engine.complex_double_integral("i*x+y", "0", "1", "0", "1")


def test_public_triple_integral_translates_numeric_backend_failures(engine, monkeypatch):
    monkeypatch.setattr(engine, "_try_exact_nested_integral", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calculus_module, "tplquad", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")))

    with pytest.raises(CalculatorError):
        engine.triple_integral("x+y+z", "0", "1", "0", "1", "0", "1")


def test_numeric_adapter_errors_are_raised_as_calculator_errors(engine, monkeypatch):
    x = sp.Symbol("x")
    real = engine._numeric_real_callable(sp.sqrt(x), (x,), label="integrand")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(CalculatorError):
            real(-1.0)

    monkeypatch.setattr(calculus_module.sp, "lambdify", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad adapter")))
    with pytest.raises(CalculatorError):
        engine._numeric_complex_callable(x, (x,), label="integrand")


def test_numeric_adapter_wraps_construction_and_callback_failures(engine, monkeypatch):
    x = sp.Symbol("x")

    monkeypatch.setattr(
        calculus_module.sp, "lambdify", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad adapter"))
    )
    with pytest.raises(CalculatorError):
        engine._numeric_real_callable(x, (x,), label="integrand")

    monkeypatch.setattr(
        calculus_module.sp, "lambdify", lambda *_args, **_kwargs: (lambda *_values: (_ for _ in ()).throw(RuntimeError("bad value")))
    )
    real = engine._numeric_real_callable(x, (x,), label="integrand")
    complex_ = engine._numeric_complex_callable(x, (x,), label="integrand")
    with pytest.raises(CalculatorError):
        real(0.0)
    with pytest.raises(CalculatorError):
        complex_(0.0)


def test_numeric_helpers_handle_conversion_and_calculator_error_boundaries(engine, monkeypatch):
    x, y, z = sp.symbols("x y z")
    with pytest.raises(CalculatorError):
        engine._numeric_integral(x, x, [(sp.Integer(0), sp.Integer(1))], tol="bad", allow_complex=False)

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")))
    assert engine._try_exact_nested_integral(x, ((x, sp.Integer(0), sp.Integer(1)),)) is None

    monkeypatch.setattr(
        calculus_module, "dblquad", lambda callback, *_args, **_kwargs: (callback(0.0, 0.0), 0.0)
    )
    with pytest.raises(CalculatorError):
        engine._numeric_double_integral(1 / (x - y), x, y, sp.Integer(0), sp.Integer(1), sp.Integer(0), sp.Integer(1), tol=1e-8)
    with pytest.raises(CalculatorError):
        engine._numeric_complex_double_integral(
            1 / (x - y), x, y, sp.Integer(0), sp.Integer(1), sp.Integer(0), sp.Integer(1), tol=1e-8
        )
    with pytest.raises(CalculatorError):
        engine._numeric_complex_double_integral(
            1 / (x - y), x, y, sp.Integer(0), sp.Integer(1), sp.Integer(0), sp.Integer(1), tol="bad"
        )

    monkeypatch.setattr(
        calculus_module, "tplquad", lambda callback, *_args, **_kwargs: (callback(0.0, 0.0, 0.0), 0.0)
    )
    with pytest.raises(CalculatorError):
        engine._numeric_triple_integral(
            1 / (x - y), x, y, z,
            sp.Integer(0), sp.Integer(1), sp.Integer(0), sp.Integer(1), sp.Integer(0), sp.Integer(1), tol=1e-8,
        )


def test_complex_numeric_integral_rejects_nonfinite_error_estimates(engine, monkeypatch):
    x = sp.Symbol("x")
    monkeypatch.setattr(calculus_module, "quad", lambda *_args, **_kwargs: (1.0, math.inf))

    with pytest.raises(CalculatorError):
        engine._numeric_integral(sp.I * x, x, [(sp.Integer(0), sp.Integer(1))], tol=1e-8, allow_complex=True)

    nonfinite = engine._numeric_complex_callable(sp.oo, (), label="integrand")
    with pytest.raises(CalculatorError):
        nonfinite()


def test_vector_line_integral_translates_a_symbolic_transformation_failure(engine, monkeypatch):
    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("down")))

    with pytest.raises(CalculatorError):
        engine.vector_line_integral("y", "x", "t", "0", "0", "1")


def test_surface_parameterization_rejects_symbols_outside_its_selected_coordinates(engine):
    with pytest.raises(CalculatorError):
        engine.surface_integral("1", "q", "v", "0", "0", "1", "0", "1")


@pytest.mark.parametrize(
    ("equation", "dependent", "independent"),
    [
        ("dy/dx=y", "y", "y"),
        ("dy/dx=y", "e", "x"),
        ("y'''=y", "y", "x"),
        ("dy/dx=y=x", "y", "x"),
        ("dy/dx=", "y", "x"),
        ("=dy/dx", "y", "x"),
        ("dy/dx=dy/dx", "y", "x"),
    ],
)
def test_public_ode_validation_rejects_invalid_variable_and_equation_shapes(engine, equation, dependent, independent):
    with pytest.raises(CalculatorError):
        engine.solve_ode(equation, dependent, independent)


def test_ode_without_an_equals_sign_is_solved_as_an_equation_to_zero(engine):
    x = sp.Symbol("x")

    result = engine.solve_ode("dy/dx-y")

    assert result.lhs == sp.Function("y")(x)
    assert sp.simplify(result.rhs / sp.exp(x)).name == "C1"


def test_ode_initial_conditions_accept_numeric_and_natural_keys(engine):
    x = sp.Symbol("x")
    y = sp.Function("y")(x)

    numeric = engine.solve_ode("d2y/dx2+y=0", initial_conditions={"x0": 0, "y0": 0, "dy0": 1})
    natural = engine.solve_ode(
        "d2y/dx2+y=0", initial_conditions={"x0": "0", "y(0)": "0", "y'(0)": "1"}
    )

    assert numeric == sp.Eq(y, sp.sin(x))
    assert natural == sp.Eq(y, sp.sin(x))


@pytest.mark.parametrize(
    "conditions",
    [
        {1: "0", "y0": "1"},
        {"x0": False, "y0": "1"},
        {"x0": [], "y0": "1"},
        "x0",
        [],
        "x0=0,x0=0,y0=1",
        {"x0": "1", "y(0)": "1"},
        {"x0": "0", "y0": "x"},
        {"not-a-condition": "0", "y0": "1"},
        {"x0": "1/0", "y0": "1"},
    ],
)
def test_public_ode_initial_condition_validation_rejects_unsafe_or_incomplete_values(engine, conditions):
    with pytest.raises(CalculatorError):
        engine.solve_ode("dy/dx=y", initial_conditions=conditions)


def test_ode_worker_result_contract_requires_one_closed_equality(engine, monkeypatch):
    x = sp.Symbol("x")
    expected = sp.Eq(sp.Function("y")(x), sp.exp(x))

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: [])
    with pytest.raises(CalculatorError):
        engine.solve_ode("dy/dx=y")

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: [expected])
    assert engine.solve_ode("dy/dx=y") == expected

    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: sp.Integer(1))
    with pytest.raises(CalculatorError):
        engine.solve_ode("dy/dx=y")


@pytest.mark.parametrize("foreign_or_high_order", ["foreign", "third"])
def test_ode_parser_defensively_rejects_unapproved_or_high_order_derivatives(engine, monkeypatch, foreign_or_high_order):
    x = sp.Symbol("x")
    y = sp.Function("y")(x)
    if foreign_or_high_order == "foreign":
        parsed = iter((sp.diff(sp.Function("f")(x), x), sp.Integer(0)))
    else:
        parsed = iter((sp.diff(y, x, 3), sp.Integer(0)))
    monkeypatch.setattr(engine, "_safe_parse", lambda *_args, **_kwargs: next(parsed))

    with pytest.raises(CalculatorError):
        engine._parse_ode_equation("dy/dx=0", "y", "x")
