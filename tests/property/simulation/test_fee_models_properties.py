"""Property tests for simulation fee models."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.enums import LiquidityRole
from pmrp.simulation import FeeRule, FeeTableModel

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
_BPS = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(price=_PRICE, quantity=_QUANTITY, fee_rate_bps=_BPS, rebate_rate_bps=_BPS)
def test_fee_table_model_preserves_fee_invariant(
    price: Decimal,
    quantity: Decimal,
    fee_rate_bps: Decimal,
    rebate_rate_bps: Decimal,
) -> None:
    model = FeeTableModel.from_rules(
        FeeRule(
            exchange="kalshi",
            liquidity_role=LiquidityRole.TAKER,
            fee_rate_bps=fee_rate_bps,
            rebate_rate_bps=rebate_rate_bps,
        )
    )

    estimate = model.estimate(
        exchange="kalshi",
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.TAKER,
    )

    assert estimate.notional == price * quantity
    assert estimate.fee_amount >= Decimal("0")
    assert estimate.rebate_amount >= Decimal("0")
    assert estimate.net_fee_amount == estimate.fee_amount - estimate.rebate_amount


@given(price=_PRICE, quantity=_QUANTITY)
def test_zero_fee_rule_is_deterministic_and_zero(price: Decimal, quantity: Decimal) -> None:
    model = FeeTableModel.from_rules(
        FeeRule.zero(exchange="kalshi", liquidity_role=LiquidityRole.TAKER)
    )

    first = model.estimate(
        exchange="kalshi",
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.TAKER,
    )
    second = model.estimate(
        exchange="kalshi",
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.TAKER,
    )

    assert first == second
    assert first.fee_amount == Decimal("0")
    assert first.rebate_amount == Decimal("0")
    assert first.net_fee_amount == Decimal("0")
