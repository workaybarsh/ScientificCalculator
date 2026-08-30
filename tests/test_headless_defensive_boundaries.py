"""Defensive engine, store, and spreadsheet boundaries without the UI.

These tests cover inputs and cleanup states that are realistic at public
boundaries (corrupt persisted data, malformed spreadsheet input, and stale
worker handles).  They deliberately avoid Tk/UI routing so engine and model
behaviour stays independently verifiable.
"""
from __future__ import annotations

import ast
import importlib
import math
import sqlite3
import sys

import numpy as np
import pytest
import sympy as sp

import scientific_calculator.app as app_module
import scientific_calculator.calculator_engine as engine_module
import scientific_calculator.engine.expression_parser as parser_module
from scientific_calculator.calculation_controller import CalculationController
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine
from scientific_calculator.numeric_validation import (
    finite_complex,
    finite_real_float,
    is_known_nonfinite,
)
from scientific_calculator.settings_store import DatabaseMigrationError, SettingsStore
from scientific_calculator.spreadsheet import SpreadsheetModel


class _FloatInfinity:
    def __float__(self) -> float:
        return math.inf


class _ComplexInfinity:
    def __complex__(self) -> complex:
        return complex(math.inf, 0)


class _DeadProcess:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def is_alive(self) -> bool:
        self.calls.append("is_alive")
        return False

    def join(self, timeout: float) -> None:
        self.calls.append(("join", timeout))


class _StubbornProcess:
    """A process handle that remains live and has no force-kill operation."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def is_alive(self) -> bool:
        self.calls.append("is_alive")
        return True

    def terminate(self) -> None:
        self.calls.append("terminate")

    def join(self, timeout: float) -> None:
        self.calls.append(("join", timeout))


class _Scheduler:
    def after(self, _milliseconds: int, _callback) -> None:
        raise AssertionError("close() must not schedule cleanup work")


def _engine() -> ScientificCalculatorEngine:
    # Unit tests run deterministic CAS operations in-process.  UI requests use
    # their own process boundary and are tested separately.
    return ScientificCalculatorEngine(cas_isolated=False)


def test_numeric_validation_rejects_values_that_become_nonfinite_on_conversion() -> None:
    # NumPy scalar integers use their own numeric branch, while arbitrary
    # conversion objects must still be rejected after they produce infinity.
    assert is_known_nonfinite(np.int64(7)) is False

    with pytest.raises(CalculatorError, match="non-finite"):
        finite_real_float(_FloatInfinity(), "non-finite")
    with pytest.raises(CalculatorError, match="non-finite"):
        finite_complex(_ComplexInfinity(), "non-finite")


def test_settings_store_reports_unsupported_schema_and_unknown_migration(tmp_path) -> None:
    path = tmp_path / "settings.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("INSERT INTO meta (key, value) VALUES ('db_schema_version', '4')")
    connection.commit()
    connection.close()

    issues: list[tuple[str, Exception]] = []
    store = SettingsStore(path, lambda operation, error: issues.append((operation, error)))
    assert store.load() is None
    assert issues[0][0] == "load"
    assert isinstance(issues[0][1], DatabaseMigrationError)

    with pytest.raises(DatabaseMigrationError, match="no migration"):
        store._migrate(sqlite3.connect(":memory:"), 3)


def test_spreadsheet_boundary_validation_and_literal_copy() -> None:
    sheet = SpreadsheetModel(_engine())

    with pytest.raises(CalculatorError, match="Range ERROR"):
        sheet.normalize_addr(None)  # type: ignore[arg-type]
    with pytest.raises(CalculatorError, match="Syntax ERROR"):
        sheet.set("A1", 1)  # type: ignore[arg-type]

    sheet.set("A1", "7")
    sheet.copy("A1", "B1")
    assert sheet.cells["B1"] == "7"
    assert sheet.cache["B1"] == pytest.approx(7)


def test_importing_module_entrypoint_does_not_start_gui(monkeypatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(app_module, "main", lambda: calls.append(True))

    sys.modules.pop("scientific_calculator.__main__", None)
    try:
        importlib.import_module("scientific_calculator.__main__")

        assert calls == []
    finally:
        # Leave the process-wide module cache in the same state in which the
        # test found it.  Later runpy tests execute the entry point under a
        # synthetic __main__ name and should not emit a misleading warning.
        sys.modules.pop("scientific_calculator.__main__", None)


def test_controller_close_handles_stubborn_and_partially_detached_workers() -> None:
    # A dead handle must be joined without an unnecessary terminate call.
    dead = _DeadProcess()
    CalculationController._stop_without_wait(dead)
    assert dead.calls == ["is_alive", ("join", 0)]

    # During shutdown a process can survive terminate and no longer expose
    # kill().  The controller still releases the UI callback and returns.
    controller = CalculationController(_Scheduler())
    finished: list[bool] = []
    stubborn = _StubbornProcess()
    controller._active_id = 1
    controller._process = stubborn
    controller._callbacks = (lambda: None, lambda _payload: None, lambda _error: None, lambda: finished.append(True))

    assert controller.close() is True
    assert "terminate" in stubborn.calls
    assert ("join", 0.5) in stubborn.calls
    assert finished == [True]
    assert controller.busy is False

    # A pipe may be detached before its process object during exceptional
    # startup.  This is still a successful, idempotent close operation.
    controller._active_id = 2
    assert controller.close() is True


def test_engine_numeric_guard_helpers_cover_exact_input_boundaries() -> None:
    assert parser_module.exact_nonnegative_integer(True) is None
    assert parser_module.exact_nonnegative_integer(sp.Rational(2, 1)) == 2
    assert parser_module.exact_nonnegative_integer(sp.Integer(-1)) is None
    assert parser_module.estimated_factorial_digits(1) == 1
    assert engine_module._estimated_combinatoric_digits(4, 2, permutation=True) == 2

    assert parser_module.constant_numeric_approx(ast.parse("'1.25'", mode="eval").body) == pytest.approx(1.25)
    assert parser_module.constant_numeric_approx(ast.parse("factorial(-1)", mode="eval").body) is None
    assert parser_module.constant_numeric_approx(ast.parse("nPr(3, 2)", mode="eval").body) == pytest.approx(6)
    assert parser_module.constant_numeric_approx(ast.parse("nCr(3, 4)", mode="eval").body) is None

    assert parser_module.evaluated_numeric_approx(True) is None
    assert parser_module.evaluated_numeric_approx(np.int64(4)) == pytest.approx(4)
    assert parser_module.evaluated_numeric_approx(sp.Symbol("x")) is None
    assert parser_module.evaluated_numeric_approx(sp.nan) == math.inf
    with pytest.raises(CalculatorError, match="integer"):
        engine_module._finite_exact_integer(True, "integer")
    assert engine_module._finite_exact_integer(2.0, "integer") == 2
    with pytest.raises(CalculatorError, match="integer"):
        engine_module._finite_exact_integer(2.5, "integer")


def test_engine_parser_accepts_calculator_percent_boundaries_and_blocks_attributes() -> None:
    engine = _engine()

    assert engine._percent_operand_start("") is None
    assert engine._percent_operand_start(")") is None
    assert engine._percent_operand_start("sin(1)") == 0
    assert engine._percent_operand_start("5!") == 0
    assert engine.evaluate("2(3)%") == sp.Rational(3, 50)
    assert engine.evaluate("5!%") == sp.Rational(6, 5)
    with pytest.raises(CalculatorError, match="Özellik erişimine"):
        engine.parse("x.real")


def test_engine_supports_rad_defaults_and_signed_base_formats() -> None:
    engine = _engine()

    assert engine._rad_to_angle(sp.pi / 3) == sp.pi / 3
    assert engine.pol(0, 1) == pytest.approx((1, math.pi / 2))
    assert engine.rec(1, math.pi / 2) == pytest.approx((0, 1), abs=1e-12)
    assert engine.complex_argument(1j) == pytest.approx(math.pi / 2)
    assert engine.from_polar(1, math.pi / 2) == pytest.approx(1j)

    assert engine.parse_base_token("FFFFFFFF", 16) == -1
    assert engine.format_base(-1, 8) == "37777777777"
    assert engine.format_base(-1, 2) == "11111111111111111111111111111111"
    assert engine.evaluate_base("d7/d2", 10) == 3
    with pytest.raises(CalculatorError, match="division by zero"):
        engine.evaluate_base("1/0", 10)


def test_engine_custom_solve_random_and_memory_paths_are_publicly_safe() -> None:
    engine = _engine()

    root, residual = engine.solve("z^2-4", variable="z", guess=1)
    assert root == pytest.approx(2)
    assert residual == pytest.approx(0)
    assert "z" not in engine.memory

    assert 0 <= engine.random_number() < 1
    assert engine.random_int("2", "2") == 2
    with pytest.raises(CalculatorError, match="lower bound"):
        engine.random_int(3, 2)
    with pytest.raises(CalculatorError, match="Geçersiz bellek"):
        engine.store("not-a-memory")
    with pytest.raises(CalculatorError, match="invalid memory value"):
        engine.store("A", object())


def test_engine_complex_symbolic_format_keeps_unknown_imaginary_part_unambiguous() -> None:
    engine = _engine()
    y = sp.Symbol("y")

    assert engine.format_result(sp.I * y) == "i*y"


def test_engine_auxiliary_modes_reject_malformed_values_at_their_public_boundaries() -> None:
    engine = _engine()

    with pytest.raises(CalculatorError, match="FACT"):
        engine.prime_factorization("not_an_integer")
    with pytest.raises(CalculatorError, match="tabanlı sayı"):
        engine.parse_base_token("G", 16)
    with pytest.raises(CalculatorError, match="Base-N"):
        engine.evaluate_base("d1 @ d1", 10)

    with pytest.raises(CalculatorError, match="geçersiz matris verisi"):
        engine.define_matrix("MatA", object())
    with pytest.raises(CalculatorError, match="matris verileri geçersiz"):
        engine.matrix_op("+", [[1]], [[math.inf]])
    with pytest.raises(CalculatorError, match="geçersiz vektör verisi"):
        engine.define_vector("VctA", object())
    with pytest.raises(CalculatorError, match="vektör verileri geçersiz"):
        engine.vector_op("+", [1], [1])
    with pytest.raises(CalculatorError, match="vektör verileri geçersiz"):
        engine.vector_op("+", [1, 2], [[3, 4]])
    with pytest.raises(CalculatorError, match="vektör verileri geçersiz"):
        engine.vector_op("+", [1, 2], [math.inf, 4])

    with pytest.raises(CalculatorError, match="geçersiz veri"):
        engine.one_var_stats(object())
    with pytest.raises(CalculatorError, match="geçersiz frekans"):
        engine.one_var_stats([1, 2], freq=object())
    with pytest.raises(CalculatorError, match="geçersiz regresyon verisi"):
        engine.regression(object(), [1, 2])
    with pytest.raises(CalculatorError, match="Argument ERROR: sigma"):
        engine.distribution("Normal PD", x=0, mu=0)
    with pytest.raises(CalculatorError, match="sonlu olmalıdır"):
        engine.distribution("Normal PD", x=0, mu=0, sigma=math.inf)
    with pytest.raises(CalculatorError, match="geçersiz denklem verisi"):
        engine.simultaneous(object(), [1, 2])
    with pytest.raises(CalculatorError, match="Argument ERROR"):
        engine.inequality(object(), ">")
