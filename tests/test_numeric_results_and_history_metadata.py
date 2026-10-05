"""Numeric result correctness and history metadata validation.

These cases pin results that are easy to get subtly wrong -- real-only
polynomial roots, distribution tails, one-sided derivative limits, integral
orientation -- alongside the validation that keeps stored history records
well formed.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
import sympy as sp

from scientific_calculator.app import App
from scientific_calculator.calculation_result import CalculationResult, ResultStatus
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine
from scientific_calculator.history import CalculationHistoryEntry


@pytest.fixture
def engine() -> ScientificCalculatorEngine:
    return ScientificCalculatorEngine(cas_isolated=False)


def test_real_only_polynomial_never_projects_true_complex_roots_onto_the_real_axis(engine) -> None:
    engine.settings.equation_complex = False

    assert engine.polynomial_roots([1, 0, 1e-22]).size == 0


@pytest.mark.parametrize(
    ("lower", "upper"),
    [(-10.1, -10), (-1, 1), (10, 10.1)],
)
def test_normal_cd_uses_a_stable_tail_representation(engine, lower: float, upper: float) -> None:
    result = engine.distribution("Normal CD", lower=lower, upper=upper, mu=0, sigma=1)

    assert result == pytest.approx(
        engine.distribution("Normal CD", lower=-upper, upper=-lower, mu=0, sigma=1), rel=1e-12
    )
    assert result > 0


def test_numeric_derivative_requires_matching_one_sided_limits(engine, monkeypatch) -> None:
    monkeypatch.setattr(
        engine,
        "_run_cas",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fallback required")),
    )

    assert engine.derivative("x^2", "1") == pytest.approx(2, rel=1e-8)
    with pytest.raises(CalculatorError, match="yakınsamadı"):
        engine.derivative("Abs(x)", "0")


def test_reversed_numeric_integral_orients_both_value_representations(engine, monkeypatch) -> None:
    monkeypatch.setattr(
        engine,
        "_evaluate_proper_integral",
        lambda *_args, **_kwargs: CalculationResult(
            ResultStatus.INTEGRAL_EXISTS, 0.5, approx_value=0.5, metadata={"approximate": True}
        ),
    )

    result = engine.definite_integral_result("x", "1", "0")

    assert result.value == pytest.approx(-0.5)
    assert result.approx_value == pytest.approx(-0.5)


@pytest.mark.parametrize("bound", ("i", "sqrt(-1)"))
def test_real_integrals_reject_complex_bounds_at_the_api_boundary(engine, bound: str) -> None:
    with pytest.raises(CalculatorError, match="sonlu reel"):
        engine.definite_integral("x", bound, "1")


def test_distribution_integers_are_never_coerced_through_float(engine, monkeypatch) -> None:
    passed: dict[str, object] = {}

    def pmf(x, n, p):
        passed.update(x=x, n=n, p=p)
        return 1.0

    monkeypatch.setattr("scientific_calculator.calculator_engine.stats.binom.pmf", pmf)
    large_integer = 2**53 + 1

    assert engine.distribution("Binomial PD", x=0, N=large_integer, p=0) == 1
    assert passed["n"] == large_integer


@pytest.mark.parametrize("values", ({"x": 0, "p": 0.5}, {"x": 0, "N": -1, "p": 0.5}))
def test_distribution_integer_failures_are_controlled(engine, values: dict[str, object]) -> None:
    with pytest.raises(CalculatorError, match=r"Argument ERROR: N|negatif olmayan"):
        engine.distribution("Binomial PD", **values)


def test_argument_zero_is_undefined_but_zero_has_a_usable_polar_convention(engine) -> None:
    with pytest.raises(CalculatorError, match=r"arg\(0\)"):
        engine.complex_argument(0)
    assert engine.to_polar(0) == (0.0, 0.0)


def test_extra_variable_keys_raise_a_calculator_error_instead_of_a_raw_type_error(engine) -> None:
    with pytest.raises(CalculatorError, match="tek harf"):
        engine.parse("x", {1: sp.Symbol("x")})  # type: ignore[dict-item]


def test_history_metadata_rejects_cycles_and_excessive_depth() -> None:
    cycle: dict[str, object] = {}
    cycle["self"] = cycle
    deeply_nested: object = "leaf"
    for _ in range(33):
        deeply_nested = [deeply_nested]
    many_values = list(range(1_025))
    list_cycle: list[object] = []
    list_cycle.append(list_cycle)

    with pytest.raises(TypeError, match="cycles"):
        CalculationHistoryEntry("x", "1", metadata=cycle)
    with pytest.raises(TypeError, match="deeply nested"):
        CalculationHistoryEntry("x", "1", metadata={"nested": deeply_nested})
    with pytest.raises(TypeError, match="too many values"):
        CalculationHistoryEntry("x", "1", metadata={"many": many_values})
    with pytest.raises(TypeError, match="cycles"):
        CalculationHistoryEntry("x", "1", metadata={"cycle": list_cycle})


def test_history_metadata_keeps_valid_nested_values() -> None:
    entry = CalculationHistoryEntry("x", "1", metadata={"items": [1, {"pi": math.pi}]})

    assert entry.metadata == {"items": (1, {"pi": math.pi})}


def test_history_uses_equals_for_recall_and_ignores_optn(engine, monkeypatch) -> None:
    app = object.__new__(App)
    app.shift = False
    app._history_lcd_active = lambda: True
    app.consume = lambda: None
    recalled: list[bool] = []
    app._lcd_recall_history_entry = lambda: recalled.append(True)
    app._calculation_busy = False

    App.optn_key(app)
    App.equals(app)

    assert recalled == [True]


def test_save_failure_reports_without_reopening_settings(engine) -> None:
    app = object.__new__(App)
    app.ui_scale = 100
    app.skin_name = "Graphite"
    app.core = SimpleNamespace(settings=engine.settings, history=[])
    app._settings_store = lambda: SimpleNamespace(save_state=lambda *_args: (_ for _ in ()).throw(OSError("locked")))
    app._log_settings_issue = lambda *_args: None
    reported: list[CalculatorError] = []
    app.err = lambda error, **_kwargs: reported.append(error)

    assert App.save_settings_file(app, notify=True) is False
    assert str(reported[0]) == "Settings ERROR: save failed"
