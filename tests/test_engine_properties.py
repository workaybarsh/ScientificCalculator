import pytest

hypothesis=pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st

from scientific_calculator.calculator_engine import ScientificCalculatorEngine


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
