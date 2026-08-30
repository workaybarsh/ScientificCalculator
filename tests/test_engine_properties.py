import re

import pytest

hypothesis=pytest.importorskip("hypothesis")
import sympy as sp
from hypothesis import given, settings
from hypothesis import strategies as st

from scientific_calculator.calculator_engine import CalculatorError, ScientificCalculatorEngine
from scientific_calculator.errors import translate_error_message


@settings(max_examples=60, deadline=None)
@given(st.integers(min_value=-100_000, max_value=100_000))
def test_postfix_percent_property_preserves_its_operand_boundary(value):
    engine=ScientificCalculatorEngine(cas_isolated=False)
    assert float(engine.evaluate(f"1/{value if value else 1}%")) == pytest.approx(
        100 / (value if value else 1)
    )


@settings(max_examples=50, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.integers(min_value=-1_000, max_value=1_000),
            st.integers(min_value=0, max_value=100),
        ),
        min_size=1,
        max_size=12,
    ).filter(lambda pairs: sum(weight for _value, weight in pairs) > 0),
)
def test_weighted_statistics_matches_the_expanded_mean(pairs):
    values, weights=zip(*pairs, strict=True)
    engine=ScientificCalculatorEngine()
    result=engine.one_var_stats(values, weights)
    expected=sum(value * weight for value, weight in zip(values, weights, strict=True)) / sum(weights)
    assert result["x̄"] == pytest.approx(expected)


# Characters a user can actually produce on the calculator keypad, plus the
# function names the parser must recognise or reject by name.
_EXPRESSION_ALPHABET = "0123456789+-*/^().,!%xyzeabsincotlgrqPCn √π"
_ERROR_CATEGORY = re.compile(r"^[A-Za-z][A-Za-z ]*ERROR")


def _parse_outcome(text: str) -> CalculatorError | None:
    """Parse *text*, returning the domain error it raised, or None on success."""
    engine = ScientificCalculatorEngine(cas_isolated=False)
    try:
        engine.parse(text)
    except CalculatorError as exc:
        return exc
    return None


@settings(max_examples=250, deadline=None)
@given(st.text(alphabet=_EXPRESSION_ALPHABET, max_size=24))
def test_parsing_arbitrary_keypad_text_raises_only_domain_errors(text: str) -> None:
    """The parser is a security boundary: nothing but CalculatorError escapes.

    A bare Python or SymPy exception reaching a caller is both a crash and a
    disclosure risk, because the app renders a caught error straight onto the
    LCD.
    """
    _parse_outcome(text)


@settings(max_examples=150, deadline=None)
@given(st.text(max_size=20))
def test_parsing_arbitrary_unicode_raises_only_domain_errors(text: str) -> None:
    """Text can also arrive by paste, so it is not limited to the keypad."""
    _parse_outcome(text)


@settings(max_examples=200, deadline=None)
@given(st.text(alphabet=_EXPRESSION_ALPHABET, max_size=24))
def test_a_rejected_expression_reports_a_recognised_error_category(text: str) -> None:
    """Every refusal must be classifiable, in Turkish and once translated."""
    error = _parse_outcome(text)
    if error is None:
        return

    assert _ERROR_CATEGORY.match(str(error)), str(error)
    assert _ERROR_CATEGORY.match(translate_error_message(error)), translate_error_message(error)


@settings(max_examples=100, deadline=None)
@given(
    st.integers(min_value=-9_999, max_value=9_999),
    st.integers(min_value=-9_999, max_value=9_999),
    st.integers(min_value=-99, max_value=99),
    st.sampled_from("+-*"),
    st.sampled_from("+-*"),
)
def test_integer_arithmetic_agrees_with_exact_python_evaluation(
    left: int, middle: int, right: int, first: str, second: str
) -> None:
    """Parsing must not change the value of ordinary integer arithmetic."""
    expression = f"({left}){first}({middle}){second}({right})"
    expected = eval(expression)  # noqa: S307 - operands and operators are generated here

    engine = ScientificCalculatorEngine(cas_isolated=False)

    assert sp.Integer(expected) == sp.nsimplify(engine.parse(expression))


# Syntactically valid expressions reach the restricted evaluator instead of
# being turned away by the lexical guards, which is where the allowlist,
# resource preflights, and exact-result budgets actually live.
_ATOMS = st.one_of(
    st.integers(min_value=-999, max_value=999).map(str),
    st.floats(min_value=-999, max_value=999, allow_nan=False, allow_infinity=False).map(
        lambda value: f"{value:.4g}"
    ),
    st.sampled_from(("x", "y", "z", "e", "π", "2")),
)
_CALLS = ("sin", "cos", "tan", "sqrt", "log", "ln", "abs")


def _well_formed_expressions() -> st.SearchStrategy[str]:
    return st.recursive(
        _ATOMS,
        lambda inner: st.one_of(
            st.builds(lambda a, op, b: f"({a}{op}{b})", inner, st.sampled_from("+-*/^"), inner),
            st.builds(lambda name, a: f"{name}({a})", st.sampled_from(_CALLS), inner),
            st.builds(lambda a: f"(-{a})", inner),
            st.builds(lambda a: f"({a})!", st.integers(min_value=0, max_value=12).map(str)),
            st.builds(lambda a: f"({a})%", inner),
        ),
        max_leaves=12,
    )


@settings(max_examples=300, deadline=None)
@given(_well_formed_expressions())
def test_well_formed_expressions_reach_the_evaluator_without_escaping(expression: str) -> None:
    """The restricted evaluator must contain every operand it is handed.

    These inputs are syntactically valid, so they pass the lexical guards and
    exercise the call allowlist, the exponent/factorial preflights, and the
    exact-result budget. Only a CalculatorError may leave.
    """
    error = _parse_outcome(expression)
    if error is not None:
        assert _ERROR_CATEGORY.match(str(error)), str(error)
