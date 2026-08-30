"""Engine operations reject invalid input without mutating state.

Evaluation, storage, memory arithmetic, and unit conversion each validate
before they commit, so a refused operation leaves Ans, memory, and history
exactly as they were.
"""
from __future__ import annotations

import math
from itertools import repeat
from types import MappingProxyType

import numpy as np
import pytest
import sympy as sp

import scientific_calculator.calculator_engine as engine_module
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine() -> ScientificCalculatorEngine:
    return ScientificCalculatorEngine(cas_isolated=False)


@pytest.mark.parametrize("source", ["", "1:", ":1", "1::2"])
def test_evaluate_rejects_empty_batch_segments_without_changing_state(engine, source):
    engine.ans = sp.Integer(7)
    engine.history = [("seed", "7")]

    with pytest.raises(CalculatorError, match="Empty batch expression"):
        engine.evaluate(source)

    assert engine.ans == 7
    assert engine.history == [("seed", "7")]


def test_bounded_iterable_covers_arrays_iterators_and_invalid_inputs():
    kwargs = {
        "maximum": 2,
        "invalid_message": "invalid",
        "limit_message": "limit",
    }
    array = np.array([1, 2])

    assert engine_module._bounded_iterable(array, **kwargs) is array
    assert engine_module._bounded_iterable((value for value in (1, 2)), **kwargs) == [1, 2]
    with pytest.raises(CalculatorError, match="invalid"):
        engine_module._bounded_iterable(np.array(1), **kwargs)
    with pytest.raises(CalculatorError, match="invalid"):
        engine_module._bounded_iterable(object(), **kwargs)
    with pytest.raises(CalculatorError, match="limit"):
        engine_module._bounded_iterable(repeat(1), **kwargs)
    with pytest.raises(CalculatorError, match="limit"):
        engine_module._bounded_iterable(np.arange(3), **kwargs)

    matrix = np.arange(4).reshape(2, 2)
    assert engine_module._bounded_iterable(matrix, array_maximum=4, **kwargs) is matrix
    with pytest.raises(CalculatorError, match="limit"):
        engine_module._bounded_iterable(np.arange(6).reshape(2, 3), array_maximum=4, **kwargs)


def test_collection_operations_bound_generators_and_keep_valid_four_by_four_systems(engine):
    np.testing.assert_allclose(engine.simultaneous(np.eye(4), [1, 2, 3, 4]), [1, 2, 3, 4])

    bounded_operations = [
        lambda: engine.one_var_stats(repeat(1)),
        lambda: engine.one_var_stats([1, 2], repeat(1)),
        lambda: engine.regression(repeat(1), [1, 2]),
        lambda: engine.regression([1, 2], repeat(1)),
        lambda: engine.polynomial_roots(repeat(1)),
        lambda: engine.inequality(repeat(1), ">"),
        lambda: engine.simultaneous(repeat([1, 0]), [1, 2]),
        lambda: engine.simultaneous([repeat(1)], [1]),
        lambda: engine.simultaneous(np.zeros((5, 5)), [1]),
        lambda: engine.simultaneous(np.eye(4), np.arange(5)),
    ]

    for operation in bounded_operations:
        with pytest.raises(CalculatorError, match="too many"):
            operation()


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, sp.I, sp.Symbol("q")])
def test_evaluate_with_values_rejects_nonfinite_or_nonreal_values_atomically(engine, value):
    engine.ans = sp.Integer(7)
    engine.memory["x"] = sp.Integer(9)
    engine.history = [("seed", "7")]

    with pytest.raises(CalculatorError, match="finite and real"):
        engine.evaluate_with_values("x+1", {"x": value})

    assert engine.ans == 7
    assert engine.memory["x"] == 9
    assert engine.history == [("seed", "7")]


def test_evaluate_with_values_accepts_mappings_and_validates_shape_before_state_changes(engine):
    assert float(engine.evaluate_with_values("x+1", MappingProxyType({"x": 2}))) == pytest.approx(3)
    assert float(engine.memory["x"]) == pytest.approx(2)
    assert float(engine.evaluate_with_values("z+1", {"z": 2})) == pytest.approx(3)

    engine.ans = sp.Integer(7)
    engine.memory["x"] = sp.Integer(9)
    engine.history = [("seed", "7")]
    too_many_values = {name: 1 for name in "abcdefghijklmnopqrstuvwxyzA"}
    for values, message in [
        ([], "mapping"),
        (too_many_values, "too many"),
        ({"xy": 1}, "single letters"),
        ({1: 1}, "single letters"),
    ]:
        with pytest.raises(CalculatorError, match=message):
            engine.evaluate_with_values("x+1", values)  # type: ignore[arg-type]
        assert engine.ans == 7
        assert engine.memory["x"] == 9
        assert engine.history == [("seed", "7")]


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, sp.oo, sp.zoo, sp.Symbol("q")])
def test_store_rejects_nonfinite_or_symbolic_values_without_mutation(engine, value):
    engine.memory["A"] = sp.Integer(9)

    with pytest.raises(CalculatorError, match="memory value must be finite"):
        engine.store("A", value)

    assert engine.memory["A"] == 9


def test_store_validates_ans_and_retains_finite_complex_values(engine):
    engine.memory["A"] = sp.Integer(9)
    engine.ans = sp.oo
    with pytest.raises(CalculatorError, match="memory value must be finite"):
        engine.store("A")
    assert engine.memory["A"] == 9

    engine.ans = object()  # type: ignore[assignment]
    with pytest.raises(CalculatorError, match="invalid memory value"):
        engine.store("A")
    assert engine.memory["A"] == 9

    assert sp.simplify(engine.store("A", 1 + 2j) - (1 + 2 * sp.I)) == 0


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, sp.oo, sp.zoo, sp.Symbol("q")])
def test_memory_arithmetic_rejects_invalid_ans_without_mutating_memory(engine, value):
    engine.memory["M"] = sp.Integer(9)
    engine.ans = value

    for operation in (engine.m_plus, engine.m_minus):
        with pytest.raises(CalculatorError, match="memory value must be finite"):
            operation()
        assert engine.memory["M"] == 9

    engine.ans = sp.Integer(2)
    assert float(engine.m_plus()) == pytest.approx(11)
    assert float(engine.m_minus()) == pytest.approx(9)


def test_memory_arithmetic_converts_unaddable_ans_to_a_calculator_error_atomically(engine):
    engine.memory["M"] = sp.Integer(9)
    engine.ans = object()  # type: ignore[assignment]

    for operation in (engine.m_plus, engine.m_minus):
        with pytest.raises(CalculatorError, match="invalid memory value"):
            operation()
        assert engine.memory["M"] == 9


def test_convert_rejects_nonfinite_inputs_converter_failures_and_nonfinite_results(engine, monkeypatch):
    for value in (math.nan, math.inf, -math.inf, True, sp.I):
        with pytest.raises(CalculatorError, match="conversion input"):
            engine.convert("cm→in", value)
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.convert(None, 1)  # type: ignore[arg-type]

    monkeypatch.setitem(engine_module.CONVERSIONS, "forced-overflow", lambda _value: (_ for _ in ()).throw(OverflowError()))
    monkeypatch.setitem(engine_module.CONVERSIONS, "forced-infinite", lambda _value: math.inf)
    assert engine.convert("cm→in", 2.54) == pytest.approx(1)
    with pytest.raises(CalculatorError, match="could not be completed"):
        engine.convert("forced-overflow", 1)
    with pytest.raises(CalculatorError, match="conversion result"):
        engine.convert("forced-infinite", 1)


def test_nested_unresolved_integrals_are_rejected_without_committing_state(engine, monkeypatch):
    x = sp.Symbol("x")
    nested = sp.Integer(1) + sp.Integral(sp.exp(-x**2), x)

    assert engine._has_unresolved_integral(nested)
    assert not engine._has_unresolved_integral(object())
    assert engine._exact_integral_value(nested, allow_complex=False) is None

    engine.ans = sp.Integer(7)
    engine.history = [("seed", "7")]
    monkeypatch.setattr(engine, "_run_cas", lambda operation, _payload: nested if operation == "indefinite_integral" else pytest.fail(operation))
    with pytest.raises(CalculatorError, match="kapalı biçimde"):
        engine.symbolic_integral("exp(-x^2)")
    assert engine.ans == 7
    assert engine.history == [("seed", "7")]

    monkeypatch.setattr(engine, "_run_cas", lambda operation, _payload: nested if operation == "definite_integral" else pytest.fail(operation))
    assert engine._try_exact_nested_integral(x, ((x, sp.Integer(0), sp.Integer(1)),)) is None


def test_symbolic_integral_rechecks_simplified_result_before_committing_state(engine, monkeypatch):
    x = sp.Symbol("x")
    nested = sp.Integer(1) + sp.Integral(sp.exp(-x**2), x)
    engine.ans = sp.Integer(7)
    engine.history = [("seed", "7")]

    def cas_result(operation, _payload):
        if operation == "indefinite_integral":
            return x
        if operation == "simplify":
            return nested
        pytest.fail(operation)

    monkeypatch.setattr(engine, "_run_cas", cas_result)
    with pytest.raises(CalculatorError, match="kapalı biçimde"):
        engine.symbolic_integral("x")
    assert engine.ans == 7
    assert engine.history == [("seed", "7")]


def test_complex_integrals_keep_a_verified_exact_result_when_scalar_quadrature_is_unavailable(engine, monkeypatch):
    engine.cas_isolated = False
    monkeypatch.setattr(
        engine,
        "_numeric_integral",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CalculatorError("numeric unavailable")),
    )
    assert engine.complex_definite_integral("i*z", "0", "1") == sp.I / 2


def test_complex_double_integral_keeps_a_verified_exact_result_when_quadrature_is_unavailable(engine, monkeypatch):
    engine.cas_isolated = False
    monkeypatch.setattr(
        engine,
        "_numeric_complex_double_integral",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CalculatorError("numeric unavailable")),
    )
    assert engine.complex_double_integral("i*x", "0", "1", "0", "1") == sp.I / 2


@pytest.mark.parametrize(
    ("equation", "message"),
    [
        ("∂y/∂x=0", "PDEs are not supported"),
        ("y(x,t)=0", "PDEs are not supported"),
        ("d2y/dxdy=0", "PDEs are not supported"),
        ("d2y/dx2+d2y/dt2=0", "PDEs are not supported"),
        ("d3y/dx2=0", "birinci ve ikinci"),
        ("d2y/dx3=0", "birinci ve ikinci"),
        ("d**3y/dx**3=0", "birinci ve ikinci"),
        ("d2y/dx2+(dy/dx)^2=0", "nonlinear second-order"),
        ("d2y/dx2+y^2=0", "nonlinear second-order"),
    ],
)
def test_ode_rejections_are_explicit_and_do_not_commit_state(engine, equation, message):
    engine.ans = sp.Integer(7)
    engine.history = [("seed", "7")]

    with pytest.raises(CalculatorError, match=message):
        engine.solve_ode(equation)

    assert engine.ans == 7
    assert engine.history == [("seed", "7")]


def test_ode_hardening_preserves_linear_second_order_and_nonlinear_first_order_support(engine):
    _, linear_order, _, _ = engine._parse_ode_equation("d2y/dx2+x*dy/dx+y=0", "y", "x")
    _, nonlinear_first_order, _, _ = engine._parse_ode_equation("dy/dx=y^2", "y", "x")

    assert linear_order == 2
    assert nonlinear_first_order == 1


def test_collection_conversion_errors_remain_calculator_errors_and_normal_p_is_available(engine):
    with pytest.raises(CalculatorError, match="geçersiz veri"):
        engine.one_var_stats(["not-a-number"])
    with pytest.raises(CalculatorError, match="geçersiz regresyon verisi"):
        engine.regression(["not-a-number"], [1])
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.polynomial_roots(["not-a-number", 0, 1])
    assert engine.normal_P(0) == pytest.approx(0.5)
