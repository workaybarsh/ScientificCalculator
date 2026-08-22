from __future__ import annotations

import time

import pytest

from scientific_calculator.calculation_controller import CalculationController
from scientific_calculator.calculation_worker import build_calculation_request
from scientific_calculator.calculator_engine import ScientificCalculatorEngine


class ManualScheduler:
    def __init__(self):
        self.callbacks = []

    def after(self, _milliseconds, callback):
        self.callbacks.append(callback)

    def run_until_idle(self, controller):
        deadline = time.monotonic() + 10
        while controller.busy and time.monotonic() < deadline:
            if self.callbacks:
                self.callbacks.pop(0)()
            else:
                time.sleep(0.01)
        assert not controller.busy


class CleanupProcess:
    def __init__(self):
        self.calls = []
        self._alive = True

    def is_alive(self):
        self.calls.append("is_alive")
        return self._alive

    def terminate(self):
        self.calls.append("terminate")
        self._alive = False

    def join(self, timeout):
        self.calls.append(("join", timeout))

    def close(self):
        self.calls.append("close")


def test_engine_result_is_committed_only_after_worker_success():
    scheduler = ManualScheduler()
    controller = CalculationController(scheduler, poll_ms=0)
    engine = ScientificCalculatorEngine()
    payloads = []
    finished = []

    assert controller.start_engine_method(
        engine, "evaluate", "2+3",
        on_start=lambda: None,
        on_success=payloads.append,
        on_error=lambda error: (_ for _ in ()).throw(error),
        on_finish=lambda: finished.append(True),
    )
    assert engine.ans == 0  # the worker has an isolated engine snapshot
    scheduler.run_until_idle(controller)
    assert payloads[0].result == 5
    assert payloads[0].ans == 5
    assert finished == [True]


def test_cancel_invalidates_active_operation_without_error_callback():
    scheduler = ManualScheduler()
    controller = CalculationController(scheduler)
    errors = []
    finished = []

    assert controller.start_engine_method(
        ScientificCalculatorEngine(), "evaluate", "2+2",
        on_start=lambda: None,
        on_success=lambda _payload: None,
        on_error=errors.append,
        on_finish=lambda: finished.append(True),
    )
    assert controller.cancel() is True
    assert not controller.busy
    assert errors == []
    assert finished == [True]


def test_request_excludes_large_unrelated_engine_state():
    engine = ScientificCalculatorEngine()
    engine.matrices["MatA"] = object()
    engine.vectors["VctA"] = object()

    request = build_calculation_request(engine, "evaluate", ("2+2",), {})

    assert request.ans == 0
    assert request.memory == engine.memory
    assert not hasattr(request, "matrices")
    assert not hasattr(request, "vectors")


def test_cancel_releases_ui_before_process_cleanup_runs():
    scheduler = ManualScheduler()
    controller = CalculationController(scheduler)
    process = CleanupProcess()
    finished = []
    controller._operation_id = 1
    controller._active_id = 1
    controller._process = process
    controller._callbacks = (lambda: None, lambda _payload: None, lambda _error: None, lambda: finished.append(True))

    assert controller.cancel() is True

    assert not controller.busy
    assert finished == [True]
    assert process.calls == []
    scheduler.callbacks.pop(0)()
    assert "terminate" in process.calls
    assert ("join", 0) in process.calls


class FailingScheduler:
    def after(self, _milliseconds, _callback):
        raise RuntimeError("scheduler unavailable")


def _start(controller, on_start=lambda: None, on_success=lambda _payload: None, on_error=lambda _error: None, on_finish=lambda: None):
    return controller.start_engine_method(
        ScientificCalculatorEngine(), "evaluate", "2+2",
        on_start=on_start,
        on_success=on_success,
        on_error=on_error,
        on_finish=on_finish,
    )


def test_start_callback_failure_cleans_up_and_allows_a_second_operation():
    scheduler = ManualScheduler()
    controller = CalculationController(scheduler)
    finished = []

    with pytest.raises(RuntimeError, match="start failed"):
        _start(controller, on_start=lambda: (_ for _ in ()).throw(RuntimeError("start failed")), on_finish=lambda: finished.append(True))

    assert not controller.busy
    assert finished == [True]
    assert _start(controller)
    controller.cancel()


def test_scheduler_failure_cleans_up_and_allows_a_second_operation():
    controller = CalculationController(FailingScheduler())
    finished = []

    with pytest.raises(RuntimeError, match="scheduler unavailable"):
        _start(controller, on_finish=lambda: finished.append(True))

    assert not controller.busy
    assert finished == [True]
    controller.scheduler = ManualScheduler()
    assert _start(controller)
    controller.cancel()
