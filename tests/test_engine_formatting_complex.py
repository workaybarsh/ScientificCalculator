import pytest
import sympy as sp

from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine():
    return ScientificCalculatorEngine()


def test_exact_fraction_and_radical_results(engine):
    fraction = engine.evaluate("1/3")
    radical = engine.evaluate("sqrt(8)")
    assert fraction == sp.Rational(1, 3)
    assert engine.format_result(fraction) == "1/3"
    assert radical == 2 * sp.sqrt(2)
    assert engine.format_result(radical) == "2*√(2)"


def test_mixed_fraction_result(engine):
    engine.settings.fraction_result = "a b/c"
    assert engine.format_result(sp.Rational(7, 3)) == "2 1/3"
    assert engine.format_result(sp.Rational(-7, 3)) == "-2 1/3"


def test_decimal_output_respects_number_digits(engine):
    engine.settings.input_output = "MathI/DecimalO"
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 4
    result = engine.evaluate("1/3")
    assert engine.format_result(result) == "0.3333"


def test_number_format_fix_sci_norm_and_digits(engine):
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 2
    assert engine.format_result(1234.567) == "1234.57"

    engine.settings.number_format = "Sci"
    engine.settings.number_digits = 3
    assert engine.format_result(1234.567) == "1.23e+03"

    engine.settings.number_format = "Norm"
    assert engine.format_result(1234.567) == "1234.567"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (5e-11, "0.00000000005"),
        (1e-13, "0.0000000000001"),
        (-2.5e-8, "-0.000000025"),
        (0.0, "0"),
    ],
)
def test_decimal_result_display_preserves_small_nonzero_values(engine, value, expected):
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 3
    assert engine.format_result(value, approximate=True) == expected


def test_decimal_mark_and_digit_separator(engine):
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 2
    engine.settings.digit_separator = True
    assert engine.format_result(1234.5) == "1,234.50"
    engine.settings.digit_separator = False
    engine.settings.decimal_mark = "Comma"
    assert engine.format_result(12.5) == "12,50"


def test_exact_rectangular_complex_result(engine):
    result = engine.evaluate("1+2i")
    assert sp.simplify(result - (1 + 2 * sp.I)) == 0
    assert engine.format_result(result) == "1+2i"
    assert engine.format_result(-sp.I) == "-i"


def test_complex_mode_rejects_nonfinite_before_ans_mutation(engine):
    engine.ans = sp.Integer(7)
    with pytest.raises(CalculatorError):
        engine.complex_eval("1/0")
    assert engine.ans == 7


def test_symbolic_complex_result_with_unknown_sign_has_stable_exact_format(engine):
    result = engine.symbolic_integral("i*x")
    assert engine.format_result(result) == "i*x^2/2"


def test_polar_input_and_output(engine):
    result = engine.parse("2∠pi/2")
    assert sp.simplify(result - 2 * sp.I) == 0

    engine.settings.angle_unit = "DEG"
    engine.settings.complex_format = "r∠θ"
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 2
    assert engine.format_result(complex(0, 2), approximate=True) == "2.00∠90.00"


def test_rectangular_numeric_complex_respects_digits(engine):
    engine.settings.number_format = "Fix"
    engine.settings.number_digits = 2
    assert engine.format_result(complex(1.25, -2.5), approximate=True) == "1.25-2.50i"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(complex(0, 2.5), "2.5i"), (complex(0, -2.5), "-2.5i")],
)
def test_purely_imaginary_numeric_results_do_not_show_a_spurious_zero_real_part(
    engine, value, expected
):
    engine.settings.number_format = "Norm"
    assert engine.format_result(value, approximate=True) == expected
