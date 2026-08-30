"""Behavioural tests for canonical calculator errors."""

from __future__ import annotations

import pytest

from scientific_calculator.errors import CalculatorError, ErrorCode, translate_error_message


@pytest.mark.parametrize("code", tuple(ErrorCode))
def test_structured_error_codes_render_a_nonempty_english_message(code: ErrorCode) -> None:
    error = CalculatorError(code)

    assert error.code is code
    assert str(error).endswith("ERROR")
    assert translate_error_message(error) == str(error)


def test_legacy_error_text_keeps_compatibility_while_the_renderer_is_english() -> None:
    error = CalculatorError("Syntax ERROR: Matematik dışı karakter")

    assert error.code is ErrorCode.SYNTAX
    assert str(error) == "Syntax ERROR: Matematik dışı karakter"
    assert translate_error_message(error) == "Syntax ERROR: Non-mathematical character"
