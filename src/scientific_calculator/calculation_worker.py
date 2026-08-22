"""Minimal, serializable entry points for isolated calculator operations."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .calculator_engine import CalculatorSettings, ScientificCalculatorEngine


@dataclass(frozen=True, slots=True)
class CalculationRequest:
    """Only the calculator state needed by a foreground calculation.

    Matrix, vector, spreadsheet, and Tk state are deliberately excluded.  In
    addition to making spawning faster, that gives the calculation controller
    one clear process owner: the process created for this request.
    """

    method: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    settings: CalculatorSettings
    ans: Any
    memory: dict[str, Any]
    history: tuple[tuple[str, str], ...]


@dataclass(slots=True)
class CalculationPayload:
    result: Any
    ans: Any
    history: list[tuple[str, str]]
    memory: dict[str, Any]


def build_calculation_request(
    engine: ScientificCalculatorEngine,
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> CalculationRequest:
    """Copy the small immutable-by-convention calculation boundary only."""
    return CalculationRequest(
        method=method,
        args=args,
        kwargs=dict(kwargs),
        settings=copy.copy(engine.settings),
        ans=engine.ans,
        memory=dict(engine.memory),
        history=tuple(engine.history),
    )


def run_calculation(request: CalculationRequest) -> CalculationPayload:
    """Run a request in the controller-owned worker process.

    CAS calls run inline here: the controller can cancel this one process, so
    no descendant process can survive a cancelled UI operation.
    """
    engine = ScientificCalculatorEngine(
        settings=copy.copy(request.settings),
        ans=request.ans,
        memory=dict(request.memory),
        history=list(request.history),
        cas_isolated=False,
        cas_timeout=None,
    )
    result = getattr(engine, request.method)(*request.args, **request.kwargs)
    return CalculationPayload(result, engine.ans, list(engine.history), dict(engine.memory))
