from __future__ import annotations

import importlib

from scientific_calculator.calculator_engine import ScientificCalculatorEngine


def test_calculus_module_is_importable_and_exposed_by_the_engine():
    calculus = importlib.import_module("scientific_calculator.calculus")

    assert calculus.CalculusMixin in ScientificCalculatorEngine.__mro__
