"""Deterministic queue-position models for simulated orders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from pmrp.schemas.enums import Side
from pmrp.schemas.market_data import OrderBookLevel, OrderBookSnapshot
from pmrp.schemas.numeric import parse_decimal
from pmrp.simulation.errors import SimulationInputError

IMMEDIATE_TOUCH_QUEUE_MODEL_NAME = "immediate_touch_v1"
VOLUME_AHEAD_QUEUE_MODEL_NAME = "volume_ahead_v1"


@dataclass(frozen=True, slots=True)
class QueueEstimate:
    """Estimated queue state for one simulated order."""

    side: Side
    price: Decimal
    quantity: Decimal
    volume_ahead: Decimal
    queue_position: Decimal
    crosses_spread: bool
    rests_on_book: bool


@runtime_checkable
class QueueModel(Protocol):
    """Pure queue model for simulated order placement."""

    def estimate(
        self,
        *,
        snapshot: OrderBookSnapshot,
        side: Side,
        price: Decimal,
        quantity: Decimal,
    ) -> QueueEstimate:
        """Estimate queue state for a simulated order."""
        ...


class ImmediateTouchQueueModel:
    """Assume simulated orders start at the front of the queue."""

    def estimate(
        self,
        *,
        snapshot: OrderBookSnapshot,
        side: Side,
        price: Decimal,
        quantity: Decimal,
    ) -> QueueEstimate:
        """Return a zero-volume-ahead queue estimate."""

        side, price, quantity = _validate_inputs(
            snapshot=snapshot,
            side=side,
            price=price,
            quantity=quantity,
        )
        crosses_spread = _crosses_spread(snapshot=snapshot, side=side, price=price)
        return QueueEstimate(
            side=side,
            price=price,
            quantity=quantity,
            volume_ahead=Decimal("0"),
            queue_position=Decimal("0"),
            crosses_spread=crosses_spread,
            rests_on_book=not crosses_spread,
        )


class VolumeAheadQueueModel:
    """Estimate resting queue position from same-side displayed book volume."""

    def estimate(
        self,
        *,
        snapshot: OrderBookSnapshot,
        side: Side,
        price: Decimal,
        quantity: Decimal,
    ) -> QueueEstimate:
        """Return volume ahead at better prices and the order's limit price."""

        side, price, quantity = _validate_inputs(
            snapshot=snapshot,
            side=side,
            price=price,
            quantity=quantity,
        )
        crosses_spread = _crosses_spread(snapshot=snapshot, side=side, price=price)
        volume_ahead = (
            Decimal("0")
            if crosses_spread
            else _same_side_volume_ahead(snapshot=snapshot, side=side, price=price)
        )
        return QueueEstimate(
            side=side,
            price=price,
            quantity=quantity,
            volume_ahead=volume_ahead,
            queue_position=volume_ahead,
            crosses_spread=crosses_spread,
            rests_on_book=not crosses_spread,
        )


def _validate_inputs(
    *,
    snapshot: OrderBookSnapshot,
    side: Side,
    price: Decimal,
    quantity: Decimal,
) -> tuple[Side, Decimal, Decimal]:
    if not isinstance(snapshot, OrderBookSnapshot):
        raise SimulationInputError(
            "Queue model requires an OrderBookSnapshot",
            reason_code="simulation_queue_snapshot_invalid",
        )
    if not snapshot.is_valid:
        raise SimulationInputError(
            "Queue model requires a valid order book snapshot",
            reason_code="simulation_queue_snapshot_invalid",
            context={"market_id": str(snapshot.market_id)},
        )
    if not isinstance(side, Side):
        raise SimulationInputError(
            "Queue model side must be a canonical Side",
            reason_code="simulation_queue_side_invalid",
        )
    parsed_price = parse_decimal(price, field_name="queue model price")
    parsed_quantity = parse_decimal(quantity, field_name="queue model quantity")
    if parsed_price < Decimal("0"):
        msg = "queue model price must be nonnegative"
        raise ValueError(msg)
    if parsed_quantity <= Decimal("0"):
        msg = "queue model quantity must be positive"
        raise ValueError(msg)
    return side, parsed_price, parsed_quantity


def _crosses_spread(*, snapshot: OrderBookSnapshot, side: Side, price: Decimal) -> bool:
    if side is Side.BUY:
        best_ask = _best_ask(snapshot.asks)
        return best_ask is not None and price >= best_ask
    best_bid = _best_bid(snapshot.bids)
    return best_bid is not None and price <= best_bid


def _same_side_volume_ahead(
    *,
    snapshot: OrderBookSnapshot,
    side: Side,
    price: Decimal,
) -> Decimal:
    if side is Side.BUY:
        return sum(
            (level.quantity for level in snapshot.bids if level.price >= price), Decimal("0")
        )
    return sum((level.quantity for level in snapshot.asks if level.price <= price), Decimal("0"))


def _best_bid(levels: tuple[OrderBookLevel, ...]) -> Decimal | None:
    if not levels:
        return None
    return levels[0].price


def _best_ask(levels: tuple[OrderBookLevel, ...]) -> Decimal | None:
    if not levels:
        return None
    return levels[0].price
