from __future__ import annotations

from pathlib import Path

import pytest

from scientific_calculator.calculator_engine import ScientificCalculatorEngine
from scientific_calculator.history import CalculationHistoryEntry
from scientific_calculator.settings_store import SettingsStore


def test_symbolic_calculus_history_preserves_omitted_optional_fields() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)

    engine.symbolic_integral("sin(x)")
    integral = engine.history[-1]
    assert integral.kind == "integral_indefinite"
    assert integral.metadata["bounds"] is None

    engine.symbolic_derivative("x^3*sin(x)")
    derivative = engine.history[-1]
    assert derivative.kind == "derivative"
    assert derivative.metadata["evaluation_point"] is None


def test_complex_calculus_entries_keep_the_original_structured_inputs() -> None:
    engine = ScientificCalculatorEngine(cas_isolated=False)
    engine.complex_eval("1+i")
    evaluated = engine.history[-1]
    assert evaluated.kind == "complex_calculus"
    assert evaluated.metadata == {"operation": "evaluate", "expression": "1+i"}

    engine.complex_definite_integral("z", "0", "1")
    integral = engine.history[-1]
    assert integral.kind == "complex_calculus"
    assert integral.metadata["operation"] == "integral"
    assert integral.metadata["upper"] == "1"


def test_structured_history_round_trips_through_sqlite_and_legacy_rows_remain_readable(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.db")
    entries = [
        ("2+2", "4"),
        CalculationHistoryEntry(
            "∫0→inf exp(-x) dx",
            "1",
            "integral_single",
            {"integrand": "exp(-x)", "variables": ["x"], "bounds": [{"variable": "x", "lower": "0", "upper": "inf"}]},
        ),
    ]

    store.save_history(entries)
    restored = store.load_history()

    assert restored is not None
    assert restored[0] == ("2+2", "4")
    assert restored[0].kind == "legacy"
    assert restored[1] == entries[1]


def test_history_entries_validate_metadata_and_legacy_shapes() -> None:
    entry = CalculationHistoryEntry("x", "1", metadata={"items": [1, "a"], "nested": {"ok": True}, "ratio": 1.5})
    assert entry.metadata == {"items": (1, "a"), "nested": {"ok": True}, "ratio": 1.5}
    assert tuple(entry) == ("x", "1")
    assert len(entry) == 2
    assert entry[1] == "1"
    assert entry != []
    assert CalculationHistoryEntry.from_legacy(entry) is entry

    with pytest.raises(TypeError):
        CalculationHistoryEntry(1, "1")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        CalculationHistoryEntry("x", "1", metadata=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        CalculationHistoryEntry("x", "1", metadata={"bad": object()})
    with pytest.raises(ValueError):
        CalculationHistoryEntry.from_legacy(("only-one",))
    with pytest.raises(ValueError):
        CalculationHistoryEntry.from_legacy(("x", 1))


def test_history_store_rejects_large_metadata_and_malformed_json_rows(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.db")
    with pytest.raises(ValueError, match="metadata is too large"):
        store.save_history([CalculationHistoryEntry("x", "1", metadata={"long": "x" * 16385})])

    issues: list[tuple[str, Exception]] = []
    store = SettingsStore(tmp_path / "malformed.db", lambda operation, error: issues.append((operation, error)))
    store.save_history([("x", "1")])
    import sqlite3

    connection = sqlite3.connect(tmp_path / "malformed.db")
    connection.execute("UPDATE calculation_history SET metadata = ?", ("[]",))
    connection.commit()
    connection.close()
    assert store.load_history() is None
    assert issues[0][0] == "load history"
