from __future__ import annotations

import pytest

from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine
from scientific_calculator.spreadsheet import SpreadsheetModel


@pytest.fixture
def sheet() -> SpreadsheetModel:
    engine = ScientificCalculatorEngine()
    engine.settings.spreadsheet_auto_calc = True
    return SpreadsheetModel(engine)


def test_address_boundaries_and_normalization(sheet: SpreadsheetModel) -> None:
    for address in ("A1", "E45", "$A$1", "$e$45"):
        assert sheet.valid(address)

    assert sheet.normalize_addr("$e$45") == "E45"
    assert sheet.value("A1") == 0.0

    for address in ("A0", "A46", "F1", "AA1", "1A", ""):
        assert not sheet.valid(address)
        with pytest.raises(CalculatorError, match="Range ERROR"):
            sheet.set(address, "1")

    assert not sheet.valid(None)
    with pytest.raises(CalculatorError, match="Range ERROR"):
        sheet.value(None)


def test_formulas_references_ranges_and_aggregates(sheet: SpreadsheetModel) -> None:
    sheet.set("A1", "1")
    sheet.set("A2", "2")
    sheet.set("A3", "3")
    sheet.set("B1", "=A1+A2*A3")
    sheet.set("B2", "=Sum(A1:A3)")
    sheet.set("B3", "=Mean($A$1:$A$3)")
    sheet.set("B4", "=Min(A3:A1)")
    sheet.set("B5", "=Max(A3:A1)")
    sheet.set("C1", "=E45+1")

    assert sheet.cache["B1"] == pytest.approx(7)
    assert sheet.cache["B2"] == pytest.approx(6)
    assert sheet.cache["B3"] == pytest.approx(2)
    assert sheet.cache["B4"] == pytest.approx(1)
    assert sheet.cache["B5"] == pytest.approx(3)
    assert sheet.cache["C1"] == pytest.approx(1)
    assert sheet.value("B2") == pytest.approx(6)


def test_spreadsheet_evaluation_preserves_ans_and_history(
    sheet: SpreadsheetModel,
) -> None:
    sheet.engine.evaluate("6*7")
    saved_ans = sheet.engine.ans
    history_object = sheet.engine.history
    saved_history = list(history_object)

    sheet.set("A1", "=Ans+1")
    assert sheet.cache["A1"] == pytest.approx(43)
    assert sheet.engine.ans == saved_ans
    assert sheet.engine.history is history_object
    assert sheet.engine.history == saved_history
    assert sheet.value("A1") == pytest.approx(43)
    sheet.recalculate()
    assert sheet.engine.ans == saved_ans
    assert sheet.engine.history is history_object
    assert sheet.engine.history == saved_history


def test_manual_calculation_marks_cached_values_stale_until_recalculated(sheet):
    sheet.set("A1", "2")
    sheet.set("B1", "=A1+1")
    sheet.engine.settings.spreadsheet_auto_calc = False
    sheet.set("A1", "5")

    assert sheet.needs_recalculation is True
    assert {"A1", "B1"}.issubset(sheet.dirty_cells)
    assert sheet.cache["B1"] == pytest.approx(3)

    sheet.recalculate()
    assert sheet.needs_recalculation is False
    assert not sheet.dirty_cells
    assert sheet.cache["B1"] == pytest.approx(6)


def test_recalculation_memoizes_shared_dependencies_within_one_pass(sheet, monkeypatch):
    sheet.engine.settings.spreadsheet_auto_calc = False
    sheet.set("A1", "2")
    sheet.set("B1", "=A1+1")
    sheet.set("C1", "=A1+B1")
    calls = []
    original_evaluate = sheet._evaluate

    def observed_evaluate(expression):
        calls.append(expression)
        return original_evaluate(expression)

    monkeypatch.setattr(sheet, "_evaluate", observed_evaluate)
    sheet.recalculate()

    assert sheet.cache == {"A1": 2.0, "B1": 3.0, "C1": 5.0}
    assert len(calls) == 3

def test_set_rolls_back_on_formula_errors_and_cycles(
    sheet: SpreadsheetModel,
) -> None:
    sheet.set("A1", "5")
    original_cells = dict(sheet.cells)
    original_cache = dict(sheet.cache)

    with pytest.raises(CalculatorError, match="Circular ERROR"):
        sheet.set("A1", "=A1+1")
    assert sheet.cells == original_cells
    assert sheet.cache == original_cache

    with pytest.raises(CalculatorError):
        sheet.set("A1", "=unknown(1)")
    assert sheet.cells == original_cells
    assert sheet.cache == original_cache

    sheet.set("B1", "=C1+1")
    before_indirect_cycle = dict(sheet.cells)
    before_indirect_cache = dict(sheet.cache)
    with pytest.raises(CalculatorError, match="Circular ERROR"):
        sheet.set("C1", "=B1+1")
    assert sheet.cells == before_indirect_cycle
    assert sheet.cache == before_indirect_cache


def test_manual_recalculation_is_transactional_on_cycle(
    sheet: SpreadsheetModel,
) -> None:
    sheet.engine.settings.spreadsheet_auto_calc = False
    sheet.set("A1", "5")
    sheet.recalculate()
    old_cache = dict(sheet.cache)

    sheet.set("A1", "=A1+1")
    assert sheet.cache == old_cache
    with pytest.raises(CalculatorError, match="Circular ERROR"):
        sheet.recalculate()
    assert sheet.cache == old_cache


def test_per_cell_and_total_memory_limits_are_byte_based_and_transactional(
    sheet: SpreadsheetModel,
) -> None:
    sheet.engine.settings.spreadsheet_auto_calc = False

    sheet.set("A1", "1234567890")
    with pytest.raises(CalculatorError, match="sabit 10 baytı"):
        sheet.set("A2", "12345678901")

    sheet.set("A2", "é" * 5)
    with pytest.raises(CalculatorError, match="sabit 10 baytı"):
        sheet.set("A3", "é" * 6)

    sheet.set("A3", "=" + "1" * 49)
    with pytest.raises(CalculatorError, match="formül 49 baytı"):
        sheet.set("A4", "=" + "1" * 50)

    full = SpreadsheetModel(sheet.engine)
    full.fill_value("A1", "D21", "1234567890")
    full.set("E1", "")
    full.set("E2", "")
    assert full.memory_used() == 1700
    assert full.free_space() == 0

    original_cells = dict(full.cells)
    with pytest.raises(CalculatorError, match="Memory ERROR"):
        full.set("E2", "1")
    assert full.cells == original_cells
    assert full.cells["E2"] == ""
    assert full.memory_used() == 1700


def test_copy_shifts_mixed_references_and_is_transactional(
    sheet: SpreadsheetModel,
) -> None:
    sheet.set("A1", "10")
    sheet.set("B1", "=$A$1+A1+$A1+A$1")
    sheet.copy("B1", "C2")

    assert sheet.cells["C2"] == "=$A$1+B2+$A2+B$1"
    assert sheet.cache["B1"] == pytest.approx(40)
    assert sheet.cache["C2"] == pytest.approx(50)

    before_cells = dict(sheet.cells)
    before_cache = dict(sheet.cache)
    with pytest.raises(CalculatorError, match="Range ERROR"):
        sheet.copy("B1", "A1")
    assert sheet.cells == before_cells
    assert sheet.cache == before_cache


def test_cut_to_self_is_a_no_op(sheet: SpreadsheetModel) -> None:
    sheet.set("A1", "7")
    cells_object = sheet.cells
    cache_object = sheet.cache
    original_cells = dict(sheet.cells)
    original_cache = dict(sheet.cache)

    sheet.cut("$a$1", "A1")

    assert sheet.cells is cells_object
    assert sheet.cache is cache_object
    assert sheet.cells == original_cells
    assert sheet.cache == original_cache


def test_fill_delete_and_delete_all(sheet: SpreadsheetModel) -> None:
    sheet.fill_value("A1", "B2", 2)
    assert {key: sheet.cells[key] for key in ("A1", "B1", "A2", "B2")} == {
        "A1": "2",
        "B1": "2",
        "A2": "2",
        "B2": "2",
    }
    assert all(sheet.cache[key] == pytest.approx(2) for key in sheet.cells)

    sheet.fill_formula("C1", "C2", "=A1+B1")
    assert sheet.cells["C1"] == "=A1+B1"
    assert sheet.cells["C2"] == "=A2+B2"
    assert sheet.cache["C1"] == pytest.approx(4)
    assert sheet.cache["C2"] == pytest.approx(4)

    sheet.delete("A1")
    assert "A1" not in sheet.cells
    assert "A1" not in sheet.cache
    assert sheet.cache["C1"] == pytest.approx(2)

    sheet.delete_all()
    assert sheet.cells == {}
    assert sheet.cache == {}


def test_fill_rolls_back_as_one_transaction(sheet: SpreadsheetModel) -> None:
    sheet.set("D1", "9")
    original_cells = dict(sheet.cells)
    original_cache = dict(sheet.cache)

    with pytest.raises(CalculatorError, match="Circular ERROR"):
        sheet.fill_formula("A1", "A2", "=A1")

    assert sheet.cells == original_cells
    assert sheet.cache == original_cache


def test_auto_calc_on_and_off(sheet: SpreadsheetModel) -> None:
    sheet.engine.settings.spreadsheet_auto_calc = False
    sheet.set("A1", "1")
    assert sheet.cache == {}

    assert sheet.recalculate() == {"A1": pytest.approx(1)}
    sheet.set("A1", "2")
    assert sheet.cache["A1"] == pytest.approx(1)
    sheet.delete("A1")
    assert "A1" not in sheet.cache
    assert sheet.dirty_cells == set()
    assert sheet.needs_recalculation is False
    assert sheet.recalculate() == {}

    sheet.engine.settings.spreadsheet_auto_calc = True
    sheet.set("B1", "3")
    assert sheet.cache == {"B1": pytest.approx(3)}
    sheet.set("B1", "4")
    assert sheet.cache == {"B1": pytest.approx(4)}
