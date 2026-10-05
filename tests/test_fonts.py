"""Behavioural tests for the widget-independent font family resolution."""

from __future__ import annotations

import scientific_calculator.fonts as fonts


def test_choose_family_returns_the_first_installed_candidate() -> None:
    assert fonts.choose_family(["Menlo"], fonts.LCD_FAMILIES) == "Menlo"


def test_choose_family_is_case_insensitive() -> None:
    assert fonts.choose_family(["consolas"], fonts.LCD_FAMILIES) == "Consolas"


def test_choose_family_falls_back_when_no_candidate_is_installed() -> None:
    assert fonts.choose_family(["Arial"], fonts.LCD_FAMILIES) == fonts.DEFAULT_FALLBACK


def test_choose_family_honours_a_custom_fallback_and_empty_inputs() -> None:
    assert fonts.choose_family([], fonts.MATH_FAMILIES, fallback="Santos") == "Santos"
    assert fonts.choose_family(["Consolas"], (), fallback="Santos") == "Santos"


def test_supports_letter_superscripts_matches_known_families_case_insensitively() -> None:
    assert fonts.supports_letter_superscripts("consolas") is True
    assert fonts.supports_letter_superscripts("Menlo") is True
    assert fonts.supports_letter_superscripts("Some Unknown Font") is False
