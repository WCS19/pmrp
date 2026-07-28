"""Financial and probability value objects."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from pydantic import Field, field_validator

from pmrp.schemas.base import CanonicalModel

_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")


def parse_decimal(value: object, *, field_name: str) -> Decimal:
    """Parse exact Decimal inputs while rejecting floats and non-finite values."""

    if isinstance(value, bool):
        msg = f"{field_name} does not accept bool input"
        raise TypeError(msg)
    if isinstance(value, float):
        msg = f"{field_name} does not accept float input"
        raise TypeError(msg)
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, str):
        if value == "" or value.strip() != value:
            msg = f"{field_name} must be a decimal string without surrounding whitespace"
            raise ValueError(msg)
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            msg = f"{field_name} must be a valid decimal string"
            raise ValueError(msg) from exc
    else:
        msg = f"{field_name} must be Decimal, int, or decimal string"
        raise TypeError(msg)

    if not decimal_value.is_finite():
        msg = f"{field_name} must be finite"
        raise ValueError(msg)
    return decimal_value


def validate_currency(value: str) -> str:
    if _CURRENCY_PATTERN.fullmatch(value) is None:
        msg = "currency must be a three-letter uppercase ISO 4217 code"
        raise ValueError(msg)
    return value


class Price(CanonicalModel):
    value: Decimal = Field(ge=Decimal("0"))
    currency: str = "USD"

    @field_validator("value", mode="before")
    @classmethod
    def parse_value(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="Price.value")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return validate_currency(value)


class Probability(CanonicalModel):
    value: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("value", mode="before")
    @classmethod
    def parse_value(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="Probability.value")


class Quantity(CanonicalModel):
    value: Decimal = Field(ge=Decimal("0"))

    @field_validator("value", mode="before")
    @classmethod
    def parse_value(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="Quantity.value")


class Money(CanonicalModel):
    amount: Decimal
    currency: str

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="Money.amount")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return validate_currency(value)
