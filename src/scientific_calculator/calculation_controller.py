"""Cancellation-first, single-process controller used by the Tk application."""
from __future__ import annotations

import multiprocessing as mp
import time
from collections.abc import Callable
from contextlib import suppress
from multiprocessing.connection import Connection
from typing import Any

from .calculation_errors import CalculationTimeout, WorkerCrashed, WorkerProtocolError
from .calculation_worker import CalculationPayload, CalculationRequest, build_calculation_request, run_calculation
from .calculator_engine import CalculatorError, ScientificCalculatorEngine


def _worker(connection: Connection, request: CalculationRequest) -> None:
    try:
        response = ("ok", run_calculation(request))
    except CalculatorError as exc:
        response = ("input_error", str(exc)[:500])
    except CalculationTimeout as exc:
        response = ("timeout", str(exc)[:500])
    except BaseException as exc:
        response = ("crash", type(exc).__name__, str(exc)[:500])
    try:
        connection.send(response)
    except (BrokenPipeError, EOFError, OSError):
        # The controller may have cancelled and closed the receiving end.  A
        # response is no longer useful, and retrying it would only create a
        # noisy child-process traceback during normal shutdown.
        pass
    finally:
        connection.close()


class CalculationController:
    """Own one cancellable foreground process and discard stale completions."""

    _KILL_AFTER_CLEANUP_ATTEMPTS = 20
    _MAX_CLEANUP_ATTEMPTS = 40

    def __init__(self, scheduler: Any, poll_ms: int = 50, timeout_seconds: float | None = 30.0):
        self.scheduler, self.poll_ms, self.timeout_seconds = scheduler, poll_ms, timeout_seconds
        self._operation_id = 0
        self._active_id: int | None = None
        # ``spawn`` returns platform-specific Process/Connection subclasses
        # whose precise types are not modeled consistently by Pyright.
        self._process: Any = None
        self._connection: Any = None
        self._callbacks = None
        self._started_at: float | None = None

    @property
    def busy(self) -> bool:
        return self._active_id is not None

    def start_engine_method(self, engine: ScientificCalculatorEngine, method: str, *args: Any, on_start: Callable[[], None], on_success: Callable[[CalculationPayload], None], on_error: Callable[[Exception], None], on_finish: Callable[[], None], **kwargs: Any) -> bool:
        if self.busy:
            return False
        self._operation_id += 1
        operation_id = self._operation_id
        context = mp.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        try:
            request = build_calculation_request(engine, method, args, kwargs)
            process = context.Process(target=_worker, args=(child, request))
            process.start()
        except Exception:
            parent.close(); child.close()
            raise
        child.close()
        self._active_id, self._process, self._connection = operation_id, process, parent
        self._started_at = time.monotonic()
        self._callbacks = (on_start, on_success, on_error, on_finish)
        try:
            on_start()
            self.scheduler.after(self.poll_ms, lambda: self._poll(operation_id))
        except Exception:
            # Startup is transactional: callback or scheduler errors cannot
            # strand a worker or leave the controller permanently busy.
            callbacks, process, connection = self._detach()
            self._schedule_cleanup(process, connection, terminate=True)
            if callbacks:
                callbacks[3]()
            raise
        return True

    def _poll(self, operation_id: int) -> None:
        if operation_id != self._active_id or not self._connection or not self._process:
            return
        try:
            if (
                self.timeout_seconds is not None
                and self._started_at is not None
                and time.monotonic() - self._started_at > self.timeout_seconds
            ):
                self._finish_error(CalculationTimeout("Calculation timed out"), terminate=True)
                return
            if not self._connection.poll():
                if self._process.is_alive():
                    self.scheduler.after(self.poll_ms, lambda: self._poll(operation_id)); return
                self._finish_error(WorkerCrashed(f"Calculation worker exited with code {self._process.exitcode}")); return
            response = self._connection.recv()
        except (EOFError, OSError, ValueError):
            self._finish_error(WorkerCrashed("Calculation worker closed without a result")); return
        if response and response[0] == "ok":
            self._finish_success(response[1])
        elif response and response[0] == "input_error" and len(response) == 2:
            self._finish_error(CalculatorError(response[1]))
        elif response and response[0] == "timeout" and len(response) == 2:
            self._finish_error(CalculationTimeout(response[1]))
        elif response and response[0] == "crash" and len(response) == 3:
            self._finish_error(WorkerCrashed(f"{response[1]}: {response[2]}"))
        else:
            self._finish_error(WorkerProtocolError("Invalid calculation worker response"))

    def _detach(self):
        callbacks = self._callbacks
        process, connection = self._process, self._connection
        self._callbacks = None; self._active_id = None; self._process = self._connection = None; self._started_at = None
        return callbacks, process, connection

    @staticmethod
    def _stop_without_wait(process: Any) -> None:
        """Best-effort emergency cleanup that never blocks the Tk thread."""
        try:
            if process.is_alive():
                process.terminate()
            process.join(0)
        except (OSError, ValueError):
            pass

    def _schedule_cleanup(self, process: Any, connection: Any, *, terminate: bool) -> None:
        if connection:
            with suppress(OSError, ValueError):
                connection.close()
        if not process:
            return
        try:
            self.scheduler.after(0, lambda: self._poll_cleanup(process, terminate, 0))
        except Exception:
            self._stop_without_wait(process)

    def _poll_cleanup(self, process: Any, terminate: bool, attempts: int, *, killed: bool = False) -> None:
        """Reap a detached worker in small scheduler turns, never with waits."""
        try:
            if terminate and attempts == 0 and process.is_alive():
                process.terminate()
            process.join(0)
            if not process.is_alive():
                with suppress(OSError, ValueError):
                    process.close()
                return
            if attempts >= self._MAX_CLEANUP_ATTEMPTS:
                # A pathological OS process must not retain an endless Tk
                # callback chain.  It was already terminated/killed below;
                # stop scheduling and let the OS finish reaping it.
                if not killed:
                    self._stop_without_wait(process)
                return
            if not killed and attempts >= self._KILL_AFTER_CLEANUP_ATTEMPTS and hasattr(process, "kill"):
                process.kill()
                killed = True
            self.scheduler.after(25, lambda: self._poll_cleanup(process, terminate, attempts + 1, killed=killed))
        except (OSError, ValueError):
            return

    def _finish_success(self, payload: CalculationPayload) -> None:
        callbacks, process, connection = self._detach()
        self._schedule_cleanup(process, connection, terminate=False)
        if callbacks:
            _start, success, _error, finish = callbacks
            try: success(payload)
            finally: finish()

    def _finish_error(self, error: Exception, *, terminate: bool = False) -> None:
        callbacks, process, connection = self._detach()
        self._schedule_cleanup(process, connection, terminate=terminate)
        if callbacks:
            _start, _success, failure, finish = callbacks
            try: failure(error)
            finally: finish()

    def cancel(self) -> bool:
        if not self.busy: return False
        self._operation_id += 1
        callbacks, process, connection = self._detach()
        self._schedule_cleanup(process, connection, terminate=True)
        if callbacks: callbacks[3]()
        return True

    def close(self) -> bool:
        """Stop and reap the active worker before the Tk scheduler is destroyed.

        ``cancel`` intentionally schedules non-blocking reaping so normal UI
        interaction stays responsive.  During application shutdown that
        callback may never run, so closing needs a bounded synchronous path.
        """
        if not self.busy:
            return False
        self._operation_id += 1
        callbacks, process, connection = self._detach()
        if connection:
            with suppress(OSError, ValueError):
                connection.close()
        if process:
            try:
                if process.is_alive():
                    process.terminate()
                process.join(0.5)
                if process.is_alive() and hasattr(process, "kill"):
                    process.kill()
                    process.join(0.5)
                if not process.is_alive():
                    with suppress(OSError, ValueError):
                        process.close()
            except (OSError, ValueError):
                pass
        if callbacks:
            with suppress(Exception):
                callbacks[3]()
        return True
