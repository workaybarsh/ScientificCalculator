"""Tests for the successful worker-state commit boundary."""

from __future__ import annotations

from scientific_calculator.calculation_session import CalculationSession
from scientific_calculator.calculation_worker import CalculationPayload
from scientific_calculator.calculator_engine import ScientificCalculatorEngine
from scientific_calculator.history import CalculationHistoryEntry


def test_successful_payload_commits_ans_history_and_memory_as_copies() -> None:
    engine = ScientificCalculatorEngine()
    payload = CalculationPayload(
        result=5,
        ans=5,
        history=[CalculationHistoryEntry("2+3", "5")],
        memory={"M": 5},
    )

    CalculationSession(engine).apply_success(payload)
    payload.history.clear()
    payload.memory.clear()

    assert engine.ans == 5
    assert engine.history == [CalculationHistoryEntry("2+3", "5")]
    assert engine.memory == {"M": 5}
