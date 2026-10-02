"""Unit tests for portfolio projection workflows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import apply_fill_once
from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.identifiers import EventId, FillId
from pmrp.schemas.orders import Fill

pytestmark = pytest.mark.unit

OCCURRED_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 9, 25, 14, 0, 1, tzinfo=UTC)
CREATED_AT = datetime(2026, 9, 25, 14, 0, 2, tzinfo=UTC)
SOURCE_EVENT_ID = EventId("evt_projection_fill_001")


def test_apply_fill_once_projects_position_and_journal_for_new_fill() -> None:
    fill = _fill(price="0.40", quantity="10")

    result = apply_fill_once(
        position=None,
        fill=fill,
        applied_fill_ids=frozenset(),
        currency="USD",
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    assert result.applied is True
    assert result.duplicate_fill is False
    assert result.position is not None
    assert result.position.quantity == Decimal("10")
    assert result.position_projection is not None
    assert result.position_projection.trade_notional.amount == Decimal("4.00")
    assert result.journal_entry is not None
    assert result.journal_entry.reference_id == fill.fill_id
    assert result.journal_entry.source_event_id == SOURCE_EVENT_ID
    assert result.applied_fill_ids == frozenset({fill.fill_id})


def test_apply_fill_once_returns_noop_for_duplicate_fill_id() -> None:
    fill = _fill(price="0.40", quantity="10")
    first = apply_fill_once(
        position=None,
        fill=fill,
        applied_fill_ids=frozenset(),
        currency="USD",
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    duplicate = apply_fill_once(
        position=first.position,
        fill=fill,
        applied_fill_ids=first.applied_fill_ids,
        currency="USD",
        source_event_id=EventId("evt_projection_fill_duplicate"),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert duplicate.applied is False
    assert duplicate.duplicate_fill is True
    assert duplicate.position == first.position
    assert duplicate.position_projection is None
    assert duplicate.journal_entry is None
    assert duplicate.applied_fill_ids == first.applied_fill_ids


def test_apply_fill_once_accepts_existing_fill_id_sets_without_mutating_them() -> None:
    existing_fill_ids = {FillId("fill_existing_projection")}
    fill = _fill(fill_id="fill_projection_new")

    result = apply_fill_once(
        position=None,
        fill=fill,
        applied_fill_ids=existing_fill_ids,
        currency="USD",
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )

    assert existing_fill_ids == {FillId("fill_existing_projection")}
    assert result.applied_fill_ids == frozenset({FillId("fill_existing_projection"), fill.fill_id})


def test_apply_fill_once_chains_distinct_fills_in_order() -> None:
    first_fill = _fill(fill_id="fill_projection_first", price="0.40", quantity="10")
    first = apply_fill_once(
        position=None,
        fill=first_fill,
        applied_fill_ids=frozenset(),
        currency="USD",
        source_event_id=SOURCE_EVENT_ID,
        created_at=CREATED_AT,
    )
    second_fill = _fill(
        fill_id="fill_projection_second",
        exchange_fill_id="ex-fill-projection-second",
        side=Side.SELL,
        price="0.60",
        quantity="4",
        exchange_occurred_at=OCCURRED_AT + timedelta(seconds=1),
        received_at=RECEIVED_AT + timedelta(seconds=1),
    )

    second = apply_fill_once(
        position=first.position,
        fill=second_fill,
        applied_fill_ids=first.applied_fill_ids,
        currency="USD",
        source_event_id=EventId("evt_projection_fill_002"),
        created_at=CREATED_AT + timedelta(seconds=1),
    )

    assert second.applied is True
    assert second.position is not None
    assert second.position.quantity == Decimal("6")
    assert second.position.realized_pnl.amount == Decimal("0.80")
    assert second.applied_fill_ids == frozenset({first_fill.fill_id, second_fill.fill_id})


def _fill(
    *,
    fill_id: str = "fill_projection_001",
    exchange_fill_id: str = "ex-fill-projection-001",
    side: Side = Side.BUY,
    price: str = "0.40",
    quantity: str = "10",
    exchange_occurred_at: datetime = OCCURRED_AT,
    received_at: datetime = RECEIVED_AT,
) -> Fill:
    return Fill(
        fill_id=fill_id,
        exchange_fill_id=exchange_fill_id,
        order_id="ord_projection_order_001",
        exchange_order_id="exchange-order-projection-001",
        client_order_id="client-order-projection-001",
        exchange="kalshi",
        account_id="acct_projection_001",
        market_id="mkt_projection_001",
        contract_id="ctr_projection_001",
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
