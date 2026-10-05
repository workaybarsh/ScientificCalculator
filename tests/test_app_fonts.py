"""Tests for the cross-platform LCD font resolution on the Tk application."""

from __future__ import annotations

import tkinter as tk
from unittest import mock

import scientific_calculator.app as APP_MODULE
from scientific_calculator import fonts
from scientific_calculator.app import App


def test_resolve_font_families_prefers_a_platform_family_per_role() -> None:
    app = object.__new__(App)

    with mock.patch.object(APP_MODULE.tkfont, "families", return_value=["Menlo", "DejaVu Sans"]):
        App._resolve_font_families(app)

    assert app._font_family == {"lcd": "Menlo", "math": "DejaVu Sans"}
    assert app._superscript_letters is True


def test_resolve_font_families_falls_back_when_tk_cannot_list_families() -> None:
    app = object.__new__(App)

    with mock.patch.object(
        APP_MODULE.tkfont, "families", side_effect=tk.TclError("no display")
    ):
        App._resolve_font_families(app)

    assert app._font_family == {"lcd": fonts.DEFAULT_FALLBACK, "math": fonts.DEFAULT_FALLBACK}
    assert app._superscript_letters is False


def test_resolve_font_families_disables_letter_superscripts_for_unknown_families() -> None:
    app = object.__new__(App)

    with mock.patch.object(APP_MODULE.tkfont, "families", return_value=["Arial"]):
        App._resolve_font_families(app)

    assert app._font_family["lcd"] == fonts.DEFAULT_FALLBACK
    assert app._superscript_letters is False


def test_font_returns_the_resolved_role_family_and_the_original_pixel_size() -> None:
    app = object.__new__(App)
    app._font_family = {"lcd": "Menlo", "math": "Cambria Math"}
    app._tk_pixels_per_point = 96.0 / 72.0

    with mock.patch.object(App, "_scale_factor", return_value=1.0):
        assert app._font("lcd", 18, "bold") == ("Menlo", app._fp(18), "bold")
        assert app._font("math", 46) == ("Cambria Math", app._fp(46))


def test_font_defaults_to_the_windows_reference_without_resolution() -> None:
    app = object.__new__(App)
    app._tk_pixels_per_point = 96.0 / 72.0

    with mock.patch.object(App, "_scale_factor", return_value=1.0):
        assert app._font("lcd", 18) == (APP_MODULE._DEFAULT_FONT_FAMILY["lcd"], app._fp(18))
