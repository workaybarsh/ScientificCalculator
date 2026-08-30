from __future__ import annotations

import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image as PillowImage

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "src" / "scientific_calculator" / "app.py"

from scientific_calculator import app as APP_MODULE
from scientific_calculator.calculator_engine import (
    CURRENT_CONSTANTS_DATASET_LABEL,
    LEGACY_CONSTANTS_DATASET_LABEL,
    CalculatorError,
    ScientificCalculatorEngine,
    constants_for_dataset,
)

App = APP_MODULE.App


class DummySettings:
    def __init__(self):
        self.angle_unit = "RAD"
        self.number_digits = 3
        self.table_two_functions = False
        self.constant_dataset = LEGACY_CONSTANTS_DATASET_LABEL


def _bare_app(database_path: Path):
    app = object.__new__(App)
    app._db_base_path = lambda: str(database_path)
    app.core = types.SimpleNamespace(settings=DummySettings(), history=[])
    app.skin_name = "Graphite"
    return app


class UiScalingTests(unittest.TestCase):
    def test_all_supported_scales_preserve_the_100_percent_reference(self):
        self.assertEqual(App.UI_SCALES, (40, 50, 60, 75, 100, 125, 150, 200))
        app = object.__new__(App)
        for percent in App.UI_SCALES:
            with self.subTest(percent=percent):
                app.ui_scale = percent
                factor = percent / 100.0
                self.assertEqual(app._scale_factor(), factor)
                self.assertEqual(app._sp(480), round(480 * factor))
                self.assertEqual(app._sp(980), round(980 * factor))
                self.assertEqual(
                    app._skin_xy(375, 430),
                    (round((375 - 330) * 0.8 * factor), round((430 - 5) * 0.8 * factor)),
                )

    def test_invalid_scales_fall_back_to_100_percent(self):
        for value in (None, "", "abc", 0, 33, 175, 500):
            with self.subTest(value=value):
                self.assertEqual(App._validated_ui_scale(value), 100)
        for value in App.UI_SCALES:
            self.assertEqual(App._validated_ui_scale(str(value)), value)

    def test_all_platforms_use_a_100_percent_first_run_and_reset_scale(self):
        with mock.patch.object(APP_MODULE.sys, "platform", "darwin"):
            self.assertEqual(App._platform_default_ui_scale(), 100)
            self.assertEqual(App._default_saved_config()["scale"], 100)
            self.assertEqual(App._sanitize_saved_config({})["scale"], 100)

        with mock.patch.object(APP_MODULE.sys, "platform", "win32"):
            self.assertEqual(App._platform_default_ui_scale(), 100)
            self.assertEqual(App._default_saved_config()["scale"], 100)

    def test_every_platform_limits_scale_to_the_largest_complete_view(self):
        app = object.__new__(App)
        app.winfo_screenwidth = mock.Mock(return_value=1200)
        app.winfo_screenheight = mock.Mock(return_value=1600)
        with mock.patch.object(APP_MODULE.sys, "platform", "darwin"):
            self.assertEqual(app._fit_ui_scale_to_display(200), 150)

        with mock.patch.object(APP_MODULE.sys, "platform", "win32"):
            self.assertEqual(app._fit_ui_scale_to_display(200), 150)

    def test_headless_macos_scale_check_falls_back_without_a_tk_display(self):
        app = object.__new__(App)
        with mock.patch.object(APP_MODULE.sys, "platform", "darwin"):
            self.assertEqual(app._fit_ui_scale_to_display(125), 125)

    def test_only_bundled_skin_names_are_accepted(self):
        self.assertEqual(
            App.SKINS,
            {
                "Graphite": "skins/skin_graphite.png",
                "Blue": "skins/skin_blue.png",
                "Pink": "skins/skin_pink.png",
                "White": "skins/skin_white.png",
            },
        )
        for name in App.SKINS:
            self.assertEqual(App._validated_skin_name(name), name)
        for value in (None, "", "Purple", "skin_blue.png", 42):
            self.assertEqual(App._validated_skin_name(value), "Graphite")

    def test_apply_scale_saves_and_rebuilds(self):
        app = object.__new__(App)
        app.ui_scale = 100
        app.save_settings_file = mock.Mock(return_value=True)
        app._rebuild_scaled_ui = mock.Mock()

        app.apply_scale(125)

        self.assertEqual(app.ui_scale, 125)
        app.save_settings_file.assert_called_once_with(False)
        app._rebuild_scaled_ui.assert_called_once_with()

    def test_scaled_rebuild_temporarily_unlocks_window_geometry(self):
        class Entry:
            def get(self):
                return "2+2"

            def index(self, _):
                return 2

            def icursor(self, value):
                calls.append(("cursor", value))

        class Result:
            def cget(self, _):
                return "4"

            def config(self, **options):
                calls.append(("result", options["text"]))

        calls = []
        app = types.SimpleNamespace(
            expr=Entry(),
            result=Result(),
            template_kind=None,
            winfo_children=lambda: [],
            resizable=lambda width, height: calls.append(("resizable", width, height)),
            geometry=lambda value: calls.append(("geometry", value)),
            _sp=lambda value: round(value * 1.25),
            _ui=lambda: calls.append(("ui",)),
            set_expr=lambda text: calls.append(("expression", text)),
            render_template=lambda: calls.append(("template",)),
            status_refresh=lambda: calls.append(("status",)),
        )

        App._rebuild_scaled_ui(app)

        self.assertEqual(
            calls,
            [
                ("resizable", True, True),
                ("geometry", "600x1225"),
                ("ui",),
                ("expression", "2+2"),
                ("result", "4"),
                ("cursor", 2),
                ("status",),
                ("resizable", False, False),
            ],
        )

    def test_scaled_rebuild_preserves_active_template(self):
        calls = []

        class Entry:
            def get(self):
                return ""

            def index(self, _):
                return 0

        class Result:
            def cget(self, _):
                return "integral pending"

            def config(self, **options):
                calls.append(("result", options["text"]))

        app = types.SimpleNamespace(
            expr=Entry(), result=Result(), template_kind="integral",
            winfo_children=lambda: [], resizable=lambda *v: None,
            geometry=lambda value: None, _sp=lambda value: value,
            _ui=lambda: None, render_template=lambda: calls.append(("template",)),
            set_expr=lambda text: calls.append(("expression", text)),
            status_refresh=lambda: None,
        )
        App._rebuild_scaled_ui(app)
        self.assertEqual(calls, [("result", "integral pending"), ("template",)])


class TableContractTests(unittest.TestCase):
    def test_table_row_limits_and_step_directions(self):
        self.assertEqual(App._table_row_count(-1, 1, 0.5), 5)
        self.assertEqual(App._table_row_count(1, -1, -0.5), 5)
        self.assertEqual(App._table_row_count(0, 44, 1), 45)
        self.assertEqual(App._table_row_count(0, 29, 1, True), 30)

    def test_table_rejects_invalid_steps_and_oversized_ranges(self):
        invalid = [
            (0, 1, 0, False),
            (0, 1, -0.5, False),
            (1, 0, 0.5, False),
            (0, 45, 1, False),
            (0, 30, 1, True),
            (0, 1, float("inf"), False),
            (-1e308, 1e308, 1, False),
        ]
        for start, end, step, two_functions in invalid:
            with self.subTest(start=start, end=end, step=step, two_functions=two_functions), self.assertRaises(
                APP_MODULE.CalculatorError
            ):
                App._table_row_count(start, end, step, two_functions)


class LcdInputContractTests(unittest.TestCase):
    def _app(self):
        app = object.__new__(App)
        app.core = ScientificCalculatorEngine(cas_isolated=False)
        return app

    def test_lcd_numeric_fields_accept_finite_values_and_enforce_bounds(self):
        app = self._app()
        self.assertEqual(App._lcd_real(app, "2+3", "value"), 5)
        self.assertEqual(App._lcd_real(app, "3", "count", integer=True), 3)
        self.assertEqual(App._lcd_numbers(app, "1, 2; 3", "values"), [1, 2, 3])
        for value, kwargs in (("", {}), ("z", {}), ("i", {}), ("1.5", {"integer": True}), ("0", {"minimum": 1}), ("6", {"maximum": 5})):
            with self.subTest(value=value, kwargs=kwargs), self.assertRaises(CalculatorError):
                App._lcd_real(app, value, "value", **kwargs)

    def test_lcd_field_parser_validates_choices_functions_and_raw_text(self):
        app = self._app()
        choice = {"key": "kind", "label": "kind", "type": "choice", "choices": {1: "one", 2: "two"}}
        self.assertEqual(App._lcd_parse_field(app, choice, "2"), "two")
        self.assertEqual(App._lcd_parse_field(app, choice, "two"), "two")
        self.assertEqual(App._lcd_parse_field(app, {"key": "raw", "type": "raw"}, "  text  "), "  text  ")
        self.assertEqual(App._lcd_parse_field(app, {"key": "text"}, "  text  "), "text")
        self.assertEqual(App._lcd_function(app, "sin(x)", "function"), "sin(x)")
        for spec, value in ((choice, "9"), ({"key": "f", "type": "function"}, ""), ({"key": "n", "type": "numbers"}, "")):
            with self.subTest(spec=spec, value=value), self.assertRaises(CalculatorError):
                App._lcd_parse_field(app, spec, value)


class ModeMenuContractTests(unittest.TestCase):
    def test_history_view_blocks_integral_template(self):
        app = object.__new__(App)
        app._lcd_flow = {"mode": "History", "phase": "results"}
        app.shift = False
        app.alpha = False
        app.consume = mock.Mock()
        app.start_integral_template = mock.Mock()
        app.start_derivative_template = mock.Mock()

        App.integral_key(app)

        app.consume.assert_called_once_with()
        app.start_integral_template.assert_not_called()
        app.start_derivative_template.assert_not_called()

    def test_calculate_and_complex_integral_keys_open_embedded_lcd_flows(self):
        for mode, expected_flow in (("Calculate", "Integral"), ("Complex", "Complex Integral")):
            with self.subTest(mode=mode):
                app = object.__new__(App)
                app._history_lcd_active = mock.Mock(return_value=False)
                app.alpha = False
                app.shift = False
                app.mode = mode
                app.consume = mock.Mock()
                app._open_calculus_flow = mock.Mock()
                app.start_integral_template = mock.Mock()

                App.integral_key(app)

                app._open_calculus_flow.assert_called_once_with(expected_flow)
                app.start_integral_template.assert_not_called()

    def test_shift_integral_opens_the_derivative_template_in_calculate_and_complex_modes(self):
        for mode in ("Calculate", "Complex"):
            with self.subTest(mode=mode):
                app = object.__new__(App)
                app._history_lcd_active = mock.Mock(return_value=False)
                app.alpha = False
                app.shift = True
                app.mode = mode
                app.consume = mock.Mock()
                app._clear_before_interaction_transition = mock.Mock(return_value="x^2")
                app.start_derivative_template = mock.Mock()

                App.integral_key(app)

                app._clear_before_interaction_transition.assert_called_once_with()
                app.start_derivative_template.assert_called_once_with("x^2")

    def test_integral_menu_starts_the_embedded_lcd_flow_without_a_popup(self):
        app = object.__new__(App)
        app.mode = "Calculate"
        app._open_calculus_flow = mock.Mock()

        App.integral_menu(app)

        app._open_calculus_flow.assert_called_once_with("Integral")

        app.mode = "Matrix"
        app._open_calculus_flow.reset_mock()
        App.integral_menu(app)
        app._open_calculus_flow.assert_not_called()

    def test_direct_history_flow_is_ignored_outside_calculate_and_complex(self):
        app = object.__new__(App)
        app.mode = "Matrix"
        app._lcd_flow = {"mode": "Matrix"}
        app.cancel_template = mock.Mock()

        App._start_lcd_flow(app, "History")

        assert app._lcd_flow == {"mode": "Matrix"}
        app.cancel_template.assert_not_called()

    def test_each_mode_has_a_short_starting_hint(self):
        self.assertEqual(set(App.MODE_HINTS), set(App.MODES))
        self.assertTrue(all(hint and "\n" not in hint for hint in App.MODE_HINTS.values()))

    def test_every_mode_menu_item_uses_the_mode_selection_flow(self):
        class Menu:
            def __init__(self):
                self.commands = {}

            def add_command(self, *, label, command):
                self.commands[label] = command

            def add_separator(self):
                pass

            def tk_popup(self, *_):
                pass

            def grab_release(self):
                pass

        menu = Menu()
        app = types.SimpleNamespace(
            mode="Calculate",
            shift=False,
            _history_lcd_active=lambda: False,
            MODES=App.MODES,
            select_mode=mock.Mock(),
            show_history=mock.Mock(),
            setup_dialog=mock.Mock(),
            winfo_pointerx=lambda: 0,
            winfo_pointery=lambda: 0,
        )

        with mock.patch.object(APP_MODULE.tk, "Menu", return_value=menu):
            App.menu_key(app)

        self.assertTrue(set(App.MODES).issubset(menu.commands))
        for mode in App.MODES:
            with self.subTest(mode=mode):
                menu.commands[mode]()
                app.select_mode.assert_called_with(mode)
                app.select_mode.reset_mock()

        menu.commands["History"]()
        app.show_history.assert_called_once_with()

        restricted_menu = Menu()
        app.mode = "Matrix"
        with mock.patch.object(APP_MODULE.tk, "Menu", return_value=restricted_menu):
            App.menu_key(app)
        self.assertNotIn("History", restricted_menu.commands)


class LcdCalculusFlowContractTests(unittest.TestCase):
    _VARIABLE_CHOICES = {1: "x", 2: "y", 3: "z", 4: "t", 5: "u", 6: "v"}

    @staticmethod
    def _form_app(mode: str, source: str = ""):
        app = object.__new__(App)
        app._lcd_flow = {"mode": mode, "values": {}, "draft": {}, "last_error": ""}
        app.expr = types.SimpleNamespace(get=lambda: source)
        app._lcd_begin_form = mock.Mock()
        return app

    def test_integral_and_complex_integral_selectors_expose_all_lcd_actions(self):
        cases = [
            (
                "Integral",
                App._lcd_start_integral,
                "INTEGRAL",
                {1: "definite", 2: "double", 3: "triple"},
                {"definite": "Integral", "double": "Double", "triple": "Triple"},
            ),
            (
                "Complex Integral",
                App._lcd_start_complex_integral,
                "CPLX INT",
                {1: "definite"},
                {"definite": "Integral"},
            ),
        ]
        for mode, starter, title, actions, labels in cases:
            with self.subTest(mode=mode):
                app = self._form_app(mode, "sin(x)")

                starter(app)

                self.assertEqual(app._lcd_flow["source_expression"], "sin(x)")
                actual_title, fields, stage = app._lcd_begin_form.call_args.args
                self.assertEqual((actual_title, stage), (title, "calculus_action"))
                self.assertEqual(len(fields), 1)
                self.assertEqual(fields[0]["key"], "calculus_action")
                self.assertEqual(fields[0]["choices"], actions)
                self.assertEqual(fields[0]["choice_labels"], labels)
                self.assertTrue(all("…" not in label for label in labels.values()))

    def test_multi_integrals_open_numbered_natural_templates_instead_of_long_lcd_forms(self):
        for mode, action, source, order in (
            ("Integral", "Double Integral", "x*y", "double"),
            ("Integral", "Triple Integral", "x*y*z", "triple"),
        ):
            with self.subTest(action=action):
                app = self._form_app(mode, source)
                app._lcd_flow["values"]["calculus_action"] = action
                app._lcd_flow["source_expression"] = source
                app._reset_lcd_flow = mock.Mock()
                app.set_expr = mock.Mock()
                app.start_multiple_integral_template = mock.Mock()

                App._lcd_choose_calculus_action(app)

                app.set_expr.assert_called_once_with(source)
                app.start_multiple_integral_template.assert_called_once_with(order)
                app._lcd_begin_form.assert_not_called()

    def test_complex_calculus_rejects_multi_integral_actions(self):
        app = self._form_app("Complex Integral", "z^2")
        app._lcd_flow["values"]["calculus_action"] = "double"

        with self.assertRaisesRegex(CalculatorError, "unsupported calculus operation"):
            App._lcd_choose_calculus_action(app)

        app._lcd_begin_form.assert_not_called()

    def test_definite_integral_action_moves_to_the_existing_lcd_template(self):
        app = self._form_app("Integral", "cos(x)")
        app._lcd_flow["source_expression"] = "cos(x)"
        app._lcd_flow["values"]["calculus_action"] = "Definite Integral"
        app._reset_lcd_flow = mock.Mock()
        app.set_expr = mock.Mock()
        app.start_integral_template = mock.Mock()

        App._lcd_choose_calculus_action(app)

        app._reset_lcd_flow.assert_called_once_with()
        app.set_expr.assert_called_once_with("cos(x)")
        app.start_integral_template.assert_called_once_with()
        app._lcd_begin_form.assert_not_called()

class LcdDifferentialEquationFlowContractTests(unittest.TestCase):
    def test_equation_selector_exposes_differential_equations(self):
        app = object.__new__(App)
        app._lcd_begin_form = mock.Mock()

        App._lcd_start_equation(app)

        title, fields, stage = app._lcd_begin_form.call_args.args
        self.assertEqual((title, stage), ("EQUATION", "equation_kind"))
        self.assertEqual(len(fields), 1)
        self.assertEqual(fields[0]["key"], "equation_kind")
        self.assertEqual(fields[0]["choices"], {1: "polynomial", 2: "simultaneous", 3: "ode"})
        self.assertEqual(
            fields[0]["choice_labels"], {"polynomial": "Polynomial", "simultaneous": "Simultaneous", "ode": "Differential Eq."}
        )

    def test_differential_equation_opens_the_editable_coefficient_template(self):
        app = object.__new__(App)
        app._lcd_flow = {"values": {"equation_kind": "ode"}}
        app.start_ode_template = mock.Mock()

        App._lcd_choose_equation_kind(app)

        app.start_ode_template.assert_called_once_with()

    def test_ode_template_assembles_its_four_coefficients_for_the_worker(self):
        app = object.__new__(App)
        app.template_kind = "ode"
        app.template_fields = {"ode_a": "2", "ode_b": "x", "ode_c": "1", "ode_f": "sin(x)"}
        app._run_background_calculation = mock.Mock()
        app._show_completed_result = mock.Mock()
        app.cancel_template = mock.Mock()
        app.core = mock.Mock()
        app.core.format_result.return_value = "formatted"

        App.evaluate_template(app)

        self.assertEqual(
            app._run_background_calculation.call_args.args[:2],
            ("solve_ode", ("(2)*d2y/dx2+(x)*dy/dx+(1)*y=(sin(x))",)),
        )
        app._run_background_calculation.call_args.args[2]("backend result")
        app._show_completed_result.assert_called_once_with("formatted")
        app.cancel_template.assert_called_once_with()


class ModeTransitionContractTests(unittest.TestCase):
    class _Result:
        def __init__(self):
            self.text = ""

        def config(self, *, text):
            self.text = text

    def test_switching_mode_cancels_templates_without_clearing_spreadsheet_data(self):
        sheet = types.SimpleNamespace(delete_all=mock.Mock())
        app = types.SimpleNamespace(
            mode="Spreadsheet",
            sheet=sheet,
            cancel_template=mock.Mock(),
            consume=mock.Mock(),
            status_refresh=mock.Mock(),
            result=self._Result(),
            MODE_HINTS=App.MODE_HINTS,
        )

        App.select_mode(app, "Base-N")

        app.cancel_template.assert_called_once_with()
        sheet.delete_all.assert_not_called()
        self.assertEqual(app.mode, "Base-N")
        self.assertEqual(app.result.text, App.MODE_HINTS["Base-N"])


class SpreadsheetViewContractTests(unittest.TestCase):
    def test_formula_and_value_views_use_the_selected_spreadsheet_setting(self):
        app = object.__new__(App)
        app.sheet = types.SimpleNamespace(cells={"A1": "=1+1"}, cache={"A1": 2})
        app.core = types.SimpleNamespace(
            settings=types.SimpleNamespace(spreadsheet_show_cell="Formula")
        )

        self.assertEqual(app._spreadsheet_display_value("A1"), "=1+1")
        app.core.settings.spreadsheet_show_cell = "Value"
        self.assertEqual(app._spreadsheet_display_value("A1"), 2)

class ModifierAppearanceTests(unittest.TestCase):
    class _Label:
        def __init__(self):
            self.options = {}

        def config(self, **options):
            self.options.update(options)

    def test_shift_and_alpha_use_the_normal_lcd_text_color(self):
        self.assertEqual(App.LCD_TEXT_COLOR, "#273026")

    def test_modifier_state_is_text_only(self):
        app = object.__new__(App)
        app.shift_status = self._Label()
        app.alpha_status = self._Label()

        app.shift = True
        app.alpha = False
        app._refresh_modifier_status()
        self.assertEqual(app.shift_status.options["text"], "SHIFT")
        self.assertEqual(app.alpha_status.options["text"], "")

        app.shift = False
        app.alpha = True
        app._refresh_modifier_status()
        self.assertEqual(app.shift_status.options["text"], "")
        self.assertEqual(app.alpha_status.options["text"], "ALPHA")

        source = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn("modifier_state", source)
        self.assertNotIn("create_oval", source)
        self.assertNotIn("activebackground", source)
        self.assertFalse(hasattr(App, "_draw_modifier_state"))


class RemovedShortcutTests(unittest.TestCase):
    def test_infinity_legend_is_present_in_the_graphite_skin(self):
        with PillowImage.open(PROJECT_ROOT / "assets" / "skins" / "skin_graphite.png") as image:
            caption_area = image.convert("RGB").crop((44, 412, 72, 430))
        warm_pixels = sum(
            1
            for red, green, blue in caption_area.get_flattened_data()
            if red > 150 and green > 120 and blue < 130
        )
        self.assertGreaterEqual(warm_pixels, 60)

    def test_no_removed_shortcut_command_or_hotspot_remains(self):
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertNotRegex(source, r"(?i)\bqr\b")


class SkinAssetTests(unittest.TestCase):
    def test_all_selectable_skins_are_480_by_980_and_solar_free(self):
        for filename in App.SKINS.values():
            with self.subTest(filename=filename), PillowImage.open(PROJECT_ROOT / "assets" / filename) as image:
                self.assertEqual(image.size, (480, 980))
        self.assertTrue((PROJECT_ROOT / "assets" / "skins" / "skin_white.png").exists())

        # This was the former brown solar-panel area.  Graphite case pixels are
        # intentionally neutral now, without a brown photovoltaic panel.
        with PillowImage.open(PROJECT_ROOT / "assets" / "skins" / "skin_graphite.png") as image:
            panel_area = image.convert("RGB").crop((207, 28, 419, 115))
        self.assertLessEqual(
            max(max(red, green, blue) - min(red, green, blue) for red, green, blue in panel_area.get_flattened_data()),
            10,
        )

    def test_readme_art_uses_the_bundled_graphite_skin_and_icon_is_clean(self):
        self.assertFalse((PROJECT_ROOT / "assets" / "readme_hero.png").exists())
        self.assertFalse((PROJECT_ROOT / "assets" / "readme_hero_v1_0.png").exists())
        with PillowImage.open(PROJECT_ROOT / "assets" / "skins" / "skin_graphite.png") as image:
            self.assertEqual(image.size, (480, 980))
        with PillowImage.open(PROJECT_ROOT / "assets" / "icons" / "app.ico") as icon:
            icon.seek(0)
            self.assertEqual(icon.size, (256, 256))
            rgba = icon.convert("RGBA")
            alpha_bounds = rgba.getchannel("A").getbbox()
            self.assertIsNotNone(alpha_bounds)
            self.assertLessEqual(alpha_bounds[0], 12)
            self.assertLessEqual(alpha_bounds[1], 12)
            self.assertGreaterEqual(alpha_bounds[2], 244)
            self.assertGreaterEqual(alpha_bounds[3], 244)
            self.assertEqual(rgba.getpixel((0, 0))[3], 0)
            # The central LCD is intentionally blank: only its pale display
            # gradient remains, without dark text glyphs.
            lcd_center = rgba.convert("RGB").crop((72, 62, 184, 96))
            self.assertGreater(min(min(pixel) for pixel in lcd_center.get_flattened_data()), 150)


class DialogCancelContractTests(unittest.TestCase):
    def test_base_logic_second_value_cancel_is_silent(self):
        app = object.__new__(App)
        app.base = 10
        app.expr = types.SimpleNamespace(get=lambda: "1")
        app.core = types.SimpleNamespace(evaluate_base=mock.Mock(return_value=1))
        app.err = mock.Mock()
        with mock.patch.object(APP_MODULE.simpledialog, "askstring", return_value=None):
            app.base_logic_dialog("and")
        app.err.assert_not_called()
        app.core.evaluate_base.assert_called_once_with("1", 10)

class TemplateViewportTests(unittest.TestCase):
    def test_complex_integral_template_leaves_the_differential_blank_until_the_user_enters_it(self):
        app = object.__new__(App)
        app.mode = "Complex"
        app.template_kind = None
        app.expr = types.SimpleNamespace(get=lambda: "")
        app._reset_lcd_flow = mock.Mock()
        app.render_template = mock.Mock()
        app.result = mock.Mock()
        app._set_lcd_label = mock.Mock()

        App.start_integral_template(app)

        self.assertEqual(app.template_fields["var"], "z")
        self.assertEqual(app.template_fields["lower"], "")
        self.assertEqual(app.template_fields["upper"], "")
        self.assertEqual(app.template_order, ["body", "lower", "upper"])
        app._set_lcd_label.assert_called_once_with("")
        app.template_fields["body"] = "z^2"
        app.template_cursors = {key: len(value) for key, value in app.template_fields.items()}
        app.template_fields.update({"body": "i*z", "lower": "0", "upper": "1"})
        app.template_cursors = {key: len(value) for key, value in app.template_fields.items()}
        app._run_background_calculation = mock.Mock()
        app.cancel_template = mock.Mock()
        app._calculation_busy = False

        App.evaluate_template(app)

        self.assertEqual(
            app._run_background_calculation.call_args.args[:2],
            ("complex_definite_integral", ("i*z", "0", "1", "z")),
        )

    def test_long_template_expression_tracks_the_caret_without_overflow(self):
        app = object.__new__(App)
        expression = "sin(x^2)*cos(x)*ln(x)/(x+1)"
        fixed_font = types.SimpleNamespace(measure=lambda value: len(value) * 10)

        with mock.patch.object(APP_MODULE.tkfont, "Font", return_value=fixed_font):
            shown, caret_offset = app._template_text_view(
                expression, len(expression), ("Consolas", -19), 120
            )

        self.assertTrue(shown.startswith("…"))
        self.assertLessEqual(caret_offset, 120)
        self.assertIn(expression[-1], shown)

    def test_right_navigation_keeps_the_active_integral_field(self):
        app = object.__new__(App)
        app.template_kind = "integral"
        app.template_order = ["body", "upper", "lower"]
        app.template_index = 0
        app.template_fields = {"body": "sin(x^2)*cos(x)", "upper": "", "lower": ""}
        app.template_cursors = {"body": 0, "upper": 0, "lower": 0}
        app.render_template = mock.Mock()

        app.move(1)

        self.assertEqual(app._active_template_field(), "body")
        self.assertEqual(app.template_cursors["body"], 1)
        self.assertEqual(app.render_template.call_count, 1)

    def test_multiple_integral_template_has_editable_numbered_layers_and_dispatches(self):
        app = object.__new__(App)
        app.mode = "Calculate"
        app.template_kind = None
        app.expr = types.SimpleNamespace(get=lambda: "x*y*z")
        app._reset_lcd_flow = mock.Mock()
        app.render_template = mock.Mock()
        app.result = mock.Mock()
        app._set_lcd_label = mock.Mock()

        with self.assertRaisesRegex(CalculatorError, "unsupported integral order"):
            App.start_multiple_integral_template(app, "quadruple")

        App.start_multiple_integral_template(app, "triple")

        app._set_lcd_label.assert_called_once_with("")

        self.assertEqual(app.template_order, ["body", "inner_lower", "inner_upper", "inner_var", "middle_lower", "middle_upper", "middle_var", "outer_lower", "outer_upper", "outer_var"])
        self.assertTrue(all(value == "" for key, value in app.template_fields.items() if key not in {"body", "order"}))
        app.template_fields["body"] = "x*y*z"
        with self.assertRaisesRegex(CalculatorError, "every integral bound"):
            App.evaluate_template(app)
        app.template_fields.update({
            "outer_lower": "0", "outer_upper": "1", "middle_lower": "0", "middle_upper": "1",
            "inner_lower": "0", "inner_upper": "1",
        })
        with self.assertRaisesRegex(CalculatorError, "every differential variable"):
            App.evaluate_template(app)
        App.start_multiple_integral_template(app, "double")
        self.assertEqual(app.template_fields["body"], "")
        app.expr = types.SimpleNamespace(get=mock.Mock(side_effect=AssertionError("active template must not be copied")))
        App.start_multiple_integral_template(app, "triple")
        app.template_fields.update({
            "body": "x*y*z", "outer_lower": "0", "outer_upper": "1", "outer_var": "x",
            "middle_lower": "0", "middle_upper": "1", "middle_var": "y",
            "inner_lower": "0", "inner_upper": "1", "inner_var": "z",
        })
        app._run_background_calculation = mock.Mock()
        app.cancel_template = mock.Mock()
        app._calculation_busy = False
        App.evaluate_template(app)
        self.assertEqual(
            app._run_background_calculation.call_args.args[:2],
            ("triple_integral", ("x*y*z", "0", "1", "0", "1", "0", "1", "x", "y", "z")),
        )
        app.template_fields["body"] = ""
        with self.assertRaisesRegex(CalculatorError, "Integral function is empty"):
            App.evaluate_template(app)

    def test_complex_derivative_template_uses_the_dedicated_derivative_operation(self):
        app = object.__new__(App)
        app.mode = "Complex"
        app.template_kind = None
        app.expr = types.SimpleNamespace(get=lambda: "z^2")
        app._reset_lcd_flow = mock.Mock()
        app.render_template = mock.Mock()
        app.result = mock.Mock()
        App.start_derivative_template(app)
        assert app.template_fields["var"] == "z"
        app._run_background_calculation = mock.Mock()
        app._calculation_busy = False
        app.cancel_template = mock.Mock()
        app.core = types.SimpleNamespace(format_result=mock.Mock(return_value="2"))
        app._show_completed_result = mock.Mock()
        App.evaluate_template(app)
        self.assertEqual(app._run_background_calculation.call_args.args[:2], ("complex_derivative_result", ("z^2", "z", None)))
        completed = app._run_background_calculation.call_args.args[2]
        completed(types.SimpleNamespace(value=2, message_code="OK"))
        completed(types.SimpleNamespace(value=None, message_code="DOMAIN_ERROR"))
        self.assertEqual(app._show_completed_result.call_args_list, [mock.call("d/dz=2"), mock.call("d/dz=DOMAIN ERROR")])

        app.template_fields["point"] = "1+i"
        App.evaluate_template(app)
        self.assertEqual(app._run_background_calculation.call_args.args[:2], ("complex_derivative_result", ("z^2", "z", "1+i")))


class KeyDispatchContractTests(unittest.TestCase):
    @staticmethod
    def _app(mode="Calculate"):
        app = object.__new__(App)
        app.mode = mode
        app.shift = False
        app.alpha = False
        app.base = 0
        app.insert = mock.Mock()
        app.consume = mock.Mock()
        app.status_refresh = mock.Mock()
        app._insert_function_token = mock.Mock()
        app.result = mock.Mock()
        app.core = types.SimpleNamespace(ans=12)
        return app

    def test_base_n_keys_select_base_without_inserting_calculate_tokens(self):
        app = self._app("Base-N")

        App.square_key(app)
        self.assertEqual(app.base, 10)
        App.power_key(app)
        self.assertEqual(app.base, 16)
        App.log_key(app)
        self.assertEqual(app.base, 2)
        App.ln_key(app)
        self.assertEqual(app.base, 8)
        app.insert.assert_not_called()
        self.assertEqual(app.status_refresh.call_count, 4)

    def test_modifier_keys_dispatch_visible_calculator_tokens(self):
        app = self._app()
        app.shift = True
        App.sqrt_key(app)
        app._insert_function_token.assert_called_once_with("cbrt(")

        app._insert_function_token.reset_mock()
        app.shift = False
        App.sqrt_key(app)
        app._insert_function_token.assert_called_once_with("sqrt(")

        app.alpha = True
        App.trig_key(app, "sin")
        App.neg_key(app)
        App.inv_key(app)
        App.rparen_key(app)
        self.assertEqual(
            [call.args[0] for call in app.insert.call_args_list[-4:]],
            ["D", "A", "C", "x"],
        )

        app.alpha = False
        app.shift = True
        App.trig_key(app, "cos")
        self.assertEqual(app._insert_function_token.call_args.args[0], "acos(")

    def test_equals_routes_each_main_mode_to_the_correct_execution_path(self):
        app = self._app()
        app._calculation_busy = False
        app._history_lcd_active = mock.Mock(return_value=False)
        app._lcd_flow_active = mock.Mock(return_value=False)
        app.template_kind = None
        app.expr = types.SimpleNamespace(get=lambda: "2+3")
        app._run_background_calculation = mock.Mock()
        app.core.history = []
        app.show = mock.Mock()

        App.equals(app)
        self.assertEqual(app._run_background_calculation.call_args.args[:2], ("evaluate", ("2+3",)))

        app._run_background_calculation.reset_mock()
        app.mode = "Complex"
        App.equals(app)
        self.assertEqual(app._run_background_calculation.call_args.args[:2], ("complex_eval", ("2+3",)))

        app.mode = "Base-N"
        app.core.evaluate_base = mock.Mock(return_value=15)
        app.core.format_base = mock.Mock(return_value="F")
        App.equals(app)
        app.core.evaluate_base.assert_called_once_with("2+3", 0)
        self.assertEqual(app.core.ans, 15)
        app.result.config.assert_called_with(text="F")

class PhysicalKeyboardInputTests(unittest.TestCase):
    @staticmethod
    def _event(char="", keysym="", state=0):
        return types.SimpleNamespace(char=char, keysym=keysym, state=state)

    def test_keyboard_accepts_only_visible_calculator_key_equivalents(self):
        app = object.__new__(App)
        app.template_kind = None
        app.mode = "Calculate"
        app.insert = mock.Mock()

        self.assertEqual(app._physical_keypress(self._event("*", "asterisk")), "break")
        app.insert.assert_called_once_with("×")

        app.insert.reset_mock()
        self.assertEqual(app._physical_keypress(self._event("-", "KP_Subtract")), "break")
        app.insert.assert_called_once_with("−")

        for character in ("g", "s", "n", "@", "[", " "):
            with self.subTest(character=character):
                app.insert.reset_mock()
                self.assertEqual(app._physical_keypress(self._event(character, character)), "break")
                app.insert.assert_not_called()

    def test_keyboard_allows_only_complex_i_and_blocks_paste(self):
        app = object.__new__(App)
        app.template_kind = None
        app.mode = "Calculate"
        app.insert = mock.Mock()
        self.assertEqual(app._physical_keypress(self._event("i", "i")), "break")
        app.insert.assert_not_called()

        app.mode = "Complex"
        self.assertEqual(app._physical_keypress(self._event("i", "i")), "break")
        app.insert.assert_called_once_with("i")

        app.insert.reset_mock()
        self.assertEqual(app._physical_keypress(self._event("v", "v", state=0x4)), "break")
        app.insert.assert_not_called()

    def test_templates_apply_the_same_character_restriction(self):
        app = object.__new__(App)
        app.template_kind = "integral"
        app.template_insert = mock.Mock()

        self.assertEqual(app._template_keypress(self._event("s", "s")), "break")
        app.template_insert.assert_not_called()
        self.assertEqual(app._template_keypress(self._event("x", "x")), "break")
        app.template_insert.assert_called_once_with("x")


class SqlitePersistenceTests(unittest.TestCase):
    def test_constants_dataset_is_validated_and_uses_distinct_catalogues(self):
        self.assertEqual(
            App._sanitize_calculator_settings({"constant_dataset": CURRENT_CONSTANTS_DATASET_LABEL}),
            {"constant_dataset": CURRENT_CONSTANTS_DATASET_LABEL},
        )
        self.assertEqual(App._sanitize_calculator_settings({"constant_dataset": "latest"}), {})
        self.assertNotEqual(
            constants_for_dataset(LEGACY_CONSTANTS_DATASET_LABEL)["h"][1],
            constants_for_dataset(CURRENT_CONSTANTS_DATASET_LABEL)["h"][1],
        )

    def test_history_line_keeps_the_expression_and_result_separator_visible(self):
        self.assertEqual(App._history_line("∫0→pi sin(x)cos(x) dx", "0"), "∫0→pi sin(x)cos(x) dx = 0")
        self.assertEqual(App._history_line("very long calculation expression", "123456789012345"), "very long calculation expression = 123456789012345")

    def test_history_lcd_numbers_the_newest_entry_first(self):
        app = object.__new__(App)
        app.core = types.SimpleNamespace(history=[("2+2", "4"), ("3+3", "6")])
        app._lcd_show_results = mock.Mock()

        App._lcd_start_history(app)

        app._lcd_show_results.assert_called_once_with("HISTORY", ["3+3 = 6", "2+2 = 4"])

    def test_empty_history_is_a_status_not_an_error(self):
        app = object.__new__(App)
        app.core = types.SimpleNamespace(history=[])
        app._lcd_show_results = mock.Mock()

        App._lcd_start_history(app)

        app._lcd_show_results.assert_called_once_with("HISTORY", ["No saved calculations"])

    def test_integral_template_repairs_a_trailing_decorative_closing_parenthesis(self):
        self.assertEqual(App._repair_integral_body("sin(x)cos(x))"), "sin(x)cos(x)")
        self.assertEqual(App._repair_integral_body("sin(x))cos(x)"), "sin(x))cos(x)")

    def test_history_round_trip_keeps_only_the_latest_ten_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            store = APP_MODULE.SettingsStore(Path(temp) / "settings_store")
            entries = [(f"{number}+1", str(number + 1)) for number in range(12)]

            store.save_history(entries)

            self.assertEqual(store.load_history(), entries[-10:])

    def test_clear_history_preserves_settings_and_persists_an_empty_history(self):
        with tempfile.TemporaryDirectory() as temp:
            database_path=Path(temp) / "settings_store"
            app=_bare_app(database_path)
            app.ui_scale=125
            app.core.settings.angle_unit="GRA"
            app.core.history=[("2+2", "4"), ("3+3", "6")]
            app.history_pos=1
            app._lcd_message=mock.Mock()
            self.assertTrue(app.save_settings_file())

            self.assertTrue(app.clear_calculation_history())

            self.assertEqual(app.core.history, [])
            self.assertEqual(app.history_pos, 0)
            self.assertEqual(app._settings_store().load_history(), [])
            self.assertEqual(app._settings_store().load()["scale"], 125)
            self.assertEqual(
                app._settings_store().load()["calculator.angle_unit"], "GRA"
            )
            app._lcd_message.assert_called_once_with("History cleared")

    def test_atomic_save_state_rolls_back_settings_when_history_write_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings_store"
            store = APP_MODULE.SettingsStore(path)
            store.save_state({"scale": 100}, [("1+1", "2")])
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    "CREATE TRIGGER fail_history_insert BEFORE INSERT ON calculation_history "
                    "BEGIN SELECT RAISE(ABORT, 'injected history failure'); END"
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(sqlite3.DatabaseError):
                store.save_state({"scale": 200}, [("2+2", "4")])

            self.assertEqual(store.load(), {"scale": 100})
            self.assertEqual(store.load_history(), [("1+1", "2")])

    def test_table_two_functions_is_persisted_only_as_a_real_boolean(self):
        self.assertEqual(
            App._sanitize_calculator_settings({"table_two_functions": True}),
            {"table_two_functions": True},
        )
        self.assertEqual(App._sanitize_calculator_settings({"table_two_functions": "On"}), {})

    def test_settings_schema_migrates_v1_and_rejects_future_schema(self):
        migrated = App._migrate_settings({"schema_version": 1, "scale": 125})
        self.assertEqual(migrated["schema_version"], App.SETTINGS_SCHEMA_VERSION)
        self.assertIsNone(App._migrate_settings({"schema_version": 99, "scale": 125}))
    def test_boolean_setup_values_and_legacy_digit_separator_are_normalized(self):
        for name in App.BOOLEAN_SETTINGS:
            with self.subTest(name=name):
                self.assertIs(App._coerce_boolean_setting(name, "On"), True)
                self.assertIs(App._coerce_boolean_setting(name, "Off"), False)

        app = object.__new__(App)
        app.core = types.SimpleNamespace(
            settings=types.SimpleNamespace(digit_separator=False)
        )
        app.saved_config = {
            "calculator_settings": {"digit_separator": "Off"}
        }
        app.apply_saved_engine_settings()
        self.assertIs(app.core.settings.digit_separator, False)

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "settings_store"
            writer = _bare_app(database_path)
            writer.ui_scale = 150
            writer.skin_name = "Blue"
            writer.core.settings.angle_unit = "GRA"
            writer.core.settings.number_digits = 7

            self.assertTrue(writer.save_settings_file())

            reader = _bare_app(database_path)
            reader.load_settings_file()
            self.assertEqual(reader.ui_scale, 150)
            self.assertEqual(reader.skin_name, "Blue")
            self.assertEqual(reader.saved_config["calculator_settings"]["angle_unit"], "GRA")
            self.assertEqual(reader.saved_config["calculator_settings"]["number_digits"], 7)
            self.assertEqual(reader.saved_config["schema_version"], App.SETTINGS_SCHEMA_VERSION)

    def test_settings_loader_discards_unknown_or_invalid_persisted_values(self):
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "settings_store"
            APP_MODULE.SettingsStore(database_path).save({
                "schema_version": App.SETTINGS_SCHEMA_VERSION,
                "scale": 999,
                "skin": "unbundled.png",
                "unexpected": "discarded",
                "calculator.angle_unit": "RAD",
                "calculator.number_digits": 12,
                "calculator.digit_separator": "On",
                "calculator.unknown_setting": "discarded",
            })

            reader = _bare_app(database_path)
            reader.load_settings_file()
            self.assertEqual(reader.ui_scale, 100)
            self.assertEqual(reader.skin_name, "Graphite")
            self.assertEqual(
                reader.saved_config["calculator_settings"],
                {"angle_unit": "RAD", "digit_separator": True},
            )

    def test_reset_removes_store_and_restores_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "settings_store"
            app = _bare_app(database_path)
            app.ui_scale = 200
            app.skin_name = "Pink"
            app.core.settings.angle_unit = "GRA"
            app.core.history = [("2+2", "4")]
            app._rebuild_scaled_ui = mock.Mock()
            self.assertTrue(app.save_settings_file())
            self.assertTrue(list(Path(temp).glob("settings_store*")))

            with mock.patch.object(APP_MODULE.messagebox, "showinfo") as showinfo, mock.patch.object(
                APP_MODULE.messagebox, "showerror"
            ) as showerror:
                self.assertTrue(app.reset_app_settings())

            self.assertEqual(app.ui_scale, 100)
            self.assertEqual(app.skin_name, "Graphite")
            self.assertEqual(app.core.settings.angle_unit, "RAD")
            self.assertEqual(app.core.settings.number_digits, 3)
            self.assertEqual(app.saved_config, {
                "schema_version": App.SETTINGS_SCHEMA_VERSION,
                "scale": 100,
                "skin": "Graphite",
                "calculator_settings": {},
            })
            self.assertIsNone(app._settings_store().load())
            self.assertEqual(app._settings_store().load_history(), [])
            self.assertEqual(app.core.history, [])
            app._rebuild_scaled_ui.assert_called_once_with()
            showinfo.assert_not_called()
            showerror.assert_not_called()

    def test_reset_failure_keeps_in_memory_values_and_reports_lcd_error(self):
        app = object.__new__(App)
        app.ui_scale = 200
        app.skin_name = "Pink"
        app.core = types.SimpleNamespace(settings=DummySettings(), history=[("2+2", "4")])
        app.core.settings.angle_unit = "GRA"
        app._settings_store = mock.Mock()
        app._settings_store.return_value.reset_defaults.side_effect = OSError("read-only")
        app._log_settings_issue = mock.Mock()
        app._rebuild_scaled_ui = mock.Mock()
        app.result = mock.Mock()
        app.status_refresh = mock.Mock()

        self.assertFalse(app.reset_app_settings())

        self.assertEqual(app.ui_scale, 200)
        self.assertEqual(app.skin_name, "Pink")
        self.assertEqual(app.core.settings.angle_unit, "GRA")
        self.assertEqual(app.core.history, [("2+2", "4")])
        app._rebuild_scaled_ui.assert_not_called()
        self.assertIn("Settings ERROR", app.result.config.call_args.kwargs["text"])


class LcdErrorPresenterTests(unittest.TestCase):
    def test_expected_calculator_error_clears_input_and_never_opens_a_popup(self):
        app = object.__new__(App)
        app.shift = True
        app.alpha = True
        app.template_kind = None
        app._lcd_flow = None
        app.set_expr = mock.Mock()
        app.status_refresh = mock.Mock()
        app.result = mock.Mock()

        with mock.patch.object(APP_MODULE.messagebox, "showerror") as showerror:
            app.err(APP_MODULE.CalculatorError("Math ERROR: division by zero"))

        app.set_expr.assert_called_once_with("")
        self.assertFalse(app.shift)
        self.assertFalse(app.alpha)
        self.assertIn("Math ERROR", app.result.config.call_args.kwargs["text"])
        showerror.assert_not_called()

    def test_legacy_turkish_calculator_error_is_rendered_in_english_on_the_lcd(self):
        app = object.__new__(App)
        app.shift = False
        app.alpha = False
        app.template_kind = None
        app._lcd_flow = None
        app.set_expr = mock.Mock()
        app.status_refresh = mock.Mock()
        app.result = mock.Mock()

        app.err(APP_MODULE.CalculatorError("Math ERROR: integral sınırı sayısal olmalıdır"))

        displayed = app.result.config.call_args.kwargs["text"]
        self.assertTrue(displayed.startswith("Math ERROR: integral bound"))
        self.assertNotRegex(displayed, r"[çÇğĞıİöÖşŞüÜ]")

    def test_close_persists_before_destroying(self):
        with tempfile.TemporaryDirectory() as temp:
            database_path = Path(temp) / "settings_store"
            app = _bare_app(database_path)
            app.ui_scale = 75
            app.skin_name = "Pink"
            app.core.settings.angle_unit = "GRA"
            app.destroy = mock.Mock()

            app._on_close()

            app.destroy.assert_called_once_with()
            reader = _bare_app(database_path)
            reader.load_settings_file()
            self.assertEqual(reader.ui_scale, 75)
            self.assertEqual(reader.skin_name, "Pink")
            self.assertEqual(reader.saved_config["calculator_settings"]["angle_unit"], "GRA")

    def test_shift_ac_uses_persisting_close_path(self):
        app = object.__new__(App)
        app.shift = True
        app._on_close = mock.Mock()

        app.ac_key()

        app._on_close.assert_called_once_with()

    def test_ac_cancels_work_and_restores_the_active_mode(self):
        app = object.__new__(App)
        app._calculation_busy = True
        app.calculation_controller = types.SimpleNamespace(cancel=mock.Mock())
        app._reset_active_mode_after_ac = mock.Mock()

        App.ac_key(app)

        app.calculation_controller.cancel.assert_called_once_with()
        app._reset_active_mode_after_ac.assert_called_once_with()

    def test_shift_ac_cancels_busy_work_instead_of_closing(self):
        app = object.__new__(App)
        app._calculation_busy = True
        app.shift = True
        app.calculation_controller = types.SimpleNamespace(cancel=mock.Mock())
        app._reset_active_mode_after_ac = mock.Mock()
        app._on_close = mock.Mock()

        App.ac_key(app)

        app.calculation_controller.cancel.assert_called_once_with()
        app._reset_active_mode_after_ac.assert_called_once_with()
        app._on_close.assert_not_called()

    def test_escape_routes_to_ac_while_calculation_is_busy(self):
        app = object.__new__(App)
        app._calculation_busy = True
        app.ac_key = mock.Mock()

        result = App._physical_keypress(app, types.SimpleNamespace(keysym="Escape"))

        self.assertEqual(result, "break")
        app.ac_key.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
