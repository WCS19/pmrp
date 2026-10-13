"""Property tests for idempotent portfolio fill application."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.portfolio import apply_fill_once, apply_fills_once
from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.orders import Fill

pytestmark = pytest.mark.property

OCCURRED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 9, 25, 14, 0, 1, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 25, 14, 0, 2, tzinfo=UTC)

_QUANTITIES = st.integers(min_value=1, max_value=1_000).map(Decimal)
_PRICES = st.integers(min_value=0, max_value=10_000).map(
    lambda ticks: Decimal(ticks) / Decimal("10000")
)


@given(
    side=st.sampled_from((Side.BUY, Side.SELL)),
    quantity=_QUANTITIES,
    price=_PRICES,
)
def test_apply_fill_once_is_idempotent_for_duplicate_fill_ids(
    side: Side,
    quantity: Decimal,
    price: Decimal,
) -> None:
    fill = _fill(side=side, quantity=quantity, price=price)

    first = apply_fill_once(
        position=None,
        fill=fill,
        applied_fill_ids=frozenset(),
        currency="USD",
        source_event_id=EventId("evt_property_projection_first"),
        created_at=CREATED_AT,
    )
    duplicate = apply_fill_once(
        position=first.position,
        fill=fill,
        applied_fill_ids=first.applied_fill_ids,
        currency="USD",
        source_event_id=EventId("evt_property_projection_duplicate"),
        created_at=CREATED_AT,
    )

    assert first.applied is True
    assert duplicate.applied is False
    assert duplicate.duplicate_fill is True
    assert duplicate.position == first.position
    assert duplicate.journal_entry is None
    assert duplicate.applied_fill_ids == first.applied_fill_ids


@given(
    first_quantity=_QUANTITIES,
    first_price=_PRICES,
    second_quantity=_QUANTITIES,
    second_price=_PRICES,
)
def test_apply_fills_once_matches_sorted_chronological_application(
    first_quantity: Decimal,
    first_price: Decimal,
    second_quantity: Decimal,
    second_price: Decimal,
) -> None:
    first_fill = _fill(
        fill_id="fill_property_projection_first",
        exchange_fill_id="ex-fill-property-projection-first",
        side=Side.BUY,
        quantity=first_quantity,
        price=first_price,
        exchange_occurred_at=OCCURRED_AT,
        received_at=RECEIVED_AT,
    )
    second_fill = _fill(
        fill_id="fill_property_projection_second",
        exchange_fill_id="ex-fill-property-projection-second",
        side=Side.BUY,
        quantity=second_quantity,
        price=second_price,
        exchange_occurred_at=OCCURRED_AT.replace(second=1),
        received_at=RECEIVED_AT.replace(second=2),
    )

    batch = apply_fills_once(
        position=None,
        fills=(second_fill, first_fill),
        applied_fill_ids=frozenset(),
        currency="USD",
        source_event_ids={
            first_fill.fill_id: EventId("evt_property_projection_first"),
            second_fill.fill_id: EventId("evt_property_projection_second"),
        },
        created_at=CREATED_AT,
    )
    first = apply_fill_once(
        position=None,
        fill=first_fill,
        applied_fill_ids=frozenset(),
        currency="USD",
        source_event_id=EventId("evt_property_projection_first"),
        created_at=CREATED_AT,
    )
    second = apply_fill_once(
        position=first.position,
        fill=second_fill,
        applied_fill_ids=first.applied_fill_ids,
        currency="USD",
        source_event_id=EventId("evt_property_projection_second"),
        created_at=CREATED_AT,
    )

    assert batch.position == second.position
    assert batch.applied_fill_ids == second.applied_fill_ids
    assert [journal.reference_id for journal in batch.journal_entries] == [
        first_fill.fill_id,
        second_fill.fill_id,
    ]


def _fill(
    *,
    side: Side,
    quantity: Decimal,
    price: Decimal,
    fill_id: str = "fill_property_projection_001",
    exchange_fill_id: str = "ex-fill-property-projection-001",
    exchange_occurred_at: datetime = OCCURRED_AT,
    received_at: datetime = RECEIVED_AT,
) -> Fill:
    return Fill(
        fill_id=fill_id,
        exchange_fill_id=exchange_fill_id,
        order_id="ord_property_projection",
        exchange_order_id="exchange-order-property-projection",
        client_order_id="client-order-property-projection",
        exchange="kalshi",
        account_id="acct_property_projection",
        market_id="mkt_property_projection",
        contract_id="ctr_property_projection",
        outcome_id="out_yes",
        side=side,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.UNKNOWN,
        fee=None,
        rebate=None,
        exchange_occurred_at=exchange_occurred_at,
        received_at=received_at,
        trade_id=None,
    )
