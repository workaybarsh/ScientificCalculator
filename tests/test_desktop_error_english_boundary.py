"""Regression coverage for the English-only desktop error presentation boundary."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest import mock

from scientific_calculator.app import App
from scientific_calculator.errors import CalculatorError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_TURKISH_DIACRITIC = re.compile(r"[\u00e7\u00c7\u011f\u011e\u0131\u0130\u00f6\u00d6\u015f\u015e\u00fc\u00dc]")
_TURKISH_WORD = re.compile(
    r"\b(?:adim|ad\u0131m|alan|asiyor|a\u015f\u0131yor|baslangic|ba\u015flang\u0131\u00e7|"
    r"bilinmeyen|degisken|de\u011fi\u015fken|denklem|gecersiz|ge\u00e7ersiz|"
    r"gerekl[io]|hesaplanamadi|hesaplanamad\u0131|ifade|matris|olmalidir|"
    r"olmal\u0131d\u0131r|oran|sinir|s\u0131n\u0131r|sayisal|say\u0131sal|sonlu|"
    r"turev|t\u00fcrev|vektor|vekt\u00f6r|yalniz|yaln\u0131z|yuzey|y\u00fczey)\b",
    re.IGNORECASE,
)


def _contains_turkish_text(text: str) -> bool:
    return bool(_TURKISH_DIACRITIC.search(text) or _TURKISH_WORD.search(text))


def _literal_error_text(argument: ast.expr) -> str | None:
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    if isinstance(argument, ast.JoinedStr):
        return "".join(
            value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else "<value>"
            for value in argument.values
        )
    return None


def _all_static_calculator_error_messages() -> set[str]:
    messages: set[str] = set()
    source_root = PROJECT_ROOT / "src" / "scientific_calculator"
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
                messages.add(message)
    return messages


def _bare_error_presenter() -> App:
    app = object.__new__(App)
    app._clear_active_input_for_error = mock.Mock()
    app._clear_modifiers = mock.Mock()
    app._lcd_message = mock.Mock()
    return app


def test_every_static_calculator_error_reaches_the_standard_english_lcd_boundary() -> None:
    """Test the actual ``App.err`` route, not just the translator in isolation."""
    app = _bare_error_presenter()
    messages = _all_static_calculator_error_messages()

    assert messages
    for message in messages:
        App.err(app, CalculatorError(message), clear_input=False)
        displayed = app._lcd_message.call_args.args[0]
        assert not _contains_turkish_text(displayed), (message, displayed)


def test_lcd_form_error_uses_the_same_english_presentation_boundary() -> None:
    app = object.__new__(App)
    app._lcd_flow = {}
    app._clear_active_input_for_error = mock.Mock()
    app._clear_modifiers = mock.Mock()
    app.result = mock.Mock()

    App._lcd_error(app, CalculatorError("Range ERROR: adım yönü başlangıç/bitiş ile uyuşmuyor"))

    displayed = app.result.config.call_args.kwargs["text"]
    assert displayed.startswith("ERROR: Range ERROR: step")
    assert app._lcd_flow["last_error"] == "Range ERROR: step direction does not match start/end"
    assert not _contains_turkish_text(displayed)
    assert not _contains_turkish_text(app._lcd_flow["last_error"])


def test_unexpected_exception_text_is_not_exposed_on_the_desktop() -> None:
    app = _bare_error_presenter()

    App.err(app, RuntimeError("Türkçe implementation detail"), clear_input=False)

    app._lcd_message.assert_called_once_with("Internal ERROR")


def test_app_does_not_open_explicit_error_or_warning_popups() -> None:
    """All application errors stay on the calculator LCD through ``App.err``."""
    app_source = PROJECT_ROOT / "src" / "scientific_calculator" / "app.py"
    tree = ast.parse(app_source.read_text(encoding="utf-8"), filename=str(app_source))
    popup_calls = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "messagebox"
        and node.func.attr in {"showerror", "showwarning"}
    ]

    assert popup_calls == []
