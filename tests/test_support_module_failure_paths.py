"""Failure and shutdown paths of the compact runtime support modules.

These tests exercise failure and shutdown paths that are deliberately hard to
reach through the calculator UI, without adding coverage-only production code.
"""
from __future__ import annotations

import math
import runpy
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pytest
import sympy as sp

import scientific_calculator.calculation_controller as controller_module
import scientific_calculator.numeric_validation as numeric_validation
from scientific_calculator.calculation_controller import CalculationController
from scientific_calculator.calculation_worker import CalculationPayload
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


class RecordingScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple[int, Any]] = []

    def after(self, milliseconds: int, callback: Any) -> None:
        self.calls.append((milliseconds, callback))


@dataclass
class Endpoint:
    closed: int = 0
    close_error: BaseException | None = None

    def close(self) -> None:
        self.closed += 1
        if self.close_error is not None:
            raise self.close_error


@dataclass
class Process:
    alive: bool = True
    exitcode: int = 0
    close_error: BaseException | None = None
    join_error: BaseException | None = None
    calls: list[Any] = field(default_factory=list)

    def start(self) -> None:
        self.calls.append("start")

    def is_alive(self) -> bool:
        self.calls.append("is_alive")
        return self.alive

    def terminate(self) -> None:
        self.calls.append("terminate")
        self.alive = False

    def join(self, timeout: float) -> None:
        self.calls.append(("join", timeout))
        if self.join_error is not None:
            raise self.join_error

    def close(self) -> None:
        self.calls.append("close")
        if self.close_error is not None:
            raise self.close_error


class ProcessContext:
    def __init__(self, parent: Endpoint, child: Endpoint, process: Process) -> None:
        self.parent = parent
        self.child = child
        self.process = process

    def Pipe(self, *, duplex: bool) -> tuple[Endpoint, Endpoint]:
        assert duplex is False
        return self.parent, self.child

    def Process(self, **_kwargs: Any) -> Process:
        return self.process


def _patch_process_context(monkeypatch: pytest.MonkeyPatch, process: Process) -> tuple[Endpoint, Endpoint]:
    parent, child = Endpoint(), Endpoint()
    context = ProcessContext(parent, child, process)
    monkeypatch.setattr(controller_module.mp, "get_context", lambda _name: context)
    return parent, child


def _start_with_callbacks(controller: CalculationController, **callbacks: Any) -> bool:
    return controller.start_engine_method(
        ScientificCalculatorEngine(),
        "evaluate",
        "2+2",
        on_start=callbacks.get("on_start", lambda: None),
        on_success=callbacks.get("on_success", lambda _payload: None),
        on_error=callbacks.get("on_error", lambda _error: None),
        on_finish=callbacks.get("on_finish", lambda: None),
    )


def _arm(
    controller: CalculationController,
    *,
    process: Any = None,
    connection: Any = None,
    callbacks: Any = None,
) -> None:
    controller._active_id = 1
    controller._process = process
    controller._connection = connection
    controller._callbacks = callbacks


def test_nonfinite_detection_handles_all_numeric_kinds_and_conversion_failures(monkeypatch: pytest.MonkeyPatch):
    assert numeric_validation.is_known_nonfinite(sp.Symbol("nonfinite", finite=False))
    assert not numeric_validation.is_known_nonfinite(sp.Symbol("unknown"))
    assert numeric_validation.is_known_nonfinite(np.complex128(complex(0, math.inf)))
    assert not numeric_validation.is_known_nonfinite(np.float32(1.25))
    assert not numeric_validation.is_known_nonfinite(np.int64(7))
    assert not numeric_validation.is_known_nonfinite(10**1000)

    monkeypatch.setattr(numeric_validation.math, "isfinite", lambda _value: (_ for _ in ()).throw(TypeError()))
    assert numeric_validation.is_known_nonfinite(1.0)


def test_numeric_coercion_validates_sympy_type_errors_and_post_conversion_finiteness(
    monkeypatch: pytest.MonkeyPatch,
):
    with pytest.raises(CalculatorError, match="bad"):
        numeric_validation.finite_real_float(sp.I, "bad")
    with pytest.raises(CalculatorError, match="bad"):
        numeric_validation.finite_real_float(object(), "bad")
    assert numeric_validation.finite_complex(2 + 3j, "bad") == 2 + 3j
    with pytest.raises(CalculatorError, match="bad"):
        numeric_validation.finite_complex(object(), "bad")

    monkeypatch.setattr(numeric_validation, "is_known_nonfinite", lambda _value: False)
    with pytest.raises(CalculatorError, match="bad"):
        numeric_validation.finite_real_float(math.inf, "bad")
    with pytest.raises(CalculatorError, match="bad"):
        numeric_validation.finite_complex(complex(math.inf, 0), "bad")


def test_module_entrypoint_imports_without_starting_and_runs_main_as_script(monkeypatch: pytest.MonkeyPatch):
    import scientific_calculator.app as app

    calls: list[str] = []
    monkeypatch.setattr(app, "main", lambda: calls.append("main"))

    runpy.run_module("scientific_calculator.__main__", run_name="entrypoint_import")
    assert calls == []

    runpy.run_module("scientific_calculator.__main__", run_name="__main__")
    assert calls == ["main"]


def test_start_closes_pipe_endpoints_when_child_process_start_fails(monkeypatch: pytest.MonkeyPatch):
    class FailingStartProcess(Process):
        def start(self) -> None:
            raise RuntimeError("cannot start")

    process = FailingStartProcess()
    parent, child = _patch_process_context(monkeypatch, process)
    controller = CalculationController(RecordingScheduler())

    with pytest.raises(RuntimeError, match="cannot start"):
        _start_with_callbacks(controller)

    assert parent.closed == child.closed == 1
    assert not controller.busy


def test_start_callback_failure_without_registered_callbacks_still_reaps_process(monkeypatch: pytest.MonkeyPatch):
    process = Process()
    _patch_process_context(monkeypatch, process)
    scheduler = RecordingScheduler()
    controller = CalculationController(scheduler)

    def unset_callbacks_then_fail() -> None:
        controller._callbacks = None
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        _start_with_callbacks(controller, on_start=unset_callbacks_then_fail)

    assert not controller.busy
    assert scheduler.calls


def test_stop_without_wait_handles_dead_and_broken_processes():
    dead = Process(alive=False)
    CalculationController._stop_without_wait(dead)
    assert ("join", 0) in dead.calls
    assert "terminate" not in dead.calls

    class BrokenProcess:
        def is_alive(self) -> bool:
            raise OSError("unavailable")

    CalculationController._stop_without_wait(BrokenProcess())


def test_cleanup_handles_absent_connection_process_and_scheduler_exception():
    scheduler = RecordingScheduler()
    controller = CalculationController(scheduler)
    controller._schedule_cleanup(None, None, terminate=False)
    assert scheduler.calls == []

    controller._schedule_cleanup(None, Endpoint(close_error=OSError("closed")), terminate=False)
    assert scheduler.calls == []


def test_poll_cleanup_covers_live_kill_fallback_and_operating_system_failures():
    scheduler = RecordingScheduler()
    controller = CalculationController(scheduler)

    live_with_kill = Process(alive=True)
    live_with_kill.kill = lambda: live_with_kill.calls.append("kill")  # type: ignore[attr-defined]
    controller._poll_cleanup(live_with_kill, terminate=False, attempts=20)
    assert "kill" in live_with_kill.calls
    assert scheduler.calls

    controller._poll_cleanup(Process(alive=True), terminate=False, attempts=1)
    assert len(scheduler.calls) >= 2

    class NoKillProcess(Process):
        def terminate(self) -> None:
            self.calls.append("terminate")

    no_kill = NoKillProcess(alive=True)
    controller._poll_cleanup(no_kill, terminate=False, attempts=40)
    assert "terminate" in no_kill.calls

    class BrokenJoinProcess(Process):
        def join(self, timeout: float) -> None:
            raise OSError("cannot join")

    controller._poll_cleanup(BrokenJoinProcess(alive=False), terminate=False, attempts=0)


def test_poll_cleanup_handles_nonterminating_false_condition_before_reaping():
    scheduler = RecordingScheduler()
    controller = CalculationController(scheduler)
    process = Process(alive=False)

    controller._poll_cleanup(process, terminate=False, attempts=0)

    assert "close" in process.calls


def test_finish_helpers_and_cancel_cover_no_callback_states():
    scheduler = RecordingScheduler()
    controller = CalculationController(scheduler)
    controller._finish_success(CalculationPayload(result=1, ans=1, history=[], memory={}))
    controller._finish_error(RuntimeError("failure"))
    assert controller.cancel() is False
    assert scheduler.calls == []


def test_close_handles_each_shutdown_state_and_suppresses_cleanup_errors():
    controller = CalculationController(RecordingScheduler())
    assert controller.close() is False

    controller = CalculationController(RecordingScheduler())
    _arm(controller)
    assert controller.close() is True

    dead = Process(alive=False)
    controller = CalculationController(RecordingScheduler())
    _arm(controller, process=dead)
    assert controller.close() is True
    assert ("join", 0.5) in dead.calls

    class StubbornProcess(Process):
        def terminate(self) -> None:
            self.calls.append("terminate")

        def kill(self) -> None:
            self.calls.append("kill")
            self.alive = False

    stubborn = StubbornProcess(alive=True)
    controller = CalculationController(RecordingScheduler())
    _arm(controller, process=stubborn, connection=Endpoint())
    assert controller.close() is True
    assert "kill" in stubborn.calls
    assert "close" in stubborn.calls

    class StubbornNoKill(Process):
        def terminate(self) -> None:
            self.calls.append("terminate")

    no_kill = StubbornNoKill(alive=True)
    controller = CalculationController(RecordingScheduler())
    _arm(controller, process=no_kill)
    assert controller.close() is True
    assert "terminate" in no_kill.calls

    class BrokenShutdownProcess(Process):
        def is_alive(self) -> bool:
            raise OSError("cannot query")

    finished: list[str] = []
    controller = CalculationController(RecordingScheduler())
    _arm(
        controller,
        process=BrokenShutdownProcess(),
        connection=Endpoint(close_error=OSError("already closed")),
        callbacks=(lambda: None, lambda _value: None, lambda _error: None, lambda: finished.append("finish")),
    )
    assert controller.close() is True
    assert finished == ["finish"]
