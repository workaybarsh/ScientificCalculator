import math

import numpy as np
import pytest

from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine():
    return ScientificCalculatorEngine()


def test_base_n_tokens_expression_logic_and_formatting(engine):
    assert engine.parse_base_token("FF", 16) == 255
    assert engine.evaluate_base("hF + b1", current_base=10) == 16
    assert engine.evaluate_base("FF+1", current_base=16) == 256
    assert engine.base_operation(0b1100, 0b1010, "and") == 0b1000
    assert engine.base_operation(0b1100, 0b1010, "xor") == 0b0110
    assert engine.base_operation(0, 0, "xnor") == -1
    assert engine.format_base(-1, 16) == "FFFFFFFF"


def test_base_n_explicit_prefixes_are_not_reinterpreted_in_current_base(engine):
    assert engine.evaluate_base("d10+h10+b10+o10", current_base=16) == 36
    assert engine.evaluate_base("h10", current_base=2) == 16
    assert engine.evaluate_base("10", current_base=16) == 16


def test_base_n_hex_words_are_not_mistaken_for_invalid_explicit_prefixes(engine):
    assert engine.evaluate_base("BEEF", current_base=16) == 0xBEEF
    assert engine.evaluate_base("DEAD", current_base=16) == 0xDEAD
    assert engine.evaluate_base("D00D", current_base=16) == 0xD00D
    assert engine.evaluate_base("b102", current_base=16) == 0xB102
    assert engine.evaluate_base("d10", current_base=16) == 10


@pytest.mark.parametrize(
    ("source", "base"),
    [("b102", 10), ("b102", 2), ("o89", 10), ("d1A", 8), ("hFG", 10)],
)
def test_base_n_rejects_malformed_prefixes_outside_hex(engine, source, base):
    with pytest.raises(CalculatorError):
        engine.evaluate_base(source, current_base=base)


def test_base_n_internal_prefix_handling_has_no_user_collidable_marker(engine):
    with pytest.raises(CalculatorError):
        engine.evaluate_base("QXPREFIX0XQ+h1", current_base=10)


def test_base_n_source_length_is_bounded_before_token_conversion(engine):
    assert engine.evaluate_base("1" * 2048, current_base=2) == -1
    with pytest.raises(CalculatorError, match="çok uzun"):
        engine.evaluate_base("1" * 2049, current_base=2)


@pytest.mark.parametrize("source", ["1.9", "True", "False"])
def test_base_n_rejects_python_float_and_boolean_literals(engine, source):
    with pytest.raises(CalculatorError):
        engine.evaluate_base(source, current_base=10)
    assert engine.evaluate_base("10/2", current_base=10) == 5


def test_base_n_xnor_is_true_32_bit_complement_xor(engine):
    assert engine.evaluate_base("b1100 xnor b1010", current_base=10) == -7
    assert engine.evaluate_base("d0 xnor d0", current_base=16) == -1
    assert engine.format_base(engine.evaluate_base("hF xnor hA"), 16) == "FFFFFFFA"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("10/2", 5),
        ("-10/3", -3),
        ("10/-3", -3),
        ("-10/-3", 3),
        ("9007199254740993/1", 1),
    ],
)
def test_base_n_division_truncates_exact_integers_toward_zero(engine, source, expected):
    assert engine.evaluate_base(source, current_base=10) == expected


@pytest.mark.parametrize("value", ["12.9", -12, 0, 10**10])
def test_prime_factorization_rejects_non_positive_non_integer_or_large_input(engine, value):
    with pytest.raises(CalculatorError, match="FACT requires a positive integer"):
        engine.prime_factorization(value)


def test_prime_factorization_accepts_an_exact_positive_integer(engine):
    assert engine.prime_factorization("12") == {2: 2, 3: 1}


def test_random_int_validates_integer_bounds_and_order(engine):
    assert engine.random_int(10, 10) == 10
    assert 1 <= engine.random_int(1, 10) <= 10
    with pytest.raises(CalculatorError, match="lower bound exceeds upper bound"):
        engine.random_int(10, 5)
    with pytest.raises(CalculatorError, match="finite integers"):
        engine.random_int("1.5", 2)


def test_store_uses_the_restricted_expression_parser_for_strings(engine):
    assert engine.store("A", "2+3") == 5
    with pytest.raises(CalculatorError):
        engine.store("A", "__import__('os')")


@pytest.mark.parametrize("base", [0, 3, 12, 36])
def test_base_n_rejects_unsupported_current_base(engine, base):
    with pytest.raises(CalculatorError, match="Geçersiz taban"):
        engine.evaluate_base("10", current_base=base)
    with pytest.raises(CalculatorError, match="Geçersiz taban"):
        engine.parse_base_token("10", base)
    with pytest.raises(CalculatorError, match="Geçersiz taban"):
        engine.format_base(10, base)


def test_matrix_operations(engine):
    engine.define_matrix("MatA", [[1, 2], [3, 4]])
    engine.define_matrix("MatB", [[2, 0], [1, 2]])
    np.testing.assert_allclose(engine.matrix_op("*", "MatA", "MatB"), [[4, 4], [10, 8]])
    assert engine.matrix_op("det", "MatA") == pytest.approx(-2)
    np.testing.assert_allclose(
        engine.matrix_op("inv", "MatA"), [[-2, 1], [1.5, -0.5]]
    )
    np.testing.assert_allclose(engine.identity(3), np.eye(3))


def test_matrix_dimension_errors(engine):
    with pytest.raises(CalculatorError, match="Dimension"):
        engine.define_matrix("MatA", np.ones((5, 5)))
    with pytest.raises(CalculatorError, match="Dimension"):
        engine.matrix_op("det", "MatA")


@pytest.mark.parametrize("name", ["MatE", "A", "__class__"])
def test_matrix_definition_rejects_unknown_targets(engine, name):
    with pytest.raises(CalculatorError):
        engine.define_matrix(name, [[1]])


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_matrix_definition_rejects_nonfinite_data(engine, value):
    with pytest.raises(CalculatorError):
        engine.define_matrix("MatA", [[value]])


def test_matrix_binary_operations_validate_rhs_and_dimensions(engine):
    engine.define_matrix("MatA", [[1, 2], [3, 4]])
    with pytest.raises(CalculatorError):
        engine.matrix_op("+", "MatA", "MatB")
    engine.define_matrix("MatB", [[1, 2, 3]])
    with pytest.raises(CalculatorError):
        engine.matrix_op("+", "MatA", "MatB")
    with pytest.raises(CalculatorError):
        engine.matrix_op("*", "MatA", "MatB")


def test_vector_operations_and_angle(engine):
    engine.define_vector("VctA", [1, 0, 0])
    engine.define_vector("VctB", [0, 1, 0])
    assert engine.vector_op("dot", "VctA", "VctB") == pytest.approx(0)
    np.testing.assert_allclose(engine.vector_op("cross", "VctA", "VctB"), [0, 0, 1])
    assert engine.vector_op("abs", [3, 4]) == pytest.approx(5)
    engine.settings.angle_unit = "DEG"
    assert engine.vector_op("angle", "VctA", "VctB") == pytest.approx(90)


@pytest.mark.parametrize("name", ["VctE", "A", "__class__"])
def test_vector_definition_rejects_unknown_targets(engine, name):
    with pytest.raises(CalculatorError):
        engine.define_vector(name, [1, 2])


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_vector_definition_rejects_nonfinite_data(engine, value):
    with pytest.raises(CalculatorError):
        engine.define_vector("VctA", [value, 1])


def test_vector_binary_operations_validate_rhs_and_dimensions(engine):
    engine.define_vector("VctA", [1, 2])
    with pytest.raises(CalculatorError):
        engine.vector_op("dot", "VctA", "VctB")
    engine.define_vector("VctB", [1, 2, 3])
    with pytest.raises(CalculatorError):
        engine.vector_op("+", "VctA", "VctB")


@pytest.mark.parametrize(
    ("left", "right"),
    [([0, 0], [1, 0]), ([1, 0], [0, 0]), ([float("nan"), 0], [1, 0])],
)
def test_vector_angle_rejects_zero_or_nonfinite_norm(engine, left, right):
    with pytest.raises(CalculatorError, match="açısı tanımsız"):
        engine.vector_op("angle", left, right)


def test_one_variable_statistics_with_and_without_frequency(engine):
    result = engine.one_var_stats([1, 2, 3, 4])
    assert result["n"] == 4
    assert result["Σx"] == pytest.approx(10)
    assert result["x̄"] == pytest.approx(2.5)
    assert result["σx"] == pytest.approx(math.sqrt(1.25))
    assert result["Q1"] == pytest.approx(1.5)
    weighted = engine.one_var_stats([1, 3], freq=[2, 1])
    assert weighted["n"] == 3
    assert weighted["x̄"] == pytest.approx(5 / 3)


@pytest.mark.parametrize(
    "freq",
    [
        [1.5, 1],
        [-1, 1],
        [float("nan"), 1],
        [float("inf"), 1],
        [0, 0],
    ],
)
def test_one_variable_statistics_rejects_invalid_frequencies(engine, freq):
    with pytest.raises(CalculatorError):
        engine.one_var_stats([1, 2], freq=freq)


@pytest.mark.parametrize("values", [[1, float("nan")], [1, float("inf")]])
def test_one_variable_statistics_rejects_nonfinite_values(engine, values):
    with pytest.raises(CalculatorError):
        engine.one_var_stats(values)


def test_one_variable_statistics_handles_large_frequency_without_expansion(engine):
    result = engine.one_var_stats([1, 2], freq=[1_000_001, 0])
    assert result["n"] == 1_000_001
    assert result["x̄"] == pytest.approx(1)


def test_one_variable_statistics_rejects_nonfinite_outputs_from_overflow(engine):
    with pytest.raises(CalculatorError, match="sonlu"):
        engine.one_var_stats([1e308, 1e308])


def test_one_variable_statistics_keeps_single_sample_nan_policy(engine):
    result = engine.one_var_stats([2])
    assert math.isnan(result["sx²"])
    assert math.isnan(result["sx"])


def test_linear_and_quadratic_regressions(engine):
    linear = engine.regression([0, 1, 2], [1, 3, 5], "linear")
    assert linear["a"] == pytest.approx(1)
    assert linear["b"] == pytest.approx(2)
    assert linear["r"] == pytest.approx(1)
    assert linear["predict"](4) == pytest.approx(9)

    quadratic = engine.regression([-1, 0, 1, 2], [2, 1, 2, 5], "quadratic")
    assert quadratic["a"] == pytest.approx(1)
    assert quadratic["b"] == pytest.approx(0)
    assert quadratic["c"] == pytest.approx(1)


def test_transformed_regression_modes_preserve_valid_fits(engine):
    log_fit = engine.regression([1, math.e, math.e**2], [1, 3, 5], "log")
    assert log_fit["a"] == pytest.approx(1)
    assert log_fit["b"] == pytest.approx(2)

    exp_e_fit = engine.regression(
        [0, 1, 2], [2, 2 * math.exp(0.5), 2 * math.exp(1)], "exp_e"
    )
    assert exp_e_fit["a"] == pytest.approx(2)
    assert exp_e_fit["b"] == pytest.approx(0.5)

    exp_b_fit = engine.regression([0, 1, 2], [3, 6, 12], "exp_b")
    assert exp_b_fit["a"] == pytest.approx(3)
    assert exp_b_fit["b"] == pytest.approx(2)

    power_fit = engine.regression([1, 2, 4], [4, 4 * 2**1.5, 32], "power")
    assert power_fit["a"] == pytest.approx(4)
    assert power_fit["b"] == pytest.approx(1.5)

    inverse_fit = engine.regression([1, 2, 4], [11, 8, 6.5], "inverse")
    assert inverse_fit["a"] == pytest.approx(5)
    assert inverse_fit["b"] == pytest.approx(6)


@pytest.mark.parametrize(
    ("x", "y", "kind"),
    [
        ([0, float("nan")], [1, 2], "linear"),
        ([0, 1], [1, float("inf")], "linear"),
        ([[0, 1]], [[1, 2]], "linear"),
        ([0, 1], [1], "linear"),
        ([1, 1], [2, 3], "linear"),
        ([0, 1], [0, 1], "quadratic"),
        ([1, 1, 1], [1, 2, 3], "log"),
        ([1, 1, 1], [1, 2, 3], "inverse"),
    ],
)
def test_regression_rejects_nonfinite_malformed_or_rank_deficient_data(
    engine, x, y, kind
):
    with pytest.raises(CalculatorError):
        engine.regression(x, y, kind)


@pytest.mark.parametrize("kind", ["exp_e", "exp_b"])
def test_exponential_regression_requires_two_unique_predictors(engine, kind):
    with pytest.raises(CalculatorError):
        engine.regression([1, 1], [2, 3], kind)


def test_linear_regression_reports_undefined_constant_response_correlation(engine):
    result = engine.regression([0, 1, 2], [5, 5, 5], "linear")
    assert result["a"] == pytest.approx(5)
    assert result["b"] == pytest.approx(0, abs=1e-12)
    assert result["r"] is None


def test_matrix_square_only_operations_are_not_called_singular(engine):
    for operation in ("det", "inv"):
        with pytest.raises(CalculatorError, match="matrix must be square"):
            engine.matrix_op(operation, [[1, 2, 3], [4, 5, 6]])
    with pytest.raises(CalculatorError, match="tekil"):
        engine.matrix_op("inv", [[1, 2], [2, 4]])


def test_base_division_by_zero_is_a_math_error(engine):
    with pytest.raises(CalculatorError, match="Math ERROR: division by zero"):
        engine.evaluate_base("1/0", 10)


def test_probability_distributions(engine):
    assert engine.distribution("Normal PD", x=0, mu=0, sigma=1) == pytest.approx(
        1 / math.sqrt(2 * math.pi)
    )
    assert engine.distribution("Normal CD", lower=-1, upper=1, mu=0, sigma=1) == pytest.approx(
        0.682689492, rel=1e-7
    )
    assert engine.distribution("Inverse Normal", area=0.5, mu=5, sigma=2) == pytest.approx(5)
    assert engine.distribution("Binomial PD", x=2, N=4, p=0.5) == pytest.approx(0.375)
    assert engine.distribution("Poisson CD", x=2, lam=1) == pytest.approx(0.919698603, rel=1e-7)


@pytest.mark.parametrize(
    ("kind", "values"),
    [
        ("Normal PD", {"x": 0, "mu": 0, "sigma": 0}),
        ("Normal PD", {"x": float("nan"), "mu": 0, "sigma": 1}),
        ("Normal CD", {"lower": 2, "upper": 1, "mu": 0, "sigma": 1}),
        ("Normal CD", {"lower": -1, "upper": float("inf"), "mu": 0, "sigma": 1}),
        ("Inverse Normal", {"area": 0, "mu": 0, "sigma": 1}),
        ("Inverse Normal", {"area": 1, "mu": 0, "sigma": 1}),
        ("Binomial PD", {"x": 1.5, "N": 4, "p": 0.5}),
        ("Binomial CD", {"x": 2, "N": 4.5, "p": 0.5}),
        ("Binomial PD", {"x": 2, "N": 4, "p": -0.1}),
        ("Binomial PD", {"x": 2, "N": 4, "p": 1.1}),
        ("Poisson PD", {"x": 1.5, "lam": 2}),
        ("Poisson CD", {"x": 2, "lam": -1}),
        ("Poisson CD", {"x": 2, "lam": float("inf")}),
    ],
)
def test_distribution_domain_and_finite_input_validation(engine, kind, values):
    with pytest.raises(CalculatorError):
        engine.distribution(kind, **values)


def test_distribution_boundary_values_remain_valid(engine):
    assert engine.distribution("Binomial PD", x=0, N=0, p=0) == pytest.approx(1)
    assert engine.distribution("Binomial CD", x=1, N=1, p=1) == pytest.approx(1)
    assert engine.distribution("Poisson PD", x=0, lam=0) == pytest.approx(1)


def test_simultaneous_and_polynomial_equations(engine):
    np.testing.assert_allclose(engine.simultaneous([[2, 1], [1, -1]], [5, 1]), [2, 1])
    roots = sorted((complex(root) for root in engine.polynomial_roots([1, -3, 2])), key=lambda z: z.real)
    assert roots[0] == pytest.approx(1 + 0j)
    assert roots[1] == pytest.approx(2 + 0j)


@pytest.mark.parametrize(
    ("coefficients", "constants"),
    [
        ([[float("nan"), 1], [1, 1]], [1, 2]),
        ([[1, 1], [1, 1]], [float("inf"), 2]),
    ],
)
def test_simultaneous_rejects_nonfinite_inputs(engine, coefficients, constants):
    with pytest.raises(CalculatorError, match="sonlu"):
        engine.simultaneous(coefficients, constants)


def test_simultaneous_rejects_nonfinite_solution(engine):
    # Finite inputs can still overflow while NumPy solves the system.
    with pytest.raises(CalculatorError, match="sonucu sonlu değil"):
        engine.simultaneous([[1e-308, 0], [0, 1]], [1e308, 1])


@pytest.mark.parametrize(
    "coefficients",
    ([0, 2, 1], [float("nan"), 2, 1], [float("inf"), 2, 1]),
)
def test_polynomial_rejects_degenerate_or_nonfinite_coefficients(engine, coefficients):
    with pytest.raises(CalculatorError):
        engine.polynomial_roots(coefficients)


def test_inequality_solutions(engine):
    solution = engine.inequality([1, -2], ">")
    symbol = next(iter(solution.free_symbols))
    assert bool(solution.subs(symbol, 3)) is True
    assert bool(solution.subs(symbol, 1)) is False


@pytest.mark.parametrize(
    "coefficients",
    ([1], [0, 1, -2], [float("nan"), 1, -2]),
)
def test_inequality_rejects_invalid_degree_or_coefficients(engine, coefficients):
    with pytest.raises(CalculatorError):
        engine.inequality(coefficients, ">")


def test_ratio_modes(engine):
    assert engine.ratio("A:B=X:D", A=2, B=3, D=12) == pytest.approx(8)
    assert engine.ratio("A:B=C:X", A=2, B=3, C=12) == pytest.approx(18)
    assert engine.ratio("A:B=X:D", A=0, B=2, D=3) == pytest.approx(0)
    assert engine.ratio("A:B=X:D", A=2, B=3, D=0) == pytest.approx(0)
    assert engine.ratio("A:B=C:X", A=2, B=0, C=3) == pytest.approx(0)
    with pytest.raises(CalculatorError):
        engine.ratio("A:B=X:D", A=2, B=0, D=12)
    with pytest.raises(CalculatorError):
        engine.ratio("A:B=C:X", A=0, B=3, C=12)
    with pytest.raises(CalculatorError, match="unsupported ratio form"):
        engine.ratio("banana", A=2, B=3, C=12)


@pytest.mark.parametrize(
    ("kind", "values"),
    [
        ("A:B=X:D", {"A": float("nan"), "B": 3, "D": 12}),
        ("A:B=X:D", {"A": 2, "B": float("inf"), "D": 12}),
        ("A:B=C:X", {"A": 2, "B": 3, "C": float("nan")}),
        ("A:B=C:X", {"A": complex(2, 1), "B": 3, "C": 12}),
    ],
)
def test_ratio_rejects_nonfinite_or_nonreal_inputs(engine, kind, values):
    with pytest.raises(CalculatorError, match="sonlu reel"):
        engine.ratio(kind, **values)


def test_ratio_rejects_nonfinite_result(engine):
    with pytest.raises(CalculatorError, match="sonucu sonlu değil"):
        engine.ratio("A:B=X:D", A=1e308, B=1, D=1e308)


@pytest.mark.parametrize("value", (-0.5, -0.001, -0.999999))
def test_dms_round_trip_preserves_subdegree_negative_sign(engine, value):
    degrees, minutes, seconds = engine.dms_from_decimal(value)
    assert math.copysign(1.0, degrees) == -1.0
    assert engine.decimal_from_dms(degrees, minutes, seconds) == pytest.approx(value)
