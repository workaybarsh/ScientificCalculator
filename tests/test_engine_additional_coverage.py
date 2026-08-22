"""Behavioral regression tests for engine and worker-controller edge paths.

These cases deliberately exercise user-visible error handling and cleanup paths
that are easy to miss in normal calculator workflows.  They are not coverage
stubs: each assertion describes a safety or lifecycle guarantee relied on by
the application.
"""
from __future__ import annotations

import ast
import math
from collections.abc import Callable

import numpy as np
import pytest
import sympy as sp

import scientific_calculator.calculation_controller as controller_module
import scientific_calculator.calculator_engine as engine_module
from scientific_calculator.calculation_controller import CalculationController
from scientific_calculator.calculation_errors import WorkerCrashed
from scientific_calculator.calculation_worker import CalculationPayload
from scientific_calculator.calculator_engine import (
    CURRENT_CONSTANTS_DATASET_LABEL,
    CalculatorError,
    ScientificCalculatorEngine,
    constants_for_dataset,
)
from scientific_calculator.cas_worker import CASWorkerError


class _Scheduler:
    def __init__(self) -> None:
        self.calls: list[int] = []
        self.callbacks: list[Callable[[], None]] = []

    def after(self, milliseconds: int, callback: Callable[[], None]) -> None:
        self.calls.append(milliseconds)
        self.callbacks.append(callback)


class _Connection:
    def __init__(self, *, poll_error: Exception | None = None) -> None:
        self.closed = False
        self.poll_error = poll_error

    def close(self) -> None:
        self.closed = True

    def poll(self) -> bool:
        if self.poll_error is not None:
            raise self.poll_error
        return False

    def recv(self) -> object:
        raise AssertionError("recv must not be reached for this connection")


class _Process:
    def __init__(self, *, alive: bool = True, exitcode: int = 0) -> None:
        self.alive = alive
        self.exitcode = exitcode
        self.calls: list[object] = []

    def start(self) -> None:
        self.calls.append("start")

    def is_alive(self) -> bool:
        self.calls.append("is_alive")
        return self.alive

    def terminate(self) -> None:
        self.calls.append("terminate")
        self.alive = False

    def kill(self) -> None:
        self.calls.append("kill")
        self.alive = False

    def join(self, timeout: float) -> None:
        self.calls.append(("join", timeout))

    def close(self) -> None:
        self.calls.append("close")


class _StubbornProcess(_Process):
    def terminate(self) -> None:
        self.calls.append("terminate")


class _NoKillProcess:
    def __init__(self) -> None:
        self.alive = True
        self.calls: list[object] = []

    def is_alive(self) -> bool:
        self.calls.append("is_alive")
        return self.alive

    def terminate(self) -> None:
        self.calls.append("terminate")
        self.alive = False

    def join(self, timeout: float) -> None:
        self.calls.append(("join", timeout))

    def close(self) -> None:
        self.calls.append("close")


class _BrokenProcess:
    def is_alive(self) -> bool:
        raise OSError("process handle is already closed")

    def terminate(self) -> None:
        raise AssertionError("a broken process must not be terminated")

    def join(self, _timeout: float) -> None:
        raise AssertionError("a broken process must not be joined")


class _StubbornCloseProcess(_Process):
    def terminate(self) -> None:
        self.calls.append("terminate")


class _BrokenConnection:
    def close(self) -> None:
        raise OSError("connection is already closed")


def _start(
    controller: CalculationController,
    *,
    on_start: Callable[[], None] = lambda: None,
    on_success: Callable[[CalculationPayload], None] = lambda _payload: None,
    on_error: Callable[[Exception], None] = lambda _error: None,
    on_finish: Callable[[], None] = lambda: None,
) -> bool:
    return controller.start_engine_method(
        ScientificCalculatorEngine(),
        "evaluate",
        "2+2",
        on_start=on_start,
        on_success=on_success,
        on_error=on_error,
        on_finish=on_finish,
    )


@pytest.fixture
def engine() -> ScientificCalculatorEngine:
    return ScientificCalculatorEngine(cas_isolated=False)


def test_controller_startup_failure_closes_both_pipe_ends_and_leaves_no_active_operation(monkeypatch):
    parent, child = _Connection(), _Connection()
    process = _Process()

    def fail_start() -> None:
        process.calls.append("start")
        raise OSError("cannot start calculation worker")

    process.start = fail_start  # type: ignore[method-assign]
    context = type(
        "Context",
        (),
        {
            "Pipe": staticmethod(lambda duplex=False: (parent, child)),
            "Process": staticmethod(lambda **_kwargs: process),
        },
    )()
    monkeypatch.setattr(controller_module.mp, "get_context", lambda _name: context)
    controller = CalculationController(_Scheduler())

    with pytest.raises(OSError, match="cannot start"):
        _start(controller)

    assert parent.closed and child.closed
    assert controller.busy is False


def test_controller_ignores_stale_polls_and_translates_connection_value_errors():
    scheduler = _Scheduler()
    controller = CalculationController(scheduler)

    controller._poll(1)
    assert scheduler.callbacks == []

    events: list[object] = []
    controller._active_id = 1
    controller._process = _Process(alive=False)
    controller._connection = _Connection(poll_error=ValueError("closed handle"))
    controller._callbacks = (
        lambda: None,
        lambda payload: events.append(payload),
        lambda error: events.append(error),
        lambda: events.append("finished"),
    )
    controller._poll(1)

    assert isinstance(events[0], WorkerCrashed)
    assert events[-1] == "finished"
    assert controller.busy is False


def test_controller_cleanup_escalates_to_kill_then_reaps_on_a_later_scheduler_turn():
    scheduler = _Scheduler()
    controller = CalculationController(scheduler)
    process = _StubbornProcess()

    controller._poll_cleanup(process, terminate=True, attempts=20)

    assert "kill" in process.calls
    assert scheduler.callbacks
    scheduler.callbacks.pop()()
    assert "close" in process.calls


def test_controller_cleanup_uses_nonblocking_emergency_stop_when_kill_is_unavailable():
    scheduler = _Scheduler()
    controller = CalculationController(scheduler)
    process = _NoKillProcess()

    controller._poll_cleanup(process, terminate=True, attempts=40)

    assert "terminate" in process.calls
    assert ("join", 0) in process.calls
    assert scheduler.callbacks == []


def test_controller_finish_always_runs_finish_callback_and_idle_operations_are_noops():
    scheduler = _Scheduler()
    controller = CalculationController(scheduler)
    finished: list[bool] = []
    controller._active_id = 1
    controller._process = _Process(alive=False)
    controller._connection = _Connection()
    controller._callbacks = (
        lambda: None,
        lambda _payload: (_ for _ in ()).throw(RuntimeError("success callback failed")),
        lambda _error: None,
        lambda: finished.append(True),
    )

    with pytest.raises(RuntimeError, match="success callback failed"):
        controller._finish_success(CalculationPayload(4, 4, [], {}))

    assert finished == [True]
    assert controller.busy is False
    assert controller.cancel() is False
    assert controller.close() is False


def test_controller_cleanup_tolerates_closed_handles_and_close_escalates_to_kill():
    controller = CalculationController(_Scheduler())
    controller._schedule_cleanup(None, _BrokenConnection(), terminate=True)
    controller._poll_cleanup(_BrokenProcess(), terminate=True, attempts=0)
    CalculationController._stop_without_wait(_BrokenProcess())

    finished: list[bool] = []
    process = _StubbornCloseProcess()
    controller._active_id = 3
    controller._process = process
    controller._connection = _Connection()
    controller._callbacks = (lambda: None, lambda _payload: None, lambda _error: None, lambda: finished.append(True))

    assert controller.close() is True
    assert "terminate" in process.calls
    assert "kill" in process.calls
    assert ("join", 0.5) in process.calls
    assert "close" in process.calls
    assert finished == [True]


def test_constants_angle_modes_memory_and_base_unary_operations(engine):
    current = constants_for_dataset(CURRENT_CONSTANTS_DATASET_LABEL)
    assert current["c0"][1] == pytest.approx(299792458.0)
    assert constants_for_dataset("not a dataset") is not current

    engine.settings.angle_unit = "GRA"
    assert engine._angle_to_rad(100) == sp.pi / 2
    assert engine._rad_to_angle(sp.pi / 2) == 100
    assert engine.pol(0, 1) == pytest.approx((1, 100))
    assert engine.rec(1, 100) == pytest.approx((0, 1), abs=1e-12)
    assert engine.complex_argument(1j) == pytest.approx(100)
    assert engine.from_polar(1, 100) == pytest.approx(1j)

    engine.ans = sp.Integer(7)
    assert engine.store("A") == 7
    assert engine.m_plus() == pytest.approx(7)
    assert engine.m_minus() == pytest.approx(0)
    engine.history.append(("seed", "7"))
    engine.define_matrix("MatA", [[1]])
    engine.define_vector("VctA", [1, 0])
    engine.initialize_all()
    assert engine.ans == 0
    assert engine.history == []
    assert engine.matrices["MatA"] is None
    assert engine.vectors["VctA"] is None

    assert engine.base_operation(0, op="Not") == -1
    assert engine.base_operation(1, op="Neg") == -1
    assert engine.evaluate_base("Not(b0)", 10) == -1
    assert engine.evaluate_base("Neg(h1)", 10) == -1
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.base_operation(1, op="unsupported")


def test_parser_and_evaluation_keep_security_and_transactional_state_boundaries(engine):
    with pytest.raises(CalculatorError, match="Değişken tek harf"):
        engine.locals({"xy": 2})
    with pytest.raises(CalculatorError, match="Geçersiz değişken"):
        engine.locals({"x": True})
    with pytest.raises(CalculatorError, match="yüzde için sol değer"):
        engine.parse("%2")
    with pytest.raises(CalculatorError, match="Math ERROR"):
        engine.evaluate("nCr(3,4)")

    engine.ans = sp.Integer(9)
    engine.history = [("seed", "9")]
    with pytest.raises(CalculatorError):
        engine.evaluate("2:1/0")
    assert engine.ans == 9
    assert engine.history == [("seed", "9")]

    assert engine.evaluate("2:Ans+3") == 5
    assert engine.history[-2:] == [("2", "2"), ("Ans+3", "5")]
    assert engine.evaluate_with_values("2x=ignored", {"x": 3}) == pytest.approx(6)
    assert engine.history[-1] == ("2x=ignored", "6.000")


def test_parser_security_helpers_classify_untrusted_ast_and_resource_inputs(engine):
    assert math.isinf(engine_module._constant_numeric_approx(ast.parse("2**100000", mode="eval").body))
    assert engine_module._constant_numeric_approx(ast.parse("(-1)**0.5", mode="eval").body) is None
    assert engine_module._constant_numeric_approx(ast.parse("factorial(171)", mode="eval").body) == math.inf
    assert engine_module._constant_numeric_approx(ast.parse("nCr(3,4)", mode="eval").body) is None
    assert engine_module._evaluated_numeric_approx(complex(math.inf, 0)) == math.inf
    assert engine_module._evaluated_numeric_approx(sp.oo) == math.inf
    assert engine_module._evaluated_numeric_approx(sp.Rational(3, 2)) == pytest.approx(1.5)
    assert engine_module._estimated_combinatoric_digits(3, 4, permutation=False) == 1

    for source in ("1//2", "not 1", "missing_name", "'text'", "[1]"):
        restricted = engine_module._RestrictedExpression({})
        with pytest.raises(CalculatorError):
            restricted.validate(ast.parse(source, mode="eval"))
    with pytest.raises(CalculatorError):
        engine_module._RestrictedExpression({}).evaluate(ast.parse("[1]", mode="eval"))

    assert engine.evaluate("(1/2)^0") == 1
    assert engine.evaluate("0^4") == 0
    assert engine.evaluate("2^-3") == sp.Rational(1, 8)
    with pytest.raises(CalculatorError, match="çok uzun"):
        engine.parse("²" * 1025)
    with pytest.raises(CalculatorError, match="geçerli sol değer"):
        engine.parse("1+%")
    with pytest.raises(CalculatorError, match="unmatched opening"):
        engine.parse("(1")
    with pytest.raises(CalculatorError, match="İfade metin"):
        engine.evaluate(None)  # type: ignore[arg-type]


def test_solver_and_calculus_failure_paths_preserve_last_committed_state(engine, monkeypatch):
    original = engine._run_cas

    def fallback(operation: str, payload: dict[str, object]):
        if operation == "nsolve":
            raise CASWorkerError("NoConvergence", "forced numerical failure")
        return original(operation, payload)

    monkeypatch.setattr(engine, "_run_cas", fallback)
    engine.ans = sp.Integer(13)
    engine.history = [("seed", "13")]
    with pytest.raises(CalculatorError, match="Başlangıç tahminini"):
        engine.solve("x^2+1=0", guess=0)
    assert engine.ans == 13
    assert engine.history == [("seed", "13")]

    monkeypatch.setattr(
        engine,
        "_run_cas",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CASWorkerError("unavailable")),
    )
    with pytest.raises(CalculatorError, match="Σ hesaplanamadı"):
        engine.summation("x", "1", "3")
    assert engine.ans == 13
    assert engine.history == [("seed", "13")]


def test_numeric_derivative_fallback_rejects_nonfinite_samples(engine, monkeypatch):
    monkeypatch.setattr(
        engine,
        "_run_cas",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CASWorkerError("unavailable")),
    )
    monkeypatch.setattr(engine_module.sp, "lambdify", lambda *_args, **_kwargs: lambda _x: math.nan)

    with pytest.raises(CalculatorError, match="türev noktasında"):
        engine.derivative("x", "0")


def test_solve_falls_back_to_symbolic_roots_when_numeric_solver_fails(engine, monkeypatch):
    original = engine._run_cas

    def fallback(operation: str, payload: dict[str, object]):
        if operation == "nsolve":
            raise CASWorkerError("NoConvergence", "forced numerical failure")
        return original(operation, payload)

    monkeypatch.setattr(engine, "_run_cas", fallback)

    root, residual = engine.solve("x^2=4", guess=1)

    assert root == pytest.approx(2)
    assert residual == pytest.approx(0)
    assert engine.memory["x"] == pytest.approx(2)


def test_symbolic_failures_and_unresolved_results_do_not_commit_calculus_state(engine, monkeypatch):
    engine.ans = sp.Integer(11)
    engine.history = [("seed", "11")]

    def unresolved(operation: str, payload: dict[str, object]):
        if operation == "indefinite_integral":
            symbol = payload["symbol"]
            return sp.Integral(payload["expression"], symbol)
        raise AssertionError(f"unexpected CAS operation: {operation}")

    monkeypatch.setattr(engine, "_run_cas", unresolved)
    with pytest.raises(CalculatorError, match="kapalı biçimde"):
        engine.symbolic_integral("sin(x)")
    assert engine.ans == 11
    assert engine.history == [("seed", "11")]

    monkeypatch.setattr(
        engine,
        "_run_cas",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(CASWorkerError("down")),
    )
    with pytest.raises(CalculatorError, match="sembolik türev"):
        engine.symbolic_derivative("x^2")
    assert engine.ans == 11
    assert engine.history == [("seed", "11")]


def test_extended_matrix_and_vector_operations_cover_safe_transforms(engine):
    matrix = [[1, -2], [3, -4]]
    other = [[2, 1], [0, 2]]
    np.testing.assert_allclose(engine.matrix_op("+", matrix, other), [[3, -1], [3, -2]])
    np.testing.assert_allclose(engine.matrix_op("-", matrix, other), [[-1, -3], [3, -6]])
    np.testing.assert_allclose(engine.matrix_op("trn", matrix), [[1, 3], [-2, -4]])
    np.testing.assert_allclose(engine.matrix_op("square", matrix), [[-5, 6], [-9, 10]])
    np.testing.assert_allclose(engine.matrix_op("cube", matrix), [[13, -14], [21, -22]])
    np.testing.assert_allclose(engine.matrix_op("abs", matrix), [[1, 2], [3, 4]])
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.matrix_op("unknown", matrix)
    with pytest.raises(CalculatorError, match="geçersiz matris verisi"):
        engine.matrix_op("trn", object())
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.matrix_op("square", [[1, 2, 3], [4, 5, 6]])
    with np.errstate(over="ignore"), pytest.raises(CalculatorError, match="sonucu sonlu değil"):
        engine.matrix_op("square", [[1e308]])

    np.testing.assert_allclose(engine.vector_op("+", [1, 2], [3, 4]), [4, 6])
    np.testing.assert_allclose(engine.vector_op("-", [1, 2], [3, 4]), [-2, -2])
    np.testing.assert_allclose(engine.vector_op("scale", [1, -2], scalar=2.5), [2.5, -5])
    np.testing.assert_allclose(engine.vector_op("unit", [3, 4]), [0.6, 0.8])
    engine.settings.angle_unit = "GRA"
    assert engine.vector_op("angle", [1, 0], [0, 1]) == pytest.approx(100)
    with pytest.raises(CalculatorError, match="skaler"):
        engine.vector_op("scale", [1, 2], scalar="not a scalar")
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.vector_op("unknown", [1, 2])
    with np.errstate(over="ignore"), pytest.raises(CalculatorError, match="sonucu sonlu değil"):
        engine.vector_op("scale", [1e308, 1], scalar=1e308)


def test_extended_equation_distribution_and_conversion_paths(engine):
    assert engine.distribution("Binomial CD", x=2, N=4, p=0.5) == pytest.approx(0.6875)
    assert engine.distribution("Poisson PD", x=2, lam=1) == pytest.approx(math.exp(-1) / 2)
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.distribution("unknown")

    with pytest.raises(CalculatorError, match="Math ERROR"):
        engine.simultaneous([[1, 1], [2, 2]], [1, 2])
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.simultaneous([[1, 1, 1], [2, 2, 2]], [1, 2])

    engine.settings.equation_complex = False
    assert engine.polynomial_roots([1, 0, 1]).size == 0
    solution = engine.inequality([1, -2], ">=")
    symbol = next(iter(solution.free_symbols))
    assert bool(solution.subs(symbol, 2)) is True
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.inequality([1, -2], "!=")

    assert engine.convert("cm→in", 2.54) == pytest.approx(1)
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.convert("invalid conversion", 1)
    with pytest.raises(CalculatorError, match="oran değeri eksik"):
        engine.ratio("A:B=X:D", A=1, B=2)


def test_result_formatting_handles_arrays_equalities_and_nonfinite_numeric_values(engine):
    assert engine.format_result(np.array([[1.0, 2.0]])) == "[[1. 2.]]"
    x = sp.Symbol("x")
    assert engine.format_result(sp.Eq(x, sp.Rational(1, 2))) == "x = 1/2"

    engine.settings.input_output = "MathI/DecimalO"
    engine.settings.number_format = "Sci"
    engine.settings.number_digits = 3
    assert engine.format_result(sp.Rational(1, 3)) == "3.33e-01"
    assert engine.format_result(complex(1, 0)) == "1.00e+00"
    assert engine.format_result(1 + sp.I, approximate=True) == "1.00e+00+1.00e+00i"
    with pytest.raises(CalculatorError, match="görüntüleme aralığını"):
        engine.format_result(float("inf"))
