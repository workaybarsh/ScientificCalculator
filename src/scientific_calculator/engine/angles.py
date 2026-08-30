"""Stateless conversion between calculator angle units and radians."""

from __future__ import annotations

import sympy as sp


def angle_to_radians(value: object, angle_unit: str) -> object:
    """Convert a calculator angle to radians without retaining settings state."""
    if angle_unit == "DEG":
        return value * sp.pi / 180
    if angle_unit == "GRA":
        return value * sp.pi / 200
    return value


def radians_to_angle(value: object, angle_unit: str) -> object:
    """Convert radians to the selected calculator angle unit."""
    if angle_unit == "DEG":
        return value * 180 / sp.pi
    if angle_unit == "GRA":
        return value * 200 / sp.pi
    return value
