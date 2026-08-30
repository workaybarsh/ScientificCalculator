import pytest
import sympy as sp

import scientific_calculator.cas_worker as cas_module
from scientific_calculator.calculation_errors import WorkerCrashed
from scientific_calculator.cas_worker import CASTimeout, CASWorkerError, _dispatch, run_cas


def test_dispatches_every_bounded_calculus_operation():
    x=sp.Symbol("x")
    assert _dispatch("simplify", {"expression": (x**2-1)/(x-1)}) == x+1
    assert _dispatch("differentiate", {"expression": x**3, "symbol": x}) == 3*x**2
    assert _dispatch("differentiate_at_point", {"expression": x**3, "symbol": x, "point": 2}) == 12
    assert _dispatch("limit", {"expression": sp.sin(x)/x, "symbol": x, "point": 0, "dir": "+"}) == 1
    assert _dispatch("singularities", {"expression": 1/(x-1), "symbol": x}) == sp.FiniteSet(1)
    assert float(_dispatch("nsolve", {"expression": x - 3, "symbol": x, "guess": 0})) == pytest.approx(3)
    assert _dispatch("solve", {"expression": x**2 - 1, "symbol": x}) == [-1, 1]
    y = sp.Function("y")(x)
    assert _dispatch("dsolve", {"equation": sp.Eq(sp.diff(y, x), y), "function": y}) == sp.Eq(y, sp.Symbol("C1") * sp.exp(x))
    assert _dispatch("definite_integral", {"expression": x, "symbol": x, "lower": 0, "upper": 1}) == sp.Rational(1, 2)
    assert _dispatch("indefinite_integral", {"expression": x, "symbol": x}) == x**2 / 2
    assert _dispatch("summation", {"expression": x, "symbol": x, "lower": 1, "upper": 3}) == 6


def test_dispatch_rejects_unknown_operation():
    with pytest.raises(ValueError, match="Unknown CAS operation"):
        _dispatch("not-an-operation", {})


class _Connection:
    def __init__(self, response=None, *, poll=True, recv_error=None):
        self.response = response
        self.poll_value = poll
        self.recv_error = recv_error
        self.sent = []
        self.closed = False

    def send(self, value):
        self.sent.append(value)

    def poll(self, _timeout=None):
        return self.poll_value

    def recv(self):
        if self.recv_error:
            raise self.recv_error
        return self.response

    def close(self):
        self.closed = True


class _Process:
    def __init__(self, *, alive=True, exitcode=0, kill=True):
        self.alive = alive
        self.exitcode = exitcode
        self.can_kill = kill
        self.calls = []

    def is_alive(self):
        self.calls.append("is_alive")
        return self.alive

    def start(self):
        self.calls.append("start")

    def terminate(self):
        self.calls.append("terminate")
        self.alive = False

    def kill(self):
        if not self.can_kill:
            raise AttributeError
        self.calls.append("kill")
        self.alive = False

    def join(self, timeout):
        self.calls.append(("join", timeout))


class _StubbornProcess(_Process):
    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")
        self.alive = False


def test_worker_main_serializes_success_and_failure(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(cas_module, "_dispatch", lambda *_args: 42)
    cas_module._worker_main(connection, "simplify", {})
    assert connection.sent == [("ok", 42)]
    assert connection.closed

    connection = _Connection()
    monkeypatch.setattr(cas_module, "_dispatch", lambda *_args: (_ for _ in ()).throw(ValueError("bad")))
    cas_module._worker_main(connection, "simplify", {})
    assert connection.sent[0][:2] == ("error", "ValueError")
    assert connection.closed

    connection = _Connection()
    connection.send = lambda _value: (_ for _ in ()).throw(BrokenPipeError())
    monkeypatch.setattr(cas_module, "_dispatch", lambda *_args: 42)
    cas_module._worker_main(connection, "simplify", {})
    assert connection.closed


def test_stop_terminates_and_reaps_processes():
    process = _Process(alive=True)
    cas_module._stop(process)
    assert "terminate" in process.calls
    assert ("join", 0.5) in process.calls

    process = _Process(alive=False)
    cas_module._stop(process)
    assert ("join", 0.1) in process.calls

    process = _StubbornProcess(alive=True)
    cas_module._stop(process)
    assert "kill" in process.calls


def test_run_cas_inline_success_and_timeout(monkeypatch):
    monkeypatch.setattr(cas_module, "_dispatch", lambda *_args: 9)
    assert run_cas("simplify", {}, isolated=False) == 9
    ticks = iter((1.0, 2.0))
    monkeypatch.setattr(cas_module.time, "monotonic", lambda: next(ticks))
    with pytest.raises(CASTimeout):
        run_cas("simplify", {}, isolated=False, timeout=0.5)


def test_isolated_protocol_and_eof_failures_are_typed(monkeypatch):
    connection = _Connection(("error", "ValueError", "bad"))
    process = _Process(alive=False)
    context = type("Context", (), {
        "Pipe": staticmethod(lambda duplex=False: (connection, _Connection())),
        "Process": staticmethod(lambda **_kwargs: process),
    })()
    monkeypatch.setattr(cas_module.mp, "get_context", lambda _name: context)
    with pytest.raises(CASWorkerError, match="ValueError"):
        cas_module._run_isolated("simplify", {}, 1)

    eof_connection = _Connection(recv_error=EOFError())
    eof_process = _Process(alive=False, exitcode=7)
    eof_context = type("Context", (), {
        "Pipe": staticmethod(lambda duplex=False: (eof_connection, _Connection())),
        "Process": staticmethod(lambda **_kwargs: eof_process),
    })()
    monkeypatch.setattr(cas_module.mp, "get_context", lambda _name: eof_context)
    with pytest.raises(WorkerCrashed, match="exited with code 7"):
        cas_module._run_isolated("simplify", {}, 1)


def test_isolated_timeout_and_invalid_response_stop_the_child(monkeypatch):
    timeout_connection = _Connection(poll=False)
    timeout_process = _Process(alive=True)
    timeout_context = type("Context", (), {
        "Pipe": staticmethod(lambda duplex=False: (timeout_connection, _Connection())),
        "Process": staticmethod(lambda **_kwargs: timeout_process),
    })()
    monkeypatch.setattr(cas_module.mp, "get_context", lambda _name: timeout_context)
    with pytest.raises(CASTimeout):
        cas_module._run_isolated("simplify", {}, 1)
    assert "terminate" in timeout_process.calls

    invalid_connection = _Connection(("invalid",))
    invalid_process = _Process(alive=False)
    invalid_context = type("Context", (), {
        "Pipe": staticmethod(lambda duplex=False: (invalid_connection, _Connection())),
        "Process": staticmethod(lambda **_kwargs: invalid_process),
    })()
    monkeypatch.setattr(cas_module.mp, "get_context", lambda _name: invalid_context)
    with pytest.raises(CASWorkerError, match="WorkerProtocolError"):
        cas_module._run_isolated("simplify", {}, 1)


def test_isolated_startup_failure_closes_both_pipe_ends(monkeypatch):
    parent, child = _Connection(), _Connection()
    process = _Process()
    process.start = lambda: (_ for _ in ()).throw(OSError("cannot start"))
    context = type("Context", (), {
        "Pipe": staticmethod(lambda duplex=False: (parent, child)),
        "Process": staticmethod(lambda **_kwargs: process),
    })()
    monkeypatch.setattr(cas_module.mp, "get_context", lambda _name: context)

    with pytest.raises(OSError, match="cannot start"):
        cas_module._run_isolated("simplify", {}, 1)

    assert parent.closed
    assert child.closed


def test_direct_isolated_cas_process_completes_a_small_operation():
    x=sp.Symbol("x")
    assert run_cas("simplify", {"expression": (x**2-1)/(x-1)}, isolated=True, timeout=10) == x+1
