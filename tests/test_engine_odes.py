from __future__ import annotations

import pytest
import sympy as sp

from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine() -> ScientificCalculatorEngine:
    return ScientificCalculatorEngine(cas_isolated=False)


def test_solve_ode_accepts_keypad_first_order_notation_and_commits_a_readable_history(engine):
    engine.memory["x"] = sp.Integer(99)
    engine.memory["y"] = sp.Integer(42)

    result = engine.solve_ode("dy/dx=y")

    x = sp.Symbol("x")
    assert isinstance(result, sp.Equality)
    assert result.lhs == sp.Function("y")(x)
    assert sp.simplify(result.rhs / sp.exp(x)).name == "C1"
    assert engine.ans == result
    assert engine.history[-1] == ("ODE dy/dx=y; y(x)", "y(x) = C1*exp(x)")
    assert engine.format_result(result) == "y(x) = C1*exp(x)"


@pytest.mark.parametrize("equation", ["d2y/dx2+y=0", "y''+y=0"])
def test_solve_ode_solves_second_order_keypad_or_prime_notation_with_initial_data(engine, equation):
    result = engine.solve_ode(equation, initial_conditions={"x0": "0", "y0": "0", "dy0": "1"})

    x = sp.Symbol("x")
    assert result == sp.Eq(sp.Function("y")(x), sp.sin(x))
    assert "derivative=1" in engine.history[-1][0]


def test_solve_ode_accepts_custom_variables_and_compact_initial_condition_text(engine):
    result = engine.solve_ode("df/dt=f", "f", "t", "t0=0, f0=2")

    t = sp.Symbol("t")
    assert result.lhs == sp.Function("f")(t)
    assert sp.simplify(result.rhs - 2 * sp.exp(t)) == 0
    assert "point=0, value=2" in engine.history[-1][0]


def test_solve_ode_accepts_natural_initial_condition_keys(engine):
    result = engine.solve_ode("y'=y", initial_conditions={"y(0)": "1"})

    x = sp.Symbol("x")
    assert result == sp.Eq(sp.Function("y")(x), sp.exp(x))


def test_solve_ode_works_through_the_direct_engine_cas_boundary():
    result = ScientificCalculatorEngine(cas_timeout=10).solve_ode(
        "dy/dx=y", initial_conditions={"x0": "0", "y0": "1"},
    )

    x = sp.Symbol("x")
    assert result == sp.Eq(sp.Function("y")(x), sp.exp(x))


@pytest.mark.parametrize(
    ("equation", "conditions", "message"),
    [
        ("d3y/dx3=y", None, "birinci ve ikinci"),
        ("dy/dt=y", None, "bağımsız değişken"),
        ("y=x", None, "türev içermelidir"),
        ("dy/dx=ODEDERIVATIVETWO", None, "ayrılmış ifade"),
        ("dy/dx=y", {"x0": "0"}, "x0 ve y0"),
        ("dy/dx=y", {"x0": "0", "y0": "1", "dy0": "0"}, "birinci dereceden"),
        ("d2y/dx2+y=0", {"x0": "0", "y0": "1"}, "dy0"),
    ],
)
def test_solve_ode_rejects_unsupported_or_incomplete_input_without_committing(engine, equation, conditions, message):
    engine.ans = sp.Integer(7)
    engine.history = [("seed", "7")]

    with pytest.raises(CalculatorError, match=message):
        engine.solve_ode(equation, initial_conditions=conditions)

    assert engine.ans == 7
    assert engine.history == [("seed", "7")]


def test_solve_ode_translates_cas_failures_without_committing(engine, monkeypatch):
    engine.ans = sp.Integer(7)
    engine.history = [("seed", "7")]
    monkeypatch.setattr(engine, "_run_cas", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("CAS down")))

    with pytest.raises(CalculatorError, match="kapalı biçimde"):
        engine.solve_ode("dy/dx=y")

    assert engine.ans == 7
    assert engine.history == [("seed", "7")]
