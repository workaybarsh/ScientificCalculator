import numpy as np
import pytest
import sympy as sp

from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine


@pytest.fixture
def engine():
    return ScientificCalculatorEngine()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("2pi", 2 * sp.pi),
        ("2(3+4)", sp.Integer(14)),
        ("3!", sp.Integer(6)),
        ("2^3^2", sp.Integer(512)),
        ("sqrt(8)", 2 * sp.sqrt(2)),
        ("log(100,10)", sp.Integer(2)),
        ("nCr(10,3)", sp.Integer(120)),
        ("2∠pi/2", 2 * sp.I),
    ],
)
def test_whitelisted_calculator_syntax_remains_supported(engine, source, expected):
    assert sp.simplify(engine.parse(source) - expected) == 0


def test_single_letter_symbol_and_implicit_products_remain_supported(engine):
    x = sp.Symbol("x")
    result = engine.parse_symbolic("2x+(x+1)(x-1)", {"x": x})
    assert sp.expand(result) == x**2 + 2 * x - 1


def test_adjacent_whitelisted_single_letter_bindings_form_safe_products(engine):
    engine.memory.update(
        {"A": sp.Integer(2), "B": sp.Integer(5), "x": sp.Integer(3), "y": sp.Integer(4)}
    )
    assert engine.parse("xy") == 12
    assert engine.parse("AB") == 10
    assert engine.parse("Ax") == 6
    assert engine.parse("2xy") == 24

    u, v = sp.symbols("u v")
    assert engine.parse_symbolic("uv", {"u": u, "v": v}) == u * v


def test_adjacent_product_length_is_bounded_before_eager_multiplication(engine):
    engine.memory["A"] = sp.Integer(2) ** 10000
    with pytest.raises(CalculatorError, match="çok karmaşık"):
        engine.parse("A" * 65)


@pytest.mark.parametrize("source", ["xz", "G+GG", "os", "unknownname"])
def test_adjacent_product_compatibility_does_not_create_unknown_names(engine, source):
    with pytest.raises(CalculatorError):
        engine.parse(source)


@pytest.mark.parametrize(
    "source",
    [
        "__import__(os)",
        "open(1)",
        "eval(1)",
        "lambda x",
        "unknown(1)",
        "x.__class__",
        "[1,2]",
        "'text'",
    ],
)
def test_python_and_unknown_names_are_rejected(engine, source):
    with pytest.raises(CalculatorError):
        engine.parse(source)


@pytest.mark.parametrize(
    "source",
    [
        "1 .q",       # Numeric-receiver attribute access bypassed the old regex.
        "1 .n(5)",    # SymPy method invocation through a numeric receiver.
        "1,2",        # Tuple construction is not calculator syntax.
        "(1,2)",
        "...",        # Python Ellipsis is not a mathematical value.
        "sin",        # Bare callable objects must never escape the parser.
    ],
)
def test_only_arithmetic_ast_shapes_are_accepted(engine, source):
    with pytest.raises(CalculatorError):
        engine.parse(source)


def test_caller_locals_cannot_inject_callable_objects(engine):
    called = False

    def malicious():
        nonlocal called
        called = True
        return 1

    with pytest.raises(CalculatorError):
        engine.parse("x", {"x": malicious})
    assert called is False


def test_only_single_letter_math_values_are_accepted_as_extra_locals(engine):
    with pytest.raises(CalculatorError):
        engine.parse("theta", {"theta": sp.Integer(2)})
    with pytest.raises(CalculatorError):
        engine.parse("x", {"x": object()})
    assert engine.parse("x+1", {"x": sp.Integer(2)}) == 3


@pytest.mark.parametrize(
    "source", ["2**10001", "2**9**9", "10001!", "nCr(10001,5000)"]
)
def test_resource_amplification_is_rejected_before_sympy_evaluation(engine, source):
    with pytest.raises(CalculatorError):
        engine.parse(source)


@pytest.mark.parametrize(
    "source",
    [
        "2^sqrt(10^100)",
        "factorial(sqrt(10^100))",
        "nPr(sqrt(10^100),2)",
        "nCr(sqrt(10^100),2)",
    ],
)
def test_resource_limits_cannot_be_bypassed_with_numeric_wrappers(engine, source):
    with pytest.raises(CalculatorError):
        engine.parse(source)


@pytest.mark.parametrize("source", ["2^Ans", "factorial(Ans)", "nPr(Ans,2)", "nCr(Ans,2)"])
def test_resource_limits_cannot_be_bypassed_with_numeric_names(engine, source):
    engine.ans = sp.Integer(10001)
    with pytest.raises(CalculatorError):
        engine.parse(source)


@pytest.mark.parametrize(
    "value",
    [
        complex(10001, 0),
        complex(10001, 1),
        np.complex128(10001 + 0j),
        np.complex128(10001 + 1j),
    ],
)
@pytest.mark.parametrize("source", ["2^x", "factorial(x)"])
def test_resource_limits_cannot_be_bypassed_with_numeric_complex_locals(
    engine, source, value
):
    with pytest.raises(CalculatorError):
        engine.parse(source, {"x": value})


def test_genuinely_complex_numeric_exponent_remains_supported(engine):
    result = engine.parse("2^x", {"x": complex(0, 1)})
    assert complex(sp.N(result, 15)) == pytest.approx(complex(sp.N(2**sp.I, 15)))


def test_large_direct_complex_exponent_is_rejected_before_pow(engine):
    with pytest.raises(CalculatorError, match="Üs çok büyük"):
        engine.parse("2^(10^50+i)")


def test_bounded_operations_still_accept_ordinary_and_symbolic_operands(engine):
    assert engine.parse("2^sqrt(9)") == 8
    assert engine.parse("factorial(sqrt(9))") == 6
    assert engine.parse("nPr(sqrt(9),2)") == 6
    assert engine.parse("nCr(sqrt(9),2)") == 3

    x = sp.Symbol("x")
    result = engine.parse_symbolic(
        "2^x+factorial(x)+nPr(x,2)+nCr(x,2)", {"x": x}
    )
    assert result.has(x)


def test_complex_numeric_exponents_are_not_mistaken_for_resource_amplification(engine):
    result = engine.parse("2^((-1)^(1/2))")
    assert sp.simplify(result - 2**sp.I) == 0


def test_empty_overlong_and_non_math_input_are_rejected(engine):
    for source in ("", "2+@3", "1" * 2049):
        with pytest.raises(CalculatorError):
            engine.parse(source)
