"""Regression coverage for bounded matrix, vector, and mapping API inputs."""
from __future__ import annotations

import math
from collections.abc import Mapping
from itertools import repeat

import numpy as np
import pytest
import sympy as sp

import scientific_calculator.calculator_engine as engine_module
from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine() -> ScientificCalculatorEngine:
    return ScientificCalculatorEngine(cas_isolated=False)


class _InfiniteItemsMapping(Mapping[object, object]):
    """A deliberately dishonest Mapping: ``len`` is zero but its items never end."""

    def __getitem__(self, key: object) -> object:
        raise KeyError(key)

    def __iter__(self):
        return iter(())

    def __len__(self) -> int:
        return 0

    def items(self):
        return repeat(("x", 1))


class _BrokenItemsMapping(_InfiniteItemsMapping):
    def items(self):
        raise RuntimeError("items failed")


class _MalformedItemsMapping(_InfiniteItemsMapping):
    def items(self):
        return iter((["x", 1],))


class _FailingRegistry(dict[str, object]):
    """Model a corrupted persisted registry whose lookup fails predictably."""

    def get(self, _key: object, _default: object = None) -> object:
        raise ValueError("registry lookup failed")


def test_matrix_and_vector_public_apis_reject_oversized_lazy_inputs_before_numpy_conversion(engine, monkeypatch):
    def unexpected_conversion(*_args, **_kwargs):
        raise AssertionError("NumPy conversion should not run for an oversized input")

    monkeypatch.setattr(engine_module.np, "asarray", unexpected_conversion)

    operations = [
        lambda: engine.define_matrix("MatA", repeat((1, 2))),
        lambda: engine.matrix_op("trn", repeat((1, 2))),
        lambda: engine.define_vector("VctA", repeat(1)),
        lambda: engine.vector_op("abs", repeat(1)),
    ]

    for operation in operations:
        with pytest.raises(CalculatorError, match="Dimension ERROR"):
            operation()


def test_matrix_and_vector_public_apis_reject_oversized_arrays_before_dtype_copy(engine, monkeypatch):
    matrices = np.ones((5, 5))
    vectors = np.arange(4)

    def unexpected_conversion(*_args, **_kwargs):
        raise AssertionError("NumPy conversion should not run for an oversized input")

    monkeypatch.setattr(engine_module.np, "asarray", unexpected_conversion)

    operations = [
        lambda: engine.define_matrix("MatA", matrices),
        lambda: engine.matrix_op("trn", matrices),
        lambda: engine.define_vector("VctA", vectors),
        lambda: engine.vector_op("abs", vectors),
    ]

    for operation in operations:
        with pytest.raises(CalculatorError, match="Dimension ERROR"):
            operation()


def test_matrix_and_vector_apis_accept_bounded_lazy_values(engine):
    matrix = engine.define_matrix("MatA", (iter(row) for row in ((1, 2), (3, 4))))
    vector = engine.define_vector("VctA", (value for value in (3, 4)))

    np.testing.assert_allclose(matrix, [[1, 2], [3, 4]])
    np.testing.assert_allclose(engine.matrix_op("trn", (iter(row) for row in ((1, 2), (3, 4)))), [[1, 3], [2, 4]])
    np.testing.assert_allclose(vector, [3, 4])
    assert engine.vector_op("abs", (value for value in (3, 4))) == pytest.approx(5)


def test_matrix_and_vector_array_shape_and_conversion_boundaries(engine):
    # A NumPy scalar must take the ndarray fast path, then be rejected as a
    # non-matrix rather than accidentally becoming a one-item matrix.
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.define_matrix("MatA", np.array(1))
    # Zero rows are within the allocation cap but still not a usable matrix.
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.define_matrix("MatA", np.empty((0, 2)))
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.define_matrix("MatA", np.empty((5, 0)))
    with pytest.raises(CalculatorError, match="Dimension ERROR"):
        engine.define_vector("VctA", np.array(1))
    with pytest.raises(CalculatorError, match="geçersiz matris verisi"):
        engine.define_matrix("MatA", [["not-a-number"]])
    with pytest.raises(CalculatorError, match="geçersiz vektör verisi"):
        engine.define_vector("VctA", ["not-a-number", 1])


def test_matrix_and_vector_operations_normalize_corrupted_registry_lookup_failures(engine):
    """A damaged persisted registry must not leak its implementation exception."""
    engine.matrices = _FailingRegistry()
    with pytest.raises(CalculatorError, match="geçersiz matris verisi"):
        engine.matrix_op("trn", "MatA")

    engine.vectors = _FailingRegistry()
    with pytest.raises(CalculatorError, match="geçersiz vektör verisi"):
        engine.vector_op("abs", "VctA")


def test_stored_matrix_and_vector_inputs_are_copied_and_revalidated_before_operations(engine):
    matrix_source = np.array([[1.0, 2.0], [3.0, 4.0]])
    matrix_result = engine.define_matrix("MatA", matrix_source)
    matrix_source[0, 0] = 99
    matrix_result[0, 1] = 88
    np.testing.assert_allclose(engine.matrix_op("trn", "MatA"), [[1, 3], [2, 4]])

    engine.matrices["MatA"].resize((5, 5), refcheck=False)
    with pytest.raises(CalculatorError, match="matris verileri geçersiz"):
        engine.matrix_op("trn", "MatA")

    engine.define_matrix("MatA", [[1]])
    engine.define_matrix("MatB", [[2]])
    engine.matrices["MatB"].resize((5, 5), refcheck=False)
    with pytest.raises(CalculatorError, match="matris verileri geçersiz"):
        engine.matrix_op("+", "MatA", "MatB")

    vector_source = np.array([3.0, 4.0])
    vector_result = engine.define_vector("VctA", vector_source)
    vector_source[0] = 99
    vector_result[1] = 88
    assert engine.vector_op("abs", "VctA") == pytest.approx(5)

    engine.vectors["VctA"].resize(4, refcheck=False)
    with pytest.raises(CalculatorError, match="vektör verileri geçersiz"):
        engine.vector_op("abs", "VctA")

    engine.define_vector("VctA", [1, 2])
    engine.define_vector("VctB", [3, 4])
    engine.vectors["VctB"].resize(4, refcheck=False)
    with pytest.raises(CalculatorError, match="vektör verileri geçersiz"):
        engine.vector_op("+", "VctA", "VctB")


def test_bounded_mapping_items_handles_malformed_and_failed_mapping_views():
    kwargs = {
        "maximum": 2,
        "invalid_message": "invalid mapping",
        "limit_message": "too many mappings",
    }

    assert engine_module._bounded_mapping_items({"x": 1}, **kwargs) == [("x", 1)]
    for mapping in (object(), _BrokenItemsMapping(), _MalformedItemsMapping()):
        with pytest.raises(CalculatorError, match="invalid mapping"):
            engine_module._bounded_mapping_items(mapping, **kwargs)


def test_mapping_entry_limits_do_not_trust_len_and_leave_evaluation_state_unchanged(engine):
    engine.ans = sp.Integer(7)
    engine.history = [("seed", "7")]

    with pytest.raises(CalculatorError, match="too many variable values"):
        engine.evaluate_with_values("x+1", _InfiniteItemsMapping())
    with pytest.raises(CalculatorError, match="too many known values"):
        engine.solve("x=1", known_values=_InfiniteItemsMapping())

    assert engine.ans == 7
    assert engine.history == [("seed", "7")]


def test_solve_rejects_nonstring_bounded_known_value_names(engine):
    with pytest.raises(CalculatorError, match="known value names"):
        engine.solve("x=1", known_values={1: 1})

    with pytest.raises(CalculatorError, match="known values must be finite and real"):
        engine.solve("A*x=1", known_values={"A": math.inf})
