import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.schemas.numeric import Money, Price, Probability, Quantity

pytestmark = pytest.mark.unit


def test_price_accepts_decimal_string_and_serializes_decimal_as_string() -> None:
    price = Price(value="0.4200", currency="USD")

    assert price.value == Decimal("0.4200")
    assert json.loads(price.model_dump_json()) == {
        "currency": "USD",
        "value": "0.4200",
    }


def test_price_rejects_float_input() -> None:
    with pytest.raises(TypeError, match="float input"):
        Price(value=0.42)


def test_price_rejects_negative_value() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Price(value=Decimal("-0.01"))


def test_probability_accepts_closed_unit_interval_bounds() -> None:
    assert Probability(value=Decimal("0")).value == Decimal("0")
    assert Probability(value=Decimal("1")).value == Decimal("1")


def test_probability_rejects_value_above_one() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1"):
        Probability(value=Decimal("1.0001"))


def test_probability_rejects_value_below_zero() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Probability(value=Decimal("-0.0001"))


def test_quantity_rejects_negative_value() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Quantity(value=Decimal("-1"))


def test_money_accepts_signed_amount_and_valid_currency() -> None:
    money = Money(amount="-12.34", currency="USD")

    assert money.amount == Decimal("-12.34")
    assert money.currency == "USD"


def test_money_rejects_invalid_currency() -> None:
    with pytest.raises(ValidationError, match="three-letter uppercase"):
        Money(amount=Decimal("1"), currency="usd")


def test_decimal_values_reject_bool_input() -> None:
    with pytest.raises(TypeError, match="bool input"):
        Quantity(value=True)


def test_decimal_values_reject_non_finite_input() -> None:
    with pytest.raises(ValueError, match="finite"):
        Money(amount=Decimal("NaN"), currency="USD")
