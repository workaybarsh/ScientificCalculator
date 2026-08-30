"""Keypad actions and the prompted dialogs they open.

Each key selects one visible action, and each dialog validates its prompted
values before any background work starts.  These tests cover the success,
cancel, and failure decision a user can make in those dialogs.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
import scipy.integrate
import scipy.stats
import sympy as sp

from scientific_calculator import app as app_module
from scientific_calculator.app import App


class _Entry:
    def __init__(self, text: str = "", cursor: int | None = None, *, raises_on_index: bool = False) -> None:
        self.text = text
        self.cursor = len(text) if cursor is None else cursor
        self.raises_on_index = raises_on_index

    def get(self) -> str:
        return self.text

    def index(self, _where: object) -> int:
        if self.raises_on_index:
            raise RuntimeError("no cursor")
        return self.cursor


class _Result:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls: list[str] = []

    def config(self, **options: object) -> None:
        if "text" in options:
            self.text = str(options["text"])
            self.calls.append(self.text)

    def cget(self, _name: str) -> str:
        return self.text


def _key_app(*, text: str = "", mode: str = "Calculate") -> App:
    app = object.__new__(App)
    app.expr = _Entry(text)
    app.result = _Result()
    app.mode = mode
    app.shift = False
    app.alpha = False
    app.base = 10
    app.template_kind = None
    app.core = SimpleNamespace(
        ans=12,
        memory={},
        settings=SimpleNamespace(angle_unit="RAD"),
    )
    app.insert = mock.Mock()
    app.consume = mock.Mock()
    app.status_refresh = mock.Mock()
    app.err = mock.Mock()
    return app


def test_context_and_function_token_insertion_use_the_visible_cursor() -> None:
    app = _key_app(text="12x", mode="Calculate")
    app.template_kind = "integral"
    app._active_template_field = mock.Mock(return_value="body")
    app.template_fields = {"body": "sin(x)"}
    app.template_cursors = {"body": 3}

    assert App._left_context(app) == "sin"
    app._active_template_field.assert_called_once_with()

    app.template_kind = None
    app.expr = _Entry("123+", 2)
    assert App._left_context(app) == "12"
    app.expr = _Entry("123+", raises_on_index=True)
    assert App._left_context(app) == "123+"

    app._left_context = mock.Mock(return_value="2")
    App._insert_function_token(app, "sin(")
    app.insert.assert_called_once_with("×sin(")

    app.insert.reset_mock()
    app._left_context.return_value = "+"
    App._insert_function_token(app, "cos(")
    app.insert.assert_called_once_with("cos(")


def test_number_variable_power_log_and_root_keys_select_the_correct_visible_action() -> None:
    app = _key_app()
    app.constants_dialog = mock.Mock()
    app.conversions_dialog = mock.Mock()
    app.reset_dialog = mock.Mock()

    for key, target in (("7", app.constants_dialog), ("8", app.conversions_dialog), ("9", app.reset_dialog)):
        app.shift = True
        App.num_key(app, key)
        target.assert_called_once_with()
        app.consume.assert_called()
        target.reset_mock()
        app.consume.reset_mock()

    app.shift = False
    App.num_key(app, "4")
    app.insert.assert_called_with("4")

    app._history_lcd_active = mock.Mock(return_value=True)
    app.sum_dialog = mock.Mock()
    app.insert.reset_mock()
    App.x_key(app)
    app.consume.assert_called_once_with()
    app.insert.assert_not_called()

    app.consume.reset_mock()
    app._history_lcd_active.return_value = False
    app.shift = True
    App.x_key(app)
    app.sum_dialog.assert_called_once_with()
    app.consume.assert_called_once_with()

    app.shift = False
    app.insert.reset_mock()
    App.x_key(app)
    app.insert.assert_called_once_with("x")

    app.shift = True
    App.fraction_key(app)
    app.insert.assert_called_with(" + 1/2")
    app._insert_function_token = mock.Mock()
    App.sqrt_key(app)
    app._insert_function_token.assert_called_once_with("cbrt(")

    app.mode = "Base-N"
    app.consume.reset_mock()
    App.square_key(app)
    assert app.base == 10
    app.status_refresh.assert_called()
    app.consume.assert_called_once_with()

    app.mode = "Calculate"
    app.shift = False
    app.insert.reset_mock()
    App.square_key(app)
    app.insert.assert_called_once_with("^2")
    app.shift = True
    app.insert.reset_mock()
    App.square_key(app)
    app.insert.assert_called_once_with("^3")

    app.mode = "Base-N"
    app.consume.reset_mock()
    App.power_key(app)
    assert app.base == 16
    app.consume.assert_called_once_with()

    app.mode = "Calculate"
    app.shift = True
    app.insert.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askstring", return_value="3"):
        App.power_key(app)
    app.insert.assert_called_once_with("^(1/(3))")

    app.insert.reset_mock()
    app.consume.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askstring", return_value=None):
        App.power_key(app)
    app.insert.assert_not_called()
    app.consume.assert_called_once_with()

    app.shift = False
    app.insert.reset_mock()
    App.power_key(app)
    app.insert.assert_called_once_with("^")

    for method, base, normal, shifted in (
        (App.log_key, 2, "log(", "10^("),
        (App.ln_key, 8, "ln(", "e^("),
    ):
        app.mode = "Base-N"
        app.shift = False
        app._insert_function_token = mock.Mock()
        method(app)
        assert app.base == base
        app.mode = "Calculate"
        app._insert_function_token.reset_mock()
        method(app)
        app._insert_function_token.assert_called_once_with(normal)
        app.shift = True
        app._insert_function_token.reset_mock()
        method(app)
        app._insert_function_token.assert_called_once_with(shifted)


def test_alpha_modifier_and_prime_factorization_keys_keep_each_shortcut_distinct() -> None:
    app = _key_app()
    app.alpha = True
    App.neg_key(app)
    app.insert.assert_called_once_with("A")

    app.alpha = False
    app.shift = True
    app.insert.reset_mock()
    App.neg_key(app)
    app.insert.assert_called_once_with("log(")
    app.shift = False
    app.insert.reset_mock()
    App.neg_key(app)
    app.insert.assert_called_once_with("-")

    app.alpha = True
    app.insert.reset_mock()
    App.dms_key(app)
    app.insert.assert_called_once_with("B")

    app.alpha = False
    app.shift = True
    app.core.prime_factorization = mock.Mock(return_value={2: 2, 3: 1})
    App.dms_key(app)
    assert app.result.text == "2^2 × 3"
    app.consume.assert_called()

    app.err.reset_mock()
    app.core.prime_factorization.side_effect = ValueError("not factorable")
    App.dms_key(app)
    app.err.assert_called_once()

    app.shift = False
    app.dms_dialog = mock.Mock()
    App.dms_key(app)
    app.dms_dialog.assert_called_once_with()

    app.alpha = True
    app.insert.reset_mock()
    App.inv_key(app)
    app.insert.assert_called_once_with("C")
    app.alpha = False
    app.shift = True
    app.insert.reset_mock()
    App.inv_key(app)
    app.insert.assert_called_once_with("factorial(")

    app.alpha = True
    app.insert.reset_mock()
    App.trig_key(app, "cos")
    app.insert.assert_called_once_with("E")
    app.alpha = False
    app.shift = True
    app._insert_function_token = mock.Mock()
    App.trig_key(app, "sin")
    app._insert_function_token.assert_called_once_with("asin(")

    app.shift = True
    app._insert_function_token.reset_mock()
    App.lparen_key(app)
    app._insert_function_token.assert_called_once_with("Abs(")
    app.shift = False
    app.insert.reset_mock()
    App.lparen_key(app)
    app.insert.assert_called_once_with("(")

    app.alpha = True
    app.insert.reset_mock()
    App.rparen_key(app)
    app.insert.assert_called_once_with("x")
    app.alpha = False
    app.shift = True
    app.insert.reset_mock()
    App.rparen_key(app)
    app.insert.assert_called_once_with(",")

    app.alpha = True
    app.insert.reset_mock()
    App.sci_key(app)
    app.insert.assert_called_once_with("e")
    app.alpha = False
    app.shift = True
    app.insert.reset_mock()
    App.sci_key(app)
    app.insert.assert_called_once_with("π")
    app.shift = False
    app.insert.reset_mock()
    App.ans_key(app)
    app.insert.assert_called_once_with("Ans")
    app.shift = True
    app.insert.reset_mock()
    App.ans_key(app)
    app.insert.assert_called_once_with("%")


def test_storage_engineering_fraction_and_memory_keys_report_real_results() -> None:
    app = _key_app()
    app.core.format_result = mock.Mock(return_value="12")
    app.core.store = mock.Mock()
    app.recall_dialog = mock.Mock()

    app.shift = True
    App.sto_key(app)
    app.recall_dialog.assert_called_once_with()

    app.shift = False
    with mock.patch.object(app_module.simpledialog, "askstring", return_value=" A "):
        App.sto_key(app)
    app.core.store.assert_called_once_with("A", 12)
    assert app.result.text == " A =12"

    app.core.store.reset_mock()
    app.consume.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askstring", return_value=None):
        App.sto_key(app)
    app.core.store.assert_not_called()
    app.consume.assert_called_once_with()

    app.core.store.side_effect = ValueError("bad name")
    with mock.patch.object(app_module.simpledialog, "askstring", return_value="?"):
        App.sto_key(app)
    app.err.assert_called()

    app.mode = "Complex"
    app.shift = False
    app.insert.reset_mock()
    App.eng_key(app)
    app.insert.assert_called_once_with("i")
    app.shift = True
    app.insert.reset_mock()
    App.eng_key(app)
    app.insert.assert_called_once_with("∠")

    app.mode = "Calculate"
    app.shift = False
    app.consume.reset_mock()
    app.core.ans = 1234
    App.eng_key(app)
    assert app.result.text == "1.234×10^3"
    app.consume.assert_called_once_with()

    app.core.ans = object()
    app.err.reset_mock()
    App.eng_key(app)
    app.err.assert_called_once()

    app.alpha = True
    app.insert.reset_mock()
    App.sd_key(app)
    app.insert.assert_called_once_with("y")

    app.alpha = False
    app.shift = True
    app.core.ans = sp.Rational(7, 3)
    App.sd_key(app)
    assert app.result.text == "2 1/3"

    app.shift = False
    app.result.text = "1/3"
    app.core.ans = sp.Rational(1, 3)
    App.sd_key(app)
    assert app.core.format_result.call_args.args[1:] == (True,)

    app.result.text = "decimal"
    App.sd_key(app)
    assert app.core.format_result.call_args.args[1:] == (False,)

    app.core.ans = object()
    app.err.reset_mock()
    App.sd_key(app)
    app.err.assert_called_once()

    app.alpha = True
    app.insert.reset_mock()
    App.mplus_key(app)
    app.insert.assert_called_once_with("M")

    app.alpha = False
    app.shift = False
    app.core.m_plus = mock.Mock(return_value=4)
    App.mplus_key(app)
    assert app.result.text == "M=12"
    app.shift = True
    app.core.m_minus = mock.Mock(return_value=3)
    App.mplus_key(app)
    app.core.m_minus.assert_called_once_with()

    app.core.m_minus.side_effect = ValueError("bad memory")
    app.err.reset_mock()
    App.mplus_key(app)
    app.err.assert_called_once()


def test_combination_random_and_polar_shortcuts_cover_success_cancel_and_failure() -> None:
    app = _key_app()
    app.comb_dialog = mock.Mock()

    app.shift = True
    App.mul_key(app)
    app.comb_dialog.assert_called_once_with("nPr")
    app.comb_dialog.reset_mock()
    App.div_key(app)
    app.comb_dialog.assert_called_once_with("nCr")

    app.shift = False
    app.insert.reset_mock()
    App.mul_key(app)
    App.div_key(app)
    assert app.insert.call_args_list == [mock.call("×"), mock.call("÷")]

    app.set_expr = mock.Mock()
    app.show = mock.Mock()
    app._persist_calculation_history = mock.Mock()
    app.core.evaluate = mock.Mock(return_value=10)
    with mock.patch.object(app_module.simpledialog, "askinteger", side_effect=[5, 2]):
        App.comb_dialog(app, "nCr")
    app.set_expr.assert_called_once_with("nCr(5,2)")
    app.show.assert_called_once_with(10)
    app._persist_calculation_history.assert_called_once_with()

    app.set_expr.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askinteger", side_effect=[None, 2]):
        App.comb_dialog(app, "nPr")
    app.set_expr.assert_not_called()

    app.core.evaluate.side_effect = ValueError("bad combination")
    app.err.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askinteger", side_effect=[5, 2]):
        App.comb_dialog(app, "nPr")
    app.err.assert_called_once()

    app.pol_dialog = mock.Mock()
    app.rec_dialog = mock.Mock()
    app.shift = True
    App.plus_key(app)
    App.minus_key(app)
    app.pol_dialog.assert_called_once_with()
    app.rec_dialog.assert_called_once_with()
    app.shift = False
    app.insert.reset_mock()
    App.plus_key(app)
    App.minus_key(app)
    assert app.insert.call_args_list == [mock.call("+"), mock.call("−")]

    app.alpha = True
    app.core.random_int = mock.Mock(return_value=7)
    app.insert.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askinteger", side_effect=[1, 10]):
        App.dot_key(app)
    app.insert.assert_called_once_with("7")

    app.consume.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askinteger", side_effect=[None, 10]):
        App.dot_key(app)
    app.consume.assert_called_once_with()

    app.core.random_int.side_effect = ValueError("invalid range")
    app.err.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askinteger", side_effect=[10, 1]):
        App.dot_key(app)
    app.err.assert_called_once()

    app.alpha = False
    app.shift = True
    app.core.random_number = mock.Mock(return_value=0.25)
    app.insert.reset_mock()
    App.dot_key(app)
    app.insert.assert_called_once_with("0.25")
    app.shift = False
    app.insert.reset_mock()
    App.dot_key(app)
    app.insert.assert_called_once_with(".")


def test_equals_base_complex_and_approximation_paths_use_the_engine_contract() -> None:
    base = _key_app(text="FF", mode="Base-N")
    base._calculation_busy = False
    base._history_lcd_active = mock.Mock(return_value=False)
    base._lcd_flow_active = mock.Mock(return_value=False)
    base.core.evaluate_base = mock.Mock(return_value=255)
    base.core.format_base = mock.Mock(return_value="FF")
    App.equals(base)
    assert base.core.ans == 255
    assert base.result.text == "FF"
    base.consume.assert_called_once_with()

    base.core.evaluate_base.side_effect = ValueError("bad base")
    base.err.reset_mock()
    App.equals(base)
    base.err.assert_called_once()

    complex_app = _key_app(text="1+i", mode="Complex")
    complex_app._calculation_busy = False
    complex_app._history_lcd_active = mock.Mock(return_value=False)
    complex_app._lcd_flow_active = mock.Mock(return_value=False)
    complex_app.show = mock.Mock()
    complex_app._run_background_calculation = mock.Mock()
    App.equals(complex_app)
    method, args, callback = complex_app._run_background_calculation.call_args.args
    assert (method, args) == ("complex_eval", ("1+i",))
    callback(1 + 1j)
    complex_app.show.assert_called_once_with(1 + 1j)
    assert complex_app._last_submitted_expression == "1+i"

    approx = _key_app(text="pi")
    approx._run_background_calculation = mock.Mock()
    approx.show = mock.Mock()
    App.approx(approx)
    method, args, callback = approx._run_background_calculation.call_args.args
    assert (method, args) == ("evaluate", ("pi", False))
    callback(3.14)
    approx.show.assert_called_once_with(3.14, True)


def test_calc_and_solve_dialogs_validate_prompted_values_before_background_work() -> None:
    calc = _key_app(text="A+x")
    calc.core.memory = {"A": 2, "x": 3}
    calc._run_background_calculation = mock.Mock()
    calc.show = mock.Mock()
    with mock.patch.object(app_module.simpledialog, "askfloat", side_effect=[4.0, 5.0]):
        App.calc_dialog(calc)
    calc._run_background_calculation.assert_called_once_with(
        "evaluate_with_values", ("A+x", {"A": 4.0, "x": 5.0}), calc.show
    )

    plain = _key_app(text="2+2")
    plain._run_background_calculation = mock.Mock()
    plain.show = mock.Mock()
    App.calc_dialog(plain)
    plain._run_background_calculation.assert_called_once_with("evaluate", ("2+2",), plain.show)

    cancelled = _key_app(text="x")
    cancelled.core.memory = {"x": 0}
    cancelled._run_background_calculation = mock.Mock()
    with mock.patch.object(app_module.simpledialog, "askfloat", return_value=None):
        App.calc_dialog(cancelled)
    cancelled._run_background_calculation.assert_not_called()

    invalid_mode = _key_app(text="x=1", mode="Complex")
    App.solve_dialog(invalid_mode)
    invalid_mode.err.assert_called_once_with("SOLVE is available only in Calculate mode")

    template = _key_app(text="x=1")
    template.template_kind = "integral"
    App.solve_dialog(template)
    template.err.assert_called_once_with("Exit the integral/derivative template with AC before using SOLVE")

    blank = _key_app(text="")
    App.solve_dialog(blank)
    blank.err.assert_called_once_with("Enter an equation")

    bad_symbols = _key_app(text="x=1")
    bad_symbols.core.equation_symbols = mock.Mock(side_effect=ValueError("bad equation"))
    App.solve_dialog(bad_symbols)
    bad_symbols.err.assert_called_once()

    no_symbols = _key_app(text="1=1")
    no_symbols.core.equation_symbols = mock.Mock(return_value=[])
    App.solve_dialog(no_symbols)
    no_symbols.err.assert_called_once_with("Variable ERROR: no variable to solve in the equation")

    invalid_variable = _key_app(text="x+y=2")
    invalid_variable.core.equation_symbols = mock.Mock(return_value=["x", "y"])
    with mock.patch.object(app_module.simpledialog, "askstring", return_value="z"):
        App.solve_dialog(invalid_variable)
    invalid_variable.err.assert_called_once_with("Variable ERROR: selected variable is not in the equation")

    solve = _key_app(text="x+y=2")
    solve.core.memory = {"x": 1, "y": 2}
    solve.core.equation_symbols = mock.Mock(return_value=["x", "y"])
    solve._run_background_calculation = mock.Mock()
    with (
        mock.patch.object(app_module.simpledialog, "askstring", return_value="x"),
        mock.patch.object(app_module.simpledialog, "askfloat", side_effect=[1.5, 0.5]),
    ):
        App.solve_dialog(solve)
    method, args, callback = solve._run_background_calculation.call_args.args
    assert (method, args) == ("solve", ("x+y=2", "x", 1.5, {"y": 0.5}))
    callback((1.25, 0.001))
    assert solve.result.text == "x=1.25   L-R=0.001"

    cancelled_guess = _key_app(text="x=1")
    cancelled_guess.core.equation_symbols = mock.Mock(return_value=["x"])
    cancelled_guess._run_background_calculation = mock.Mock()
    with mock.patch.object(app_module.simpledialog, "askfloat", return_value=None):
        App.solve_dialog(cancelled_guess)
    cancelled_guess._run_background_calculation.assert_not_called()


def test_auxiliary_math_dialogs_and_complex_base_operations_cover_their_user_decisions() -> None:
    app = _key_app(text="x+1")
    app._run_background_calculation = mock.Mock()
    app.show = mock.Mock()
    with mock.patch.object(app_module.simpledialog, "askstring", side_effect=["x+1", "1", "4"]):
        App.sum_dialog(app)
    assert app._run_background_calculation.call_args.args[:2] == ("summation", ("x+1", "1", "4"))

    app._run_background_calculation.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askstring", side_effect=[None, "1", "4"]):
        App.sum_dialog(app)
    app._run_background_calculation.assert_not_called()

    app.core.pol = mock.Mock(return_value=(5.0, 0.9273))
    with mock.patch.object(app_module.simpledialog, "askfloat", side_effect=[3.0, 4.0]):
        App.pol_dialog(app)
    assert app.result.text == "r=5, θ=0.9273"

    app.core.rec = mock.Mock(return_value=(3.0, 4.0))
    with mock.patch.object(app_module.simpledialog, "askfloat", side_effect=[5.0, 0.9273]):
        App.rec_dialog(app)
    assert app.result.text == "x=3, y=4"

    app.expr = _Entry("-0.5")
    app.core.dms_from_decimal = mock.Mock(return_value=(-0.0, 30, 0.0))
    App.dms_dialog(app)
    assert app._run_background_calculation.call_args.args[:2] == ("evaluate", ("-0.5",))
    app._run_background_calculation.call_args.args[2](-0.5)
    assert app.result.text == "-0° 30′ 0″"

    app.expr = _Entry("")
    app.core.decimal_from_dms = mock.Mock(return_value=12.5)
    with mock.patch.object(app_module.simpledialog, "askfloat", side_effect=[12.0, 30.0, 0.0]):
        App.dms_dialog(app)
    assert app.result.text == "12.5"

    app._run_background_calculation.side_effect = ValueError("bad DMS")
    app.expr = _Entry("bad")
    app.err.reset_mock()
    App.dms_dialog(app)
    app.err.assert_called_once()

    app.expr = _Entry("3+4i")
    app.core.to_polar = mock.Mock(return_value=(5.0, 53.13))
    app._run_background_calculation = mock.Mock()
    App.complex_to_polar(app)
    method, args, callback = app._run_background_calculation.call_args.args
    assert (method, args) == ("complex_eval", ("3+4i",))
    callback(3 + 4j)
    assert app.result.text == "5∠53.13"

    app.core.from_polar = mock.Mock(return_value=3 + 4j)
    app.core.format_result = mock.Mock(return_value="3+4i")
    with mock.patch.object(app_module.simpledialog, "askfloat", side_effect=[5.0, 53.13]):
        App.complex_from_polar(app)
    assert app.result.text == "3+4i"

    app.expr = _Entry("1010")
    app.base = 2
    app.core.evaluate_base = mock.Mock(side_effect=[10, 3])
    app.core.base_operation = mock.Mock(return_value=2)
    app.core.format_base = mock.Mock(return_value="10")
    with mock.patch.object(app_module.simpledialog, "askstring", return_value="11"):
        App.base_logic_dialog(app, "and")
    app.core.base_operation.assert_called_once_with(10, 3, "and")
    assert app.result.text == "10"

    app.core.evaluate_base.reset_mock()
    app.core.base_operation.reset_mock()
    app.core.evaluate_base.side_effect = None
    app.core.evaluate_base.return_value = 10
    app.core.base_operation.return_value = -10
    App.base_logic_dialog(app, "Neg")
    app.core.base_operation.assert_called_once_with(10, None, "Neg")

    app.core.base_operation.reset_mock()
    with mock.patch.object(app_module.simpledialog, "askstring", return_value=None):
        App.base_logic_dialog(app, "or")
    app.core.base_operation.assert_not_called()

    app.core.evaluate_base.side_effect = ValueError("bad base")
    app.err.reset_mock()
    App.base_logic_dialog(app, "Not")
    app.err.assert_called_once()


class _PackWidget:
    def pack(self, *_args: object, **_kwargs: object) -> None:
        pass


class _Dialog(_PackWidget):
    def __init__(self) -> None:
        self.titles: list[str] = []
        self.destroy = mock.Mock()

    def title(self, text: str) -> None:
        self.titles.append(text)

    def geometry(self, _value: str) -> None:
        pass

    def resizable(self, *_values: object) -> None:
        pass


class _StringVar:
    instances: list[_StringVar] = []

    def __init__(self, value: object = "") -> None:
        self.value = str(value)
        self.__class__.instances.append(self)

    def get(self) -> str:
        return self.value

    def set(self, value: object) -> None:
        self.value = str(value)


class _Button(_PackWidget):
    instances: list[_Button] = []

    def __init__(self, _parent: object, *, text: str, command: object, **_kwargs: object) -> None:
        self.text = text
        self.command = command
        self.__class__.instances.append(self)


class _Listbox(_PackWidget):
    instances: list[_Listbox] = []

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.values: list[str] = []
        self.selection: tuple[int, ...] = ()
        self.__class__.instances.append(self)

    def insert(self, _index: object, value: object) -> None:
        self.values.append(str(value))

    def curselection(self) -> tuple[int, ...]:
        return self.selection


def _button(text: str) -> _Button:
    return next(button for button in _Button.instances if button.text == text)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        input_output="MathI/MathO",
        angle_unit="RAD",
        number_format="Norm",
        number_digits=5,
        engineer_symbol=False,
        fraction_result="d/c",
        complex_format="a+bi",
        statistics_freq=False,
        spreadsheet_auto_calc=True,
        spreadsheet_show_cell="Formula",
        equation_complex=False,
        table_two_functions=False,
        decimal_mark="Dot",
        digit_separator=False,
        multiline_font="Normal",
        constant_dataset=app_module.CONSTANTS_DATASET_LABELS[0],
    )


def _patch_basic_dialogs(window: _Dialog):
    return (
        mock.patch.object(app_module.tk, "Toplevel", return_value=window),
        mock.patch.object(app_module.tk, "StringVar", _StringVar),
        mock.patch.object(app_module.ttk, "Frame", return_value=_PackWidget()),
        mock.patch.object(app_module.ttk, "Label", return_value=_PackWidget()),
        mock.patch.object(app_module.ttk, "Combobox", return_value=_PackWidget()),
        mock.patch.object(app_module.ttk, "Button", _Button),
    )


def test_setup_dialog_persists_validated_choices_and_exposes_clear_and_reset_controls() -> None:
    _Button.instances.clear()
    _StringVar.instances.clear()
    app = _key_app()
    app.core.settings = _settings()
    app.skin_name = "Graphite"
    app.ui_scale = 100
    app._validated_skin_name = mock.Mock(side_effect=lambda value: value)
    app._coerce_boolean_setting = mock.Mock(side_effect=lambda _key, value: value == "On")
    app._fit_ui_scale_to_display = mock.Mock(return_value=125)
    app.save_settings_file = mock.Mock(return_value=True)
    app._rebuild_scaled_ui = mock.Mock()
    app._lcd_message = mock.Mock()
    app.reset_app_settings = mock.Mock(return_value=False)
    app.clear_calculation_history = mock.Mock()
    window = _Dialog()

    patches = _patch_basic_dialogs(window)
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        mock.patch.object(app_module.messagebox, "askyesno", side_effect=[False, True]),
    ):
        App.setup_dialog(app)
        assert len(_StringVar.instances) == 18
        _StringVar.instances[3].set("8")
        _StringVar.instances[4].set("On")
        _StringVar.instances[11].set("f(x),g(x)")
        _StringVar.instances[16].set("Blue")
        _StringVar.instances[17].set("125")
        _button("Save").command()
        assert app.core.settings.number_digits == 8
        assert app.core.settings.engineer_symbol is True
        assert app.core.settings.table_two_functions is True
        assert app.skin_name == "Blue"
        assert app.ui_scale == 125
        app.save_settings_file.assert_called_once_with(False)
        app._rebuild_scaled_ui.assert_called_once_with()
        app._lcd_message.assert_called_once_with("Settings saved")

        _button("Clear History").command()
        app.clear_calculation_history.assert_not_called()
        _button("Clear History").command()
        app.clear_calculation_history.assert_called_once_with()
        _button("Reset to Defaults").command()
        assert window.destroy.call_count == 1


def test_setup_dialog_rolls_back_unsaved_changes_and_reset_closes_only_after_success() -> None:
    _Button.instances.clear()
    _StringVar.instances.clear()
    app = _key_app()
    original_settings = _settings()
    app.core.settings = original_settings
    app.skin_name = "Graphite"
    app.ui_scale = 100
    app._validated_skin_name = mock.Mock(side_effect=lambda value: value)
    app._coerce_boolean_setting = mock.Mock(side_effect=lambda _key, value: value == "On")
    app._fit_ui_scale_to_display = mock.Mock(return_value=125)
    app.save_settings_file = mock.Mock(return_value=False)
    app.err = mock.Mock()
    app.reset_app_settings = mock.Mock(return_value=True)
    window = _Dialog()

    patches = _patch_basic_dialogs(window)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        App.setup_dialog(app)
        _StringVar.instances[16].set("Pink")
        _StringVar.instances[17].set("125")
        _button("Save").command()
        assert vars(app.core.settings) == vars(original_settings)
        assert app.skin_name == "Graphite"
        assert app.ui_scale == 100
        app.err.assert_called_once()

        _button("Reset to Defaults").command()
        app.reset_app_settings.assert_called_once_with()
        window.destroy.assert_called_once_with()


def test_small_tk_dialogs_keep_real_insert_conversion_reset_and_help_handlers() -> None:
    _Button.instances.clear()
    _Listbox.instances.clear()
    app = _key_app()
    app.core.settings.constant_dataset = app_module.CONSTANTS_DATASET_LABELS[0]
    app.insert = mock.Mock()
    constants_window = _Dialog()
    with (
        mock.patch.object(app_module.tk, "Toplevel", return_value=constants_window),
        mock.patch.object(app_module.tk, "Listbox", _Listbox),
        mock.patch.object(app_module.ttk, "Label", return_value=_PackWidget()),
        mock.patch.object(app_module.ttk, "Button", _Button),
    ):
        App.constants_dialog(app)
        choices = _Listbox.instances[-1]
        _button("Insert").command()
        app.insert.assert_not_called()
        choices.selection = (0,)
        _button("Insert").command()
    app.insert.assert_called_once()
    constants_window.destroy.assert_called_once_with()

    _Button.instances.clear()
    _Listbox.instances.clear()
    _StringVar.instances.clear()
    conversion_window = _Dialog()
    app.core.ans = 2
    app.core.format_result = mock.Mock(return_value="2")
    app.core.convert = mock.Mock(return_value=4.5)
    with (
        mock.patch.object(app_module.tk, "Toplevel", return_value=conversion_window),
        mock.patch.object(app_module.tk, "StringVar", _StringVar),
        mock.patch.object(app_module.tk, "Listbox", _Listbox),
        mock.patch.object(app_module.ttk, "Entry", return_value=_PackWidget()),
        mock.patch.object(app_module.ttk, "Button", _Button),
    ):
        App.conversions_dialog(app)
        _StringVar.instances[-1].set("2,5")
        _Listbox.instances[-1].selection = (0,)
        _button("Convert").command()
    app.core.convert.assert_called_once()
    assert app.core.ans == sp.Float(4.5)
    conversion_window.destroy.assert_called_once_with()

    with mock.patch.object(app_module.messagebox, "showinfo") as showinfo:
        app.core.memory = {"A": 2}
        App.recall_dialog(app)
        App.help_key(app)
    assert showinfo.call_count == 2

    _Button.instances.clear()
    reset_window = _Dialog()
    app.core.settings = _settings()
    app.core.reset_memory = mock.Mock()
    app.core.initialize_all = mock.Mock()
    app.sheet = SimpleNamespace(delete_all=mock.Mock())
    app.status_refresh = mock.Mock()
    with (
        mock.patch.object(app_module.tk, "Toplevel", return_value=reset_window),
        mock.patch.object(app_module.ttk, "Button", _Button),
    ):
        App.reset_dialog(app)
        _button("Setup Data").command()
        _button("Memory").command()
        _button("Initialize All").command()
    app.core.reset_memory.assert_called_once_with()
    app.core.initialize_all.assert_called_once_with()
    app.sheet.delete_all.assert_called_once_with()
    assert reset_window.destroy.call_count == 3

    app._start_lcd_flow = mock.Mock()
    App.mode_workspace(app, "Matrix")
    app._start_lcd_flow.assert_called_once_with("Matrix")
    app._start_lcd_flow.reset_mock()
    App.mode_workspace(app, "Calculate")
    app._start_lcd_flow.assert_not_called()

    app.core.settings.spreadsheet_show_cell = "Formula"
    app.sheet = SimpleNamespace(cells={"A1": "=1+1"}, cache={"A1": 2}, dirty_cells={"A1"})
    assert App._spreadsheet_display_value(app, "A1") == "=1+1"
    app.core.settings.spreadsheet_show_cell = "Value"
    assert App._spreadsheet_display_value(app, "B1") == ""
    assert App._spreadsheet_display_value(app, "A1") == "2 *"
    app.sheet.dirty_cells = set()
    assert App._spreadsheet_display_value(app, "A1") == 2


def test_packaged_smoke_and_entrypoint_cover_success_and_failure_without_a_tk_window() -> None:
    class _Skin:
        size = (480, 980)

        def __enter__(self) -> _Skin:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

    engine = SimpleNamespace(evaluate=mock.Mock(return_value=4))
    with (
        mock.patch.object(app_module.os.path, "isfile", return_value=True),
        mock.patch.object(app_module.Image, "open", return_value=_Skin()),
        mock.patch.object(app_module, "ScientificCalculatorEngine", return_value=engine),
    ):
        app_module.run_smoke_test()
    engine.evaluate.assert_called_once_with("2+2")

    with (
        mock.patch.object(app_module.os.path, "isfile", return_value=False),
        pytest.raises(RuntimeError, match="Required packaged asset"),
    ):
        app_module.run_smoke_test()

    # The SciPy checks guard a narrowed PyInstaller collection, so their
    # failure paths have to be real rather than assumed.
    engine = SimpleNamespace(evaluate=mock.Mock(return_value=4))
    for target, attribute, replacement, message in (
        (scipy.stats.norm, "pdf", lambda *_a, **_k: 5.0, "SciPy stats"),
        (scipy.integrate, "quad", lambda *_a, **_k: (99.0, 0.0), "SciPy integrate"),
    ):
        with (
            mock.patch.object(app_module.os.path, "isfile", return_value=True),
            mock.patch.object(app_module.Image, "open", return_value=_Skin()),
            mock.patch.object(app_module, "ScientificCalculatorEngine", return_value=engine),
            mock.patch.object(target, attribute, replacement),
            pytest.raises(RuntimeError, match=message),
        ):
            app_module.run_smoke_test()

    ui = SimpleNamespace(mainloop=mock.Mock())
    with (
        mock.patch.object(app_module.multiprocessing, "freeze_support") as freeze_support,
        mock.patch.object(app_module.sys, "argv", ["scientific-calculator"]),
        mock.patch.object(app_module, "App", return_value=ui),
    ):
        app_module.main()
    freeze_support.assert_called_once_with()
    ui.mainloop.assert_called_once_with()

    with (
        mock.patch.object(app_module.sys, "argv", ["scientific-calculator", "--smoke-test"]),
        mock.patch.object(app_module, "run_smoke_test", side_effect=RuntimeError("missing asset")),
        mock.patch("builtins.print") as output,
        pytest.raises(SystemExit, match="1"),
    ):
        app_module.main()
    assert "Scientific Calculator smoke test failed" in output.call_args.args[0]
