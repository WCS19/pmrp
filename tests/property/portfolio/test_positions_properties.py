"""Property tests for portfolio position projection invariants."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.portfolio import apply_fill_to_position
from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.orders import Fill

pytestmark = pytest.mark.property

OCCURRED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 9, 25, 14, 0, 1, tzinfo=UTC)

_QUANTITY_INTEGERS = st.integers(min_value=1, max_value=1_000)
_PRICE_TICKS = st.integers(min_value=0, max_value=10_000).map(
    lambda ticks: Decimal(ticks) / Decimal("10000")
)


@given(
    first_quantity=_QUANTITY_INTEGERS,
    second_quantity=_QUANTITY_INTEGERS,
    first_price=_PRICE_TICKS,
    second_price=_PRICE_TICKS,
)
def test_same_direction_buys_preserve_weighted_average_cost(
    first_quantity: int,
    second_quantity: int,
    first_price: Decimal,
    second_price: Decimal,
) -> None:
    first = apply_fill_to_position(
        None,
        _fill(
            fill_id="fill_property_buy_001",
            exchange_fill_id="ex-fill-property-001",
            price=first_price,
            quantity=Decimal(first_quantity),
        ),
        currency="USD",
    )

    second = apply_fill_to_position(
        first.position,
        _fill(
            fill_id="fill_property_buy_002",
            exchange_fill_id="ex-fill-property-002",
            price=second_price,
            quantity=Decimal(second_quantity),
        ),
        currency="USD",
    )

    expected_average = (
        (Decimal(first_quantity) * first_price) + (Decimal(second_quantity) * second_price)
    ) / Decimal(first_quantity + second_quantity)

    assert second.position.quantity == Decimal(first_quantity + second_quantity)
    assert second.position.average_entry_price == expected_average
    assert second.realized_trading_pnl.amount == Decimal("0")


@given(
    open_quantity=_QUANTITY_INTEGERS,
    requested_close_quantity=_QUANTITY_INTEGERS,
    entry_price=_PRICE_TICKS,
    exit_price=_PRICE_TICKS,
)
def test_long_reductions_realize_average_cost_pnl(
    open_quantity: int,
    requested_close_quantity: int,
    entry_price: Decimal,
    exit_price: Decimal,
) -> None:
    close_quantity = min(open_quantity, requested_close_quantity)
    first = apply_fill_to_position(
        None,
        _fill(
            fill_id="fill_property_reduce_001",
            exchange_fill_id="ex-fill-property-001",
            price=entry_price,
            quantity=Decimal(open_quantity),
        ),
        currency="USD",
    )

    second = apply_fill_to_position(
        first.position,
        _fill(
            fill_id="fill_property_reduce_002",
            exchange_fill_id="ex-fill-property-002",
            side=Side.SELL,
            price=exit_price,
            quantity=Decimal(close_quantity),
        ),
        currency="USD",
    )

    expected_realized = Decimal(close_quantity) * (exit_price - entry_price)
    expected_quantity = Decimal(open_quantity - close_quantity)

    assert second.position.quantity == expected_quantity
    assert second.realized_trading_pnl.amount == expected_realized
    assert second.position.realized_pnl.amount == expected_realized
    if expected_quantity == Decimal("0"):
        assert second.position.average_entry_price is None
    else:
        assert second.position.average_entry_price == entry_price


def _fill(
    *,
    fill_id: str,
    exchange_fill_id: str,
    side: Side = Side.BUY,
    price: Decimal,
    quantity: Decimal,
) -> Fill:
    return Fill(
        fill_id=fill_id,
        exchange_fill_id=exchange_fill_id,
        order_id="ord_property_order",
        exchange_order_id="exchange-order-property",
        client_order_id="client-order-property",
        exchange="kalshi",
        account_id="acct_property_001",
        market_id="mkt_property_001",
        contract_id="ctr_property_001",
        outcome_id="out_yes",
        side=side,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.UNKNOWN,
        fee=None,
        rebate=None,
        exchange_occurred_at=OCCURRED_AT,
        received_at=RECEIVED_AT,
        trade_id=None,
    )
