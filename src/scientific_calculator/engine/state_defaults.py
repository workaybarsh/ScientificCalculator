"""Mutable engine-state defaults with explicit identity semantics."""

from __future__ import annotations

import sympy as sp


def default_memory() -> dict[str, sp.Expr]:
    return {name: sp.Integer(0) for name in "ABCDEFMxy"}


def reset_memory_values(memory: dict[str, sp.Expr]) -> None:
    for name in memory:
        memory[name] = sp.Integer(0)


def default_matrices() -> dict[str, None]:
    return {f"Mat{name}": None for name in "ABCD"}


def default_vectors() -> dict[str, None]:
    return {f"Vct{name}": None for name in "ABCD"}
