"""Simulation queue model tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pmrp.schemas.enums import Side
from pmrp.schemas.market_data import OrderBookSnapshot
from pmrp.simulation import (
    ImmediateTouchQueueModel,
    QueueModel,
    SimulationInputError,
    VolumeAheadQueueModel,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def test_immediate_touch_queue_model_places_orders_at_front() -> None:
    model = ImmediateTouchQueueModel()

    estimate = model.estimate(
        snapshot=_snapshot(),
        side=Side.BUY,
        price=Decimal("0.42"),
        quantity=Decimal("5"),
    )

    assert isinstance(model, QueueModel)
    assert estimate.side is Side.BUY
    assert estimate.price == Decimal("0.42")
    assert estimate.quantity == Decimal("5")
    assert estimate.volume_ahead == Decimal("0")
    assert estimate.queue_position == Decimal("0")
    assert not estimate.crosses_spread
    assert estimate.rests_on_book


def test_immediate_touch_queue_model_marks_crossing_orders() -> None:
    buy_estimate = ImmediateTouchQueueModel().estimate(
        snapshot=_snapshot(),
        side=Side.BUY,
        price=Decimal("0.43"),
        quantity=Decimal("5"),
    )
    sell_estimate = ImmediateTouchQueueModel().estimate(
        snapshot=_snapshot(),
        side=Side.SELL,
        price=Decimal("0.41"),
        quantity=Decimal("5"),
    )

    assert buy_estimate.crosses_spread
    assert not buy_estimate.rests_on_book
    assert sell_estimate.crosses_spread
    assert not sell_estimate.rests_on_book


def test_volume_ahead_queue_model_counts_same_side_displayed_volume() -> None:
    model = VolumeAheadQueueModel()

    buy_estimate = model.estimate(
        snapshot=_snapshot(),
        side=Side.BUY,
        price=Decimal("0.40"),
        quantity=Decimal("5"),
    )
    sell_estimate = model.estimate(
        snapshot=_snapshot(),
        side=Side.SELL,
        price=Decimal("0.44"),
        quantity=Decimal("5"),
    )

    assert buy_estimate.volume_ahead == Decimal("30")
    assert buy_estimate.queue_position == Decimal("30")
    assert buy_estimate.rests_on_book
    assert sell_estimate.volume_ahead == Decimal("30")
    assert sell_estimate.queue_position == Decimal("30")
    assert sell_estimate.rests_on_book


def test_volume_ahead_queue_model_uses_zero_for_crossing_orders() -> None:
    estimate = VolumeAheadQueueModel().estimate(
        snapshot=_snapshot(),
        side=Side.BUY,
        price=Decimal("0.45"),
        quantity=Decimal("5"),
    )

    assert estimate.crosses_spread
    assert not estimate.rests_on_book
    assert estimate.volume_ahead == Decimal("0")
    assert estimate.queue_position == Decimal("0")


def test_volume_ahead_queue_model_handles_empty_books() -> None:
    estimate = VolumeAheadQueueModel().estimate(
        snapshot=_snapshot(bids=(), asks=()),
        side=Side.BUY,
        price=Decimal("0.40"),
        quantity=Decimal("5"),
    )

    assert not estimate.crosses_spread
    assert estimate.rests_on_book
    assert estimate.volume_ahead == Decimal("0")


def test_queue_models_reject_invalid_inputs() -> None:
    model = VolumeAheadQueueModel()

    with pytest.raises(SimulationInputError) as invalid_snapshot_error:
        model.estimate(
            snapshot=_snapshot(is_valid=False),
            side=Side.BUY,
            price=Decimal("0.40"),
            quantity=Decimal("5"),
        )

    assert invalid_snapshot_error.value.reason_code == "simulation_queue_snapshot_invalid"

    with pytest.raises(SimulationInputError) as invalid_side_error:
        model.estimate(
            snapshot=_snapshot(),
            side="buy",  # type: ignore[arg-type]
            price=Decimal("0.40"),
            quantity=Decimal("5"),
        )

    assert invalid_side_error.value.reason_code == "simulation_queue_side_invalid"

    with pytest.raises(TypeError, match="float input"):
        model.estimate(
            snapshot=_snapshot(),
            side=Side.BUY,
            price=0.40,  # type: ignore[arg-type]
            quantity=Decimal("5"),
        )

    with pytest.raises(ValueError, match="positive"):
        model.estimate(
            snapshot=_snapshot(),
            side=Side.BUY,
            price=Decimal("0.40"),
            quantity=Decimal("0"),
        )


def _snapshot(
    *,
    bids: tuple[dict[str, object], ...] = (
        {"price": "0.41", "quantity": "10", "order_count": 1},
        {"price": "0.40", "quantity": "20", "order_count": 2},
    ),
    asks: tuple[dict[str, object], ...] = (
        {"price": "0.43", "quantity": "12", "order_count": 1},
        {"price": "0.44", "quantity": "18", "order_count": 2},
    ),
    is_valid: bool = True,
) -> OrderBookSnapshot:
    return OrderBookSnapshot.model_validate(
        {
            "market_id": "mkt_queue_model_test",
            "contract_id": "ctr_queue_model_test",
            "exchange": "kalshi",
            "sequence": 1,
            "exchange_occurred_at": NOW,
            "received_at": NOW,
            "bids": bids,
            "asks": asks,
            "is_valid": is_valid,
            "snapshot_reason": "queue_model_test",
        }
    )
