"""Property tests for simulation rejection models."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.enums import MarketStatus
from pmrp.simulation import BoundedRejectionModel, RejectionReason

pytestmark = pytest.mark.property

_PRICE = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_QUANTITY = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_BALANCE = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("100000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(price=_PRICE, quantity=_QUANTITY, available_balance=_BALANCE)
def test_bounded_rejection_model_accepts_generated_valid_inputs(
    price: Decimal,
    quantity: Decimal,
    available_balance: Decimal,
) -> None:
    model = BoundedRejectionModel()

    decision = model.evaluate(
        market_status=MarketStatus.OPEN,
        price=price,
        quantity=quantity,
        required_balance=available_balance,
        available_balance=available_balance,
    )

    assert decision.accepted
    assert decision.reason_code is RejectionReason.ACCEPTED


@given(price=_PRICE, quantity=_QUANTITY, required_balance=_BALANCE)
def test_bounded_rejection_model_is_deterministic(
    price: Decimal,
    quantity: Decimal,
    required_balance: Decimal,
) -> None:
    model = BoundedRejectionModel()

    first = model.evaluate(
        market_status=MarketStatus.OPEN,
        price=price,
        quantity=quantity,
        required_balance=required_balance,
        available_balance=required_balance - Decimal("0.0001")
        if required_balance > Decimal("0")
        else required_balance,
    )
    second = model.evaluate(
        market_status=MarketStatus.OPEN,
        price=price,
        quantity=quantity,
        required_balance=required_balance,
        available_balance=required_balance - Decimal("0.0001")
        if required_balance > Decimal("0")
        else required_balance,
    )

    assert first == second


@given(price=_PRICE, quantity=_QUANTITY)
def test_bounded_rejection_model_rejects_generated_closed_markets(
    price: Decimal,
    quantity: Decimal,
) -> None:
    decision = BoundedRejectionModel().evaluate(
        market_status=MarketStatus.CLOSED,
        price=price,
        quantity=quantity,
    )

    assert decision.rejected
    assert decision.reason_code is RejectionReason.MARKET_CLOSED
