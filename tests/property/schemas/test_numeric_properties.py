import json
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.numeric import Money, Probability, Quantity

pytestmark = pytest.mark.property

_FINITE_DECIMALS = st.decimals(
    allow_infinity=False,
    allow_nan=False,
    places=8,
    min_value=Decimal("-1000000"),
    max_value=Decimal("1000000"),
)


@given(value=st.decimals(min_value=Decimal("0"), max_value=Decimal("1"), places=8))
def test_probability_accepts_values_in_closed_unit_interval(value: Decimal) -> None:
    probability = Probability(value=value)

    assert Decimal("0") <= probability.value <= Decimal("1")


@given(value=st.decimals(min_value=Decimal("0"), max_value=Decimal("1000000"), places=8))
def test_quantity_is_never_negative_after_validation(value: Decimal) -> None:
    quantity = Quantity(value=value)

    assert quantity.value >= Decimal("0")


@given(value=_FINITE_DECIMALS)
def test_money_decimal_string_round_trips_exactly(value: Decimal) -> None:
    money = Money.model_validate_json(
        json.dumps(
            {
                "amount": str(value),
                "currency": "USD",
            }
        )
    )

    assert money.amount == value
    assert json.loads(money.model_dump_json())["amount"] == str(value)
