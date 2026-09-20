"""Deterministic order-book projection helpers for simulations."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from pmrp.schemas.enums import Side
from pmrp.schemas.market_data import (
    OrderBookDelta,
    OrderBookDeltaAction,
    OrderBookDeltaLevel,
    OrderBookLevel,
    OrderBookSnapshot,
)
from pmrp.simulation.errors import SimulationInputError

ORDER_BOOK_PROJECTION_MODEL_NAME = "order_book_projection_v1"
ORDER_BOOK_PROJECTION_SNAPSHOT_REASON = "projected_delta"

_ZERO = Decimal("0")


def best_bid(snapshot: OrderBookSnapshot) -> OrderBookLevel | None:
    """Return the best bid level for a valid snapshot, if present."""

    _validate_snapshot(snapshot)
    return snapshot.bids[0] if snapshot.bids else None


def best_ask(snapshot: OrderBookSnapshot) -> OrderBookLevel | None:
    """Return the best ask level for a valid snapshot, if present."""

    _validate_snapshot(snapshot)
    return snapshot.asks[0] if snapshot.asks else None


def spread(snapshot: OrderBookSnapshot) -> Decimal | None:
    """Return the current ask-bid spread, including negative crossed spreads."""

    bid = best_bid(snapshot)
    ask = best_ask(snapshot)
    if bid is None or ask is None:
        return None
    return ask.price - bid.price


def is_crossed(snapshot: OrderBookSnapshot) -> bool:
    """Return whether the top of book is locked or crossed."""

    current_spread = spread(snapshot)
    return current_spread is not None and current_spread <= _ZERO


def apply_order_book_delta(
    snapshot: OrderBookSnapshot,
    delta: OrderBookDelta,
    *,
    snapshot_reason: str = ORDER_BOOK_PROJECTION_SNAPSHOT_REASON,
) -> OrderBookSnapshot:
    """Apply one canonical order-book delta to a canonical snapshot."""

    _validate_snapshot(snapshot)
    _validate_delta(delta)
    _validate_lineage(snapshot=snapshot, delta=delta)
    _validate_sequence(snapshot=snapshot, delta=delta)
    snapshot_reason = _validate_snapshot_reason(snapshot_reason)

    bids_by_price = _levels_by_price(snapshot.bids)
    asks_by_price = _levels_by_price(snapshot.asks)

    for change in delta.changes:
        _apply_change(
            bids_by_price=bids_by_price,
            asks_by_price=asks_by_price,
            change=change,
        )

    return OrderBookSnapshot(
        market_id=snapshot.market_id,
        contract_id=snapshot.contract_id,
        exchange=snapshot.exchange,
        sequence=delta.sequence if delta.sequence is not None else snapshot.sequence,
        exchange_occurred_at=delta.exchange_occurred_at,
        received_at=delta.received_at,
        bids=_sorted_levels(bids_by_price, reverse=True),
        asks=_sorted_levels(asks_by_price, reverse=False),
        is_valid=True,
        snapshot_reason=snapshot_reason,
    )


def apply_order_book_deltas(
    snapshot: OrderBookSnapshot,
    deltas: Iterable[OrderBookDelta],
    *,
    snapshot_reason: str = ORDER_BOOK_PROJECTION_SNAPSHOT_REASON,
) -> OrderBookSnapshot:
    """Apply canonical order-book deltas in caller-provided order."""

    projected = snapshot
    for delta in deltas:
        projected = apply_order_book_delta(
            projected,
            delta,
            snapshot_reason=snapshot_reason,
        )
    return projected


def _validate_snapshot(snapshot: OrderBookSnapshot) -> None:
    if not isinstance(snapshot, OrderBookSnapshot):
        raise SimulationInputError(
            "Order-book projection requires an OrderBookSnapshot",
            reason_code="simulation_order_book_snapshot_invalid",
        )
    if not snapshot.is_valid:
        raise SimulationInputError(
            "Order-book projection requires a valid snapshot",
            reason_code="simulation_order_book_snapshot_invalid",
            context={"market_id": str(snapshot.market_id)},
        )


def _validate_delta(delta: OrderBookDelta) -> None:
    if not isinstance(delta, OrderBookDelta):
        raise SimulationInputError(
            "Order-book projection requires an OrderBookDelta",
            reason_code="simulation_order_book_delta_invalid",
        )


def _validate_lineage(
    *,
    snapshot: OrderBookSnapshot,
    delta: OrderBookDelta,
) -> None:
    if snapshot.market_id != delta.market_id:
        raise SimulationInputError(
            "Order-book delta market does not match snapshot",
            reason_code="simulation_order_book_market_mismatch",
            context={
                "snapshot_market_id": str(snapshot.market_id),
                "delta_market_id": str(delta.market_id),
            },
        )
    if snapshot.contract_id != delta.contract_id:
        raise SimulationInputError(
            "Order-book delta contract does not match snapshot",
            reason_code="simulation_order_book_contract_mismatch",
            context={
                "snapshot_contract_id": str(snapshot.contract_id),
                "delta_contract_id": str(delta.contract_id),
            },
        )
    if snapshot.exchange != delta.exchange:
        raise SimulationInputError(
            "Order-book delta exchange does not match snapshot",
            reason_code="simulation_order_book_exchange_mismatch",
            context={
                "snapshot_exchange": snapshot.exchange,
                "delta_exchange": delta.exchange,
            },
        )


def _validate_sequence(
    *,
    snapshot: OrderBookSnapshot,
    delta: OrderBookDelta,
) -> None:
    if snapshot.sequence is None and (
        delta.previous_sequence is not None or delta.sequence is not None
    ):
        raise SimulationInputError(
            "Order-book delta sequence cannot be checked against unsequenced snapshot",
            reason_code="simulation_order_book_sequence_ambiguous",
            context={
                "delta_previous_sequence": str(delta.previous_sequence),
                "delta_sequence": str(delta.sequence),
            },
        )
    if snapshot.sequence is not None and delta.sequence is None:
        raise SimulationInputError(
            "Order-book delta sequence is required for sequenced snapshots",
            reason_code="simulation_order_book_sequence_ambiguous",
            context={
                "snapshot_sequence": str(snapshot.sequence),
                "delta_previous_sequence": str(delta.previous_sequence),
            },
        )
    if (
        snapshot.sequence is not None
        and delta.previous_sequence is not None
        and snapshot.sequence != delta.previous_sequence
    ):
        raise SimulationInputError(
            "Order-book delta previous sequence does not match snapshot sequence",
            reason_code="simulation_order_book_sequence_mismatch",
            context={
                "snapshot_sequence": str(snapshot.sequence),
                "delta_previous_sequence": str(delta.previous_sequence),
            },
        )
    if (
        snapshot.sequence is not None
        and delta.sequence is not None
        and delta.sequence <= snapshot.sequence
    ):
        raise SimulationInputError(
            "Order-book delta sequence must advance the snapshot sequence",
            reason_code="simulation_order_book_sequence_stale",
            context={
                "snapshot_sequence": str(snapshot.sequence),
                "delta_sequence": str(delta.sequence),
            },
        )
    if snapshot.sequence is not None and delta.sequence is not None:
        expected_sequence = snapshot.sequence + 1
        if delta.sequence != expected_sequence:
            raise SimulationInputError(
                "Order-book delta sequence must be the next snapshot sequence",
                reason_code="simulation_order_book_sequence_gap",
                context={
                    "snapshot_sequence": str(snapshot.sequence),
                    "delta_sequence": str(delta.sequence),
                    "expected_sequence": str(expected_sequence),
                },
            )
    if (
        delta.previous_sequence is not None
        and delta.sequence is not None
        and delta.sequence != delta.previous_sequence + 1
    ):
        raise SimulationInputError(
            "Order-book delta sequence must be the next previous sequence",
            reason_code="simulation_order_book_sequence_invalid",
            context={
                "delta_previous_sequence": str(delta.previous_sequence),
                "delta_sequence": str(delta.sequence),
                "expected_sequence": str(delta.previous_sequence + 1),
            },
        )


def _validate_snapshot_reason(snapshot_reason: str) -> str:
    if type(snapshot_reason) is not str:
        raise TypeError("snapshot_reason must be a string")
    if snapshot_reason == "" or snapshot_reason.strip() != snapshot_reason:
        raise ValueError("snapshot_reason must be nonempty without surrounding whitespace")
    return snapshot_reason


def _levels_by_price(levels: tuple[OrderBookLevel, ...]) -> dict[Decimal, OrderBookLevel]:
    return {level.price: level for level in levels}


def _apply_change(
    *,
    bids_by_price: dict[Decimal, OrderBookLevel],
    asks_by_price: dict[Decimal, OrderBookLevel],
    change: OrderBookDeltaLevel,
) -> None:
    target = bids_by_price if change.side is Side.BUY else asks_by_price
    if change.action is OrderBookDeltaAction.DELETE or change.quantity == _ZERO:
        target.pop(change.price, None)
        return
    target[change.price] = OrderBookLevel(price=change.price, quantity=change.quantity)


def _sorted_levels(
    levels_by_price: dict[Decimal, OrderBookLevel],
    *,
    reverse: bool,
) -> tuple[OrderBookLevel, ...]:
    return tuple(
        sorted(
            levels_by_price.values(),
            key=lambda level: level.price,
            reverse=reverse,
        )
    )
