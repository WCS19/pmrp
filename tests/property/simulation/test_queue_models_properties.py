"""Property tests for simulation queue models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.enums import Side
from pmrp.schemas.market_data import OrderBookSnapshot
from pmrp.simulation import ImmediateTouchQueueModel, VolumeAheadQueueModel

pytestmark = pytest.mark.property

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
_QUANTITY = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(quantity=_QUANTITY)
def test_immediate_touch_queue_model_always_has_zero_volume_ahead(quantity: Decimal) -> None:
    estimate = ImmediateTouchQueueModel().estimate(
        snapshot=_snapshot(),
        side=Side.BUY,
        price=Decimal("0.42"),
        quantity=quantity,
    )

    assert estimate.volume_ahead == Decimal("0")
    assert estimate.queue_position == Decimal("0")


@given(first_bid_quantity=_QUANTITY, second_bid_quantity=_QUANTITY)
def test_volume_ahead_queue_model_is_deterministic_and_nonnegative(
    first_bid_quantity: Decimal,
    second_bid_quantity: Decimal,
) -> None:
    snapshot = _snapshot(
        bids=(
            {"price": "0.41", "quantity": str(first_bid_quantity), "order_count": 1},
            {"price": "0.40", "quantity": str(second_bid_quantity), "order_count": 1},
        )
    )
    model = VolumeAheadQueueModel()

    first = model.estimate(
        snapshot=snapshot,
        side=Side.BUY,
        price=Decimal("0.40"),
        quantity=Decimal("1"),
    )
    second = model.estimate(
        snapshot=snapshot,
        side=Side.BUY,
        price=Decimal("0.40"),
        quantity=Decimal("1"),
    )

    assert first == second
    assert first.volume_ahead == first_bid_quantity + second_bid_quantity
    assert first.volume_ahead >= Decimal("0")


def _snapshot(
    *,
    bids: tuple[dict[str, object], ...] = (
        {"price": "0.41", "quantity": "10", "order_count": 1},
        {"price": "0.40", "quantity": "20", "order_count": 1},
    ),
    asks: tuple[dict[str, object], ...] = (
        {"price": "0.43", "quantity": "12", "order_count": 1},
        {"price": "0.44", "quantity": "18", "order_count": 1},
    ),
) -> OrderBookSnapshot:
    return OrderBookSnapshot.model_validate(
        {
            "market_id": "mkt_queue_model_property",
            "contract_id": "ctr_queue_model_property",
            "exchange": "kalshi",
            "sequence": 1,
            "exchange_occurred_at": NOW,
            "received_at": NOW,
            "bids": bids,
            "asks": asks,
            "is_valid": True,
            "snapshot_reason": "queue_model_property",
        }
    )
