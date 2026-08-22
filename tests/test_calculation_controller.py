from __future__ import annotations

import time
import types

import pytest

import scientific_calculator.calculation_controller as controller_module
from scientific_calculator.calculation_controller import CalculationController
from scientific_calculator.calculation_errors import CalculationTimeout, WorkerCrashed, WorkerProtocolError
from scientific_calculator.calculation_worker import CalculationPayload, build_calculation_request, run_calculation
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


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


class PollConnection:
    def __init__(self, response=None, *, ready=True, receive_error=None):
        self.response = response
        self.ready = ready
        self.receive_error = receive_error
        self.closed = False

    def poll(self):
        return self.ready

    def recv(self):
        if self.receive_error:
            raise self.receive_error
        return self.response

    def close(self):
        self.closed = True


class PollProcess(CleanupProcess):
    def __init__(self, *, alive=True, exitcode=0):
        super().__init__()
        self._alive = alive
        self.exitcode = exitcode


def _active_controller(response, *, ready=True, process=None, timeout_seconds=30.0):
    scheduler = ManualScheduler()
    controller = CalculationController(scheduler, timeout_seconds=timeout_seconds)
    events = []
    controller._operation_id = controller._active_id = 1
    controller._process = process or PollProcess(alive=False)
    controller._connection = PollConnection(response, ready=ready)
    controller._started_at = time.monotonic()
    controller._callbacks = (
        lambda: None,
        lambda payload: events.append(("success", payload)),
        lambda error: events.append(("error", error)),
        lambda: events.append(("finish", None)),
    )
    return controller, scheduler, events


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


def test_worker_request_runs_on_a_snapshot_and_returns_only_committable_state():
    engine = ScientificCalculatorEngine()
    request = build_calculation_request(engine, "evaluate", ("2+3",), {})

    payload = run_calculation(request)

    assert payload.result == 5
    assert payload.ans == 5
    assert payload.history[-1][0] == "2+3"
    assert engine.ans == 0


def test_worker_snapshot_runs_a_multivariate_integral_and_returns_its_history():
    engine = ScientificCalculatorEngine()
    request = build_calculation_request(
        engine, "double_integral", ("x*y", "0", "1", "0", "x"), {}
    )

    payload = run_calculation(request)

    assert payload.result == pytest.approx(1 / 8)
    assert payload.ans == pytest.approx(1 / 8)
    assert payload.history[-1][0] == "∫0→1 ∫0→x x*y dy dx"
    assert engine.history == []


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


def test_close_reaps_active_process_without_relying_on_the_scheduler():
    scheduler = ManualScheduler()
    controller = CalculationController(scheduler)
    process = CleanupProcess()
    finished = []
    controller._operation_id = 1
    controller._active_id = 1
    controller._process = process
    controller._callbacks = (
        lambda: None, lambda _payload: None, lambda _error: None, lambda: finished.append(True)
    )

    assert controller.close() is True

    assert not controller.busy
    assert scheduler.callbacks == []
    assert "terminate" in process.calls
    assert ("join", 0.5) in process.calls
    assert "close" in process.calls
    assert finished == [True]


def test_second_start_is_rejected_while_a_worker_is_active():
    controller = CalculationController(ManualScheduler())
    controller._active_id = 1
    assert _start(controller) is False


def test_poll_success_commits_payload_and_schedules_reap():
    payload = CalculationPayload(result=5, ans=5, history=[("2+3", "5")], memory={})
    controller, scheduler, events = _active_controller(("ok", payload))

    controller._poll(1)

    assert not controller.busy
    assert events == [("success", payload), ("finish", None)]
    assert scheduler.callbacks


@pytest.mark.parametrize(
    ("response", "error_type"),
    [
        (("input_error", "bad input"), CalculatorError),
        (("timeout", "late"), CalculationTimeout),
        (("crash", "ValueError", "bad"), WorkerCrashed),
        (("malformed",), WorkerProtocolError),
    ],
)
def test_poll_translates_each_worker_error_response(response, error_type):
    controller, _scheduler, events = _active_controller(response)

    controller._poll(1)

    assert not controller.busy
    assert isinstance(events[0][1], error_type)
    assert events[-1] == ("finish", None)


def test_poll_handles_timeout_crash_and_stale_callbacks():
    controller, scheduler, events = _active_controller(None, ready=False, timeout_seconds=0.0)
    controller._started_at = 0.0
    controller._poll(1)
    assert isinstance(events[0][1], CalculationTimeout)
    assert scheduler.callbacks

    controller, _scheduler, events = _active_controller(None, ready=False, process=PollProcess(alive=False, exitcode=12))
    controller._poll(1)
    assert isinstance(events[0][1], WorkerCrashed)
    assert "12" in str(events[0][1])

    controller, _scheduler, events = _active_controller(("ok", object()))
    controller._poll(2)
    assert controller.busy
    assert events == []


def test_poll_waits_for_live_worker_and_converts_connection_eof_to_crash():
    controller, scheduler, events = _active_controller(None, ready=False, process=PollProcess(alive=True))
    controller._poll(1)
    assert controller.busy
    assert scheduler.callbacks

    controller, _scheduler, events = _active_controller(None)
    controller._connection = PollConnection(receive_error=EOFError())
    controller._poll(1)
    assert isinstance(events[0][1], WorkerCrashed)


def test_worker_serializes_expected_and_unexpected_failures(monkeypatch):
    connection = types.SimpleNamespace(sent=[], closed=False)
    connection.send = connection.sent.append
    connection.close = lambda: setattr(connection, "closed", True)
    request = object()
    monkeypatch.setattr(controller_module, "run_calculation", lambda _request: "done")
    controller_module._worker(connection, request)
    assert connection.sent == [("ok", "done")]
    assert connection.closed

    connection = types.SimpleNamespace(sent=[], closed=False)
    connection.send = connection.sent.append
    connection.close = lambda: setattr(connection, "closed", True)
    monkeypatch.setattr(
        controller_module, "run_calculation", lambda _request: (_ for _ in ()).throw(CalculatorError("bad"))
    )
    controller_module._worker(connection, request)
    assert connection.sent == [("input_error", "bad")]

    connection = types.SimpleNamespace(sent=[], closed=False)
    connection.send = connection.sent.append
    connection.close = lambda: setattr(connection, "closed", True)
    monkeypatch.setattr(
        controller_module, "run_calculation", lambda _request: (_ for _ in ()).throw(CalculationTimeout("late"))
    )
    controller_module._worker(connection, request)
    assert connection.sent == [("timeout", "late")]

    connection = types.SimpleNamespace(sent=[], closed=False)
    connection.send = connection.sent.append
    connection.close = lambda: setattr(connection, "closed", True)
    monkeypatch.setattr(
        controller_module, "run_calculation", lambda _request: (_ for _ in ()).throw(RuntimeError("bad"))
    )
    controller_module._worker(connection, request)
    assert connection.sent[0][:2] == ("crash", "RuntimeError")

    connection = types.SimpleNamespace(closed=False)
    connection.send = lambda _value: (_ for _ in ()).throw(BrokenPipeError())
    connection.close = lambda: setattr(connection, "closed", True)
    monkeypatch.setattr(controller_module, "run_calculation", lambda _request: "done")
    controller_module._worker(connection, request)
    assert connection.closed


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
