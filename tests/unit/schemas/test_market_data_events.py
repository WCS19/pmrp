"""Canonical market data event schema tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.events import (
    MARKET_ORDER_BOOK_DELTA_EVENT_TYPE,
    MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,
    MARKET_TRADE_OBSERVED_EVENT_TYPE,
    OrderBookDeltaEvent,
    OrderBookSnapshotEvent,
    TradeObservedEvent,
)
from pmrp.schemas.market_data import OrderBookDeltaAction
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def test_order_book_snapshot_event_accepts_matching_envelope_and_snapshot() -> None:
    event = OrderBookSnapshotEvent.model_validate(
        {
            "envelope": _envelope_payload(event_type=MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE),
            "snapshot": _snapshot_payload(),
        }
    )

    assert event.envelope.event_type == MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE
    assert event.envelope.market_id == event.snapshot.market_id
    assert event.envelope.exchange == event.snapshot.exchange


def test_order_book_delta_event_accepts_matching_envelope_and_delta() -> None:
    event = OrderBookDeltaEvent.model_validate(
        {
            "envelope": _envelope_payload(event_type=MARKET_ORDER_BOOK_DELTA_EVENT_TYPE),
            "delta": _delta_payload(),
        }
    )

    assert event.envelope.event_type == MARKET_ORDER_BOOK_DELTA_EVENT_TYPE
    assert event.delta.changes[0].action is OrderBookDeltaAction.UPSERT


def test_trade_observed_event_accepts_matching_envelope_and_trade() -> None:
    event = TradeObservedEvent.model_validate(
        {
            "envelope": _envelope_payload(event_type=MARKET_TRADE_OBSERVED_EVENT_TYPE),
            "trade": _trade_payload(),
        }
    )

    assert event.envelope.event_type == MARKET_TRADE_OBSERVED_EVENT_TYPE
    assert event.trade.liquidity_role is LiquidityRole.TAKER


def test_market_data_events_reject_wrong_event_type_and_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="event envelope event_type must be"):
        OrderBookSnapshotEvent.model_validate(
            {
                "envelope": _envelope_payload(event_type=MARKET_ORDER_BOOK_DELTA_EVENT_TYPE),
                "snapshot": _snapshot_payload(),
            }
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OrderBookDeltaEvent.model_validate(
            {
                "envelope": _envelope_payload(event_type=MARKET_ORDER_BOOK_DELTA_EVENT_TYPE),
                "delta": _delta_payload(),
                "unexpected": True,
            }
        )


def test_market_data_events_require_matching_market_lineage() -> None:
    with pytest.raises(ValidationError, match="market_id is required"):
        OrderBookSnapshotEvent.model_validate(
            {
                "envelope": _envelope_payload(
                    event_type=MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,
                    market_id=None,
                ),
                "snapshot": _snapshot_payload(),
            }
        )

    with pytest.raises(ValidationError, match="market_id must match"):
        TradeObservedEvent.model_validate(
            {
                "envelope": _envelope_payload(
                    event_type=MARKET_TRADE_OBSERVED_EVENT_TYPE,
                    market_id="mkt_other_market_data_event_test",
                ),
                "trade": _trade_payload(),
            }
        )


def test_market_data_events_require_matching_exchange_lineage() -> None:
    with pytest.raises(ValidationError, match="exchange is required"):
        OrderBookDeltaEvent.model_validate(
            {
                "envelope": _envelope_payload(
                    event_type=MARKET_ORDER_BOOK_DELTA_EVENT_TYPE,
                    exchange=None,
                ),
                "delta": _delta_payload(),
            }
        )

    with pytest.raises(ValidationError, match="exchange must match"):
        TradeObservedEvent.model_validate(
            {
                "envelope": _envelope_payload(
                    event_type=MARKET_TRADE_OBSERVED_EVENT_TYPE,
                    exchange="polymarket",
                ),
                "trade": _trade_payload(exchange="kalshi"),
            }
        )


def test_market_data_event_json_round_trip_hash_and_registry_entries() -> None:
    event = OrderBookSnapshotEvent.model_validate(
        {
            "envelope": _envelope_payload(event_type=MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE),
            "snapshot": _snapshot_payload(),
        }
    )
    canonical = canonical_json(event)

    assert OrderBookSnapshotEvent.model_validate_json(canonical) == event
    assert canonical_sha256(event) == canonical_sha256(
        OrderBookSnapshotEvent.model_validate_json(canonical)
    )
    assert json.loads(canonical)["envelope"]["event_type"] == MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE
    assert get_schema_model("order_book_snapshot_event", 1) is OrderBookSnapshotEvent
    assert get_schema_model("order_book_delta_event", 1) is OrderBookDeltaEvent
    assert get_schema_model("trade_observed_event", 1) is TradeObservedEvent
    assert (
        get_schema_registration("order_book_snapshot_event", 1).model_path
        == "pmrp.schemas.events.OrderBookSnapshotEvent"
    )


def _envelope_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "evt_market_data_event_test",
        "event_type": MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,
        "schema_version": 1,
        "occurred_at": "2026-07-28T12:00:00Z",
        "received_at": "2026-07-28T12:00:00.100000Z",
        "published_at": "2026-07-28T12:00:00.200000Z",
        "producer": "market_data_normalizer",
        "exchange": "kalshi",
        "market_id": "mkt_market_data_event_test",
        "correlation_id": "corr_market_data_event_test",
    }
    payload.update(overrides)
    return payload


def _level(price: str, quantity: str = "10") -> dict[str, object]:
    return {"price": price, "quantity": quantity, "order_count": 1}


def _snapshot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "market_id": "mkt_market_data_event_test",
        "contract_id": "ctr_market_data_event_test",
        "exchange": "kalshi",
        "sequence": 10,
        "exchange_occurred_at": "2026-07-28T12:00:00Z",
        "received_at": "2026-07-28T12:00:00.100000Z",
        "bids": (_level("0.42"), _level("0.41")),
        "asks": (_level("0.43"), _level("0.44")),
        "is_valid": True,
        "snapshot_reason": "initial",
    }
    payload.update(overrides)
    return payload


def _delta_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "market_id": "mkt_market_data_event_test",
        "contract_id": "ctr_market_data_event_test",
        "exchange": "kalshi",
        "sequence": 11,
        "previous_sequence": 10,
        "exchange_occurred_at": "2026-07-28T12:00:01Z",
        "received_at": "2026-07-28T12:00:01.100000Z",
        "changes": (
            {
                "side": Side.BUY,
                "price": "0.42",
                "quantity": "12",
                "action": OrderBookDeltaAction.UPSERT,
            },
        ),
    }
    payload.update(overrides)
    return payload


def _trade_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": "trade_market_data_event_test",
        "exchange": "kalshi",
        "exchange_trade_id": "exchange-trade-market-data-event-test",
        "market_id": "mkt_market_data_event_test",
        "contract_id": "ctr_market_data_event_test",
        "outcome_id": "out_yes",
        "price": "0.42",
        "quantity": "4",
        "aggressor_side": Side.BUY,
        "liquidity_role": LiquidityRole.TAKER,
        "exchange_occurred_at": "2026-07-28T12:00:02Z",
        "received_at": "2026-07-28T12:00:02.100000Z",
        "sequence": 12,
    }
    payload.update(overrides)
    return payload
