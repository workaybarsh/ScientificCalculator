"""Tests for the desktop-only legacy-error translation boundary."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from scientific_calculator.calculator_engine import ScientificCalculatorEngine
from scientific_calculator.errors import CalculatorError, translate_error_message

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TURKISH_DIACRITIC = re.compile(
    "[\u00e7\u00c7\u011f\u011e\u0131\u0130\u00f6\u00d6\u015f\u015e\u00fc\u00dc]"
)
_TURKISH_DISPLAY_WORD = re.compile(
    "\\b(?:bilinmeyen|de\u011fi\u015fken|denklem|ge\u00e7ersiz|gerekli|hesaplanamad\u0131|"
    "ifade|matris|olmal\u0131d\u0131r|s\u0131n\u0131r|sonlu|t\u00fcrev|vekt\u00f6r|yaln\u0131z)\\b",
    re.IGNORECASE,
)


def _literal_error_text(argument: ast.expr) -> str | None:
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    if isinstance(argument, ast.JoinedStr):
        return "".join(
            value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else "<value>"
            for value in argument.values
        )
    return None


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Math ERROR: integral sınırı sayısal olmalıdır", "Math ERROR: integral bound must be numeric"),
        ("Syntax ERROR: ODE birinci veya ikinci türev içermelidir",
         "Syntax ERROR: ODE must contain a first- or second-order derivative"),
        ("Memory ERROR: formül 49 baytı aşıyor", "Memory ERROR: formula exceeds 49 bytes"),
        ("Argument ERROR: geçersiz matris verisi", "Argument ERROR: invalid matrix data"),
        ("Math ERROR: sayısal sonuç görüntüleme aralığını aşıyor",
         "Math ERROR: numeric result exceeds the display range"),
        ("Math ERROR: Upper bound sayısal hesaplamaya hazırlanamadı",
         "Math ERROR: Upper bound could not be prepared for numerical calculation"),
        ("Math ERROR: integral sonucu sonlu karmaşık değil",
         "Math ERROR: integral result is not a finite complex number"),
        ("Math ERROR: çoklu integral sınırları sonlu reel olmalıdır",
         "Math ERROR: multiple-integral bounds must be finite and real"),
    ],
)
def test_translate_error_message_translates_representative_legacy_messages(source: str, expected: str) -> None:
    assert translate_error_message(source) == expected


def test_translate_error_message_preserves_english_message_verbatim() -> None:
    message = "Argument ERROR: lower bound exceeds upper bound"

    assert translate_error_message(message) == message


def test_translate_error_message_accepts_an_exception_without_mutating_it() -> None:
    error = CalculatorError("Math ERROR: integralde bilinmeyen değişken var")

    assert str(error) == "Math ERROR: integralde bilinmeyen değişken var"
    assert translate_error_message(error) == "Math ERROR: integral contains an unknown variable"


def test_translate_error_message_never_leaks_unknown_turkish_text_to_the_lcd() -> None:
    translated = translate_error_message("Syntax ERROR: henüz eşlenmemiş bir Türkçe uyarı")

    assert translated == "Syntax ERROR: The request could not be completed."
    assert not re.search(r"[çÇğĞıİöÖşŞüÜ]", translated)
    assert not re.search(r"\b(?:uyarı|eşlenmemiş|Türkçe)\b", translated, re.IGNORECASE)


def test_translate_error_message_uses_an_english_generic_message_without_an_error_prefix() -> None:
    assert translate_error_message("Türkçe uyarı") == "Calculation ERROR: The input could not be understood."


def test_every_static_calculator_error_is_safe_for_the_english_desktop_boundary() -> None:
    """A newly added legacy error cannot silently leak Turkish back to the LCD."""
    source_root = PROJECT_ROOT / "src" / "scientific_calculator"
    messages: list[str] = []
    for source_path in source_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name != "CalculatorError":
                continue
            message = _literal_error_text(node.args[0])
            if message is not None:
                messages.append(message)

    assert messages
    for message in messages:
        translated = translate_error_message(message)
        assert not _TURKISH_DIACRITIC.search(translated), (message, translated)
        assert not _TURKISH_DISPLAY_WORD.search(translated), (message, translated)


def test_calculator_errors_never_interpolate_a_caught_exception_into_the_message() -> None:
    """A raised SymPy/ast/tokenize message is an internal detail, not LCD text.

    ``translate_error_message`` only rewrites Turkish wording, so an English
    internal message interpolated here would reach the LCD byte-for-byte.  The
    static-message check above cannot catch this: it renders every interpolated
    value as ``<value>``, which always looks safe.
    """
    source_root = PROJECT_ROOT / "src" / "scientific_calculator"
    leaks: list[str] = []
    for source_path in source_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler) and node.name):
            for node in ast.walk(handler):
                if not isinstance(node, ast.Call) or not node.args:
                    continue
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if name != "CalculatorError" or not isinstance(node.args[0], ast.JoinedStr):
                    continue
                interpolated = {value.id for value in ast.walk(node.args[0]) if isinstance(value, ast.Name)}
                if handler.name in interpolated:
                    relative_path = source_path.relative_to(PROJECT_ROOT).as_posix()
                    leaks.append(f"{relative_path}:{node.lineno} interpolates caught {handler.name!r}")

    assert not leaks, "\n".join(leaks)


def test_unsupported_function_arity_reports_a_category_not_the_sympy_message() -> None:
    """A SymPy arity complaint must not reach the LCD as raw English internals."""
    engine = ScientificCalculatorEngine(cas_isolated=False)

    with pytest.raises(CalculatorError) as raised:
        engine.parse("Abs(1,2,3)")

    assert translate_error_message(raised.value) == "Syntax ERROR: Invalid expression"
    assert "argument" not in str(raised.value)


def test_every_static_calculator_error_has_a_real_english_translation() -> None:
    """A message must not degrade to the generic category text.

    ``translate_error_message`` falls back to "The request could not be
    completed." whenever Turkish survives its replacements.  That fallback is a
    safety net for unmapped wording, not an acceptable message for an error the
    source raises on purpose: it tells the user nothing about what went wrong.
    """
    source_root = PROJECT_ROOT / "src" / "scientific_calculator"
    generic = ("The request could not be completed.", "The input could not be understood.")
    degraded: list[str] = []
    for source_path in source_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name != "CalculatorError":
                continue
            message = _literal_error_text(node.args[0])
            if message is None:
                continue
            translated = translate_error_message(message)
            if any(fallback in translated for fallback in generic):
                relative_path = source_path.relative_to(PROJECT_ROOT).as_posix()
                degraded.append(f"{relative_path}:{node.lineno} {message!r} -> {translated!r}")

    assert not degraded, "; ".join(degraded)
