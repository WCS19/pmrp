"""Property tests for fill accounting journals."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.portfolio import apply_fill_to_position, build_fill_journal_entry
from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.orders import Fill

pytestmark = pytest.mark.property

OCCURRED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 9, 25, 14, 0, 1, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 25, 14, 0, 2, tzinfo=UTC)

_QUANTITIES = st.integers(min_value=1, max_value=1_000).map(Decimal)
_MONEY_TICKS = st.integers(min_value=0, max_value=10_000).map(
    lambda ticks: Decimal(ticks) / Decimal("10000")
)


@given(
    side=st.sampled_from((Side.BUY, Side.SELL)),
    quantity=_QUANTITIES,
    price=_MONEY_TICKS,
    fee_amount=_MONEY_TICKS,
    rebate_amount=_MONEY_TICKS,
)
def test_fill_journal_lines_balance_for_generated_first_fill(
    side: Side,
    quantity: Decimal,
    price: Decimal,
    fee_amount: Decimal,
    rebate_amount: Decimal,
) -> None:
    fill = _fill(
        side=side,
        quantity=quantity,
        price=price,
        fee=Money(amount=fee_amount, currency="USD"),
        rebate=Money(amount=rebate_amount, currency="USD"),
    )
    projection = apply_fill_to_position(None, fill, currency="USD")

    journal = build_fill_journal_entry(
        fill=fill,
        projection=projection,
        source_event_id=EventId("evt_property_fill_journal"),
        created_at=CREATED_AT,
    )

    assert sum((line.amount for line in journal.lines), Decimal("0")) == Decimal("0")
    assert journal.reference_id == fill.fill_id
    assert journal.occurred_at == fill.exchange_occurred_at


def _fill(
    *,
    side: Side,
    price: Decimal,
    quantity: Decimal,
    fee: Money,
    rebate: Money,
) -> Fill:
    return Fill(
        fill_id="fill_property_journal_001",
        exchange_fill_id="ex-fill-property-journal-001",
        order_id="ord_property_journal",
        exchange_order_id="exchange-order-property-journal",
        client_order_id="client-order-property-journal",
        exchange="kalshi",
        account_id="acct_property_journal",
        market_id="mkt_property_journal",
        contract_id="ctr_property_journal",
        outcome_id="out_yes",
        side=side,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.UNKNOWN,
        fee=fee,
        rebate=rebate,
        exchange_occurred_at=OCCURRED_AT,
        received_at=RECEIVED_AT,
        trade_id=None,
    )
