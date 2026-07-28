import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.market_data import (
    OrderBookDelta,
    OrderBookDeltaAction,
    OrderBookLevel,
    OrderBookSnapshot,
    Trade,
)
from pmrp.schemas.serialization import canonical_json
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _level(price: str, quantity: str = "10", order_count: int | None = 1) -> OrderBookLevel:
    return OrderBookLevel(price=price, quantity=quantity, order_count=order_count)


def _snapshot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "market_id": "mkt_01j00000000000000000000000",
        "contract_id": "ctr_01j00000000000000000000000",
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
        "market_id": "mkt_01j00000000000000000000000",
        "contract_id": "ctr_01j00000000000000000000000",
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
            {
                "side": Side.SELL,
                "price": "0.45",
                "quantity": "0",
                "action": OrderBookDeltaAction.DELETE,
            },
        ),
    }
    payload.update(overrides)
    return payload


def _trade_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "trade_id": "trade_789",
        "exchange": "kalshi",
        "exchange_trade_id": "exchange-trade-789",
        "market_id": "mkt_01j00000000000000000000000",
        "contract_id": "ctr_01j00000000000000000000000",
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


def test_order_book_level_rejects_float_price() -> None:
    with pytest.raises(TypeError, match="float input"):
        OrderBookLevel(price=0.42, quantity="10")


def test_order_book_level_rejects_negative_quantity() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        OrderBookLevel(price="0.42", quantity="-1")


def test_order_book_snapshot_accepts_sorted_book() -> None:
    snapshot = OrderBookSnapshot.model_validate(_snapshot_payload())

    assert snapshot.bids[0].price == Decimal("0.42")
    assert snapshot.asks[0].price == Decimal("0.43")


def test_order_book_snapshot_rejects_unsorted_bids() -> None:
    with pytest.raises(ValidationError, match="bid prices must be strictly descending"):
        OrderBookSnapshot.model_validate(_snapshot_payload(bids=(_level("0.41"), _level("0.42"))))


def test_order_book_snapshot_rejects_unsorted_asks() -> None:
    with pytest.raises(ValidationError, match="ask prices must be strictly ascending"):
        OrderBookSnapshot.model_validate(_snapshot_payload(asks=(_level("0.44"), _level("0.43"))))


def test_order_book_snapshot_rejects_duplicate_bid_prices() -> None:
    with pytest.raises(ValidationError, match="bid prices must be strictly descending"):
        OrderBookSnapshot.model_validate(_snapshot_payload(bids=(_level("0.42"), _level("0.42"))))


def test_order_book_snapshot_rejects_naive_received_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        OrderBookSnapshot.model_validate(
            _snapshot_payload(received_at=datetime.fromisoformat("2026-07-28T12:00:00"))
        )


def test_order_book_snapshot_json_round_trip_accepts_level_arrays() -> None:
    payload = {
        **_snapshot_payload(),
        "bids": [{"price": "0.42", "quantity": "10", "order_count": 1}],
        "asks": [{"price": "0.43", "quantity": "8", "order_count": 2}],
    }

    snapshot = OrderBookSnapshot.model_validate_json(json.dumps(payload))

    assert snapshot.bids == (OrderBookLevel(price="0.42", quantity="10", order_count=1),)
    assert OrderBookSnapshot.model_validate_json(canonical_json(snapshot)) == snapshot


def test_order_book_delta_accepts_zero_quantity_delete() -> None:
    delta = OrderBookDelta.model_validate(_delta_payload())

    assert delta.changes[1].action is OrderBookDeltaAction.DELETE
    assert delta.changes[1].quantity == Decimal("0")


def test_order_book_delta_rejects_negative_sequence() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        OrderBookDelta.model_validate(_delta_payload(sequence=-1))


def test_order_book_delta_rejects_float_quantity() -> None:
    with pytest.raises(TypeError, match="float input"):
        OrderBookDelta.model_validate(
            _delta_payload(
                changes=(
                    {
                        "side": Side.BUY,
                        "price": "0.42",
                        "quantity": 1.0,
                        "action": OrderBookDeltaAction.UPSERT,
                    },
                )
            )
        )


def test_trade_accepts_valid_payload() -> None:
    trade = Trade.model_validate(_trade_payload())

    assert trade.price == Decimal("0.42")
    assert trade.quantity == Decimal("4")
    assert trade.liquidity_role is LiquidityRole.TAKER


def test_trade_rejects_zero_quantity() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        Trade.model_validate(_trade_payload(quantity="0"))


def test_trade_rejects_float_price() -> None:
    with pytest.raises(TypeError, match="float input"):
        Trade.model_validate(_trade_payload(price=0.42))


def test_market_data_registry_entries_exist() -> None:
    assert get_schema_model("order_book_snapshot", 1) is OrderBookSnapshot
    assert get_schema_model("order_book_delta", 1) is OrderBookDelta
    assert get_schema_model("trade", 1) is Trade
    assert (
        get_schema_registration("order_book_snapshot", 1).model_path
        == "pmrp.schemas.market_data.OrderBookSnapshot"
    )
