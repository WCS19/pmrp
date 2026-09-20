"""Simulation order-book projection tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.schemas.enums import Side
from pmrp.schemas.market_data import OrderBookDelta, OrderBookDeltaAction, OrderBookSnapshot
from pmrp.simulation import (
    ORDER_BOOK_PROJECTION_MODEL_NAME,
    ORDER_BOOK_PROJECTION_SNAPSHOT_REASON,
    SimulationInputError,
    apply_order_book_delta,
    apply_order_book_deltas,
    best_ask,
    best_bid,
    is_crossed,
    spread,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
LATER = NOW + timedelta(seconds=1)


def test_order_book_projection_applies_upserts_and_sorts_levels() -> None:
    snapshot = _snapshot()
    delta = _delta(
        sequence=2,
        previous_sequence=1,
        received_at=LATER,
        changes=(
            {"side": Side.BUY, "price": "0.42", "quantity": "7", "action": "upsert"},
            {"side": Side.SELL, "price": "0.43", "quantity": "9", "action": "upsert"},
            {"side": Side.BUY, "price": "0.41", "quantity": "3", "action": "upsert"},
        ),
    )

    projected = apply_order_book_delta(snapshot, delta)

    assert ORDER_BOOK_PROJECTION_MODEL_NAME == "order_book_projection_v1"
    assert projected.sequence == 2
    assert projected.exchange_occurred_at == delta.exchange_occurred_at
    assert projected.received_at == LATER
    assert projected.snapshot_reason == ORDER_BOOK_PROJECTION_SNAPSHOT_REASON
    assert [(level.price, level.quantity) for level in projected.bids] == [
        (Decimal("0.42"), Decimal("7")),
        (Decimal("0.41"), Decimal("3")),
        (Decimal("0.40"), Decimal("20")),
    ]
    assert [(level.price, level.quantity) for level in projected.asks] == [
        (Decimal("0.43"), Decimal("9")),
        (Decimal("0.44"), Decimal("18")),
    ]
    assert projected.bids[1].order_count is None


def test_order_book_projection_deletes_levels_idempotently() -> None:
    snapshot = _snapshot()
    delta = _delta(
        sequence=2,
        previous_sequence=1,
        changes=(
            {"side": Side.BUY, "price": "0.41", "quantity": "0", "action": "delete"},
            {"side": Side.SELL, "price": "0.99", "quantity": "0", "action": "delete"},
        ),
    )

    projected = apply_order_book_delta(snapshot, delta)

    assert [level.price for level in projected.bids] == [Decimal("0.40")]
    assert [level.price for level in projected.asks] == [Decimal("0.44")]


def test_order_book_projection_treats_zero_quantity_upserts_as_removals() -> None:
    projected = apply_order_book_delta(
        _snapshot(),
        _delta(
            sequence=2,
            previous_sequence=1,
            changes=({"side": Side.SELL, "price": "0.44", "quantity": "0", "action": "upsert"},),
        ),
    )

    assert projected.asks == ()


def test_order_book_projection_applies_multiple_deltas_in_order() -> None:
    projected = apply_order_book_deltas(
        _snapshot(),
        (
            _delta(
                sequence=2,
                previous_sequence=1,
                changes=({"side": Side.BUY, "price": "0.42", "quantity": "5", "action": "upsert"},),
            ),
            _delta(
                sequence=3,
                previous_sequence=2,
                changes=(
                    {"side": Side.BUY, "price": "0.42", "quantity": "0", "action": "delete"},
                    {"side": Side.SELL, "price": "0.43", "quantity": "8", "action": "upsert"},
                ),
            ),
        ),
        snapshot_reason="scenario_projection",
    )

    assert projected.sequence == 3
    assert projected.snapshot_reason == "scenario_projection"
    assert [level.price for level in projected.bids] == [Decimal("0.41"), Decimal("0.40")]
    assert [level.price for level in projected.asks] == [Decimal("0.43"), Decimal("0.44")]


def test_order_book_top_of_book_helpers_handle_empty_and_crossed_books() -> None:
    snapshot = _snapshot(
        bids=(
            {"price": "0.45", "quantity": "10"},
            {"price": "0.40", "quantity": "20"},
        ),
        asks=(
            {"price": "0.44", "quantity": "12"},
            {"price": "0.46", "quantity": "18"},
        ),
    )

    assert best_bid(snapshot).price == Decimal("0.45")  # type: ignore[union-attr]
    assert best_ask(snapshot).price == Decimal("0.44")  # type: ignore[union-attr]
    assert spread(snapshot) == Decimal("-0.01")
    assert is_crossed(snapshot)

    empty = _snapshot(bids=(), asks=())
    assert best_bid(empty) is None
    assert best_ask(empty) is None
    assert spread(empty) is None
    assert not is_crossed(empty)


def test_order_book_projection_rejects_invalid_inputs() -> None:
    with pytest.raises(SimulationInputError) as invalid_snapshot_error:
        apply_order_book_delta(
            _snapshot(is_valid=False),
            _delta(sequence=2, previous_sequence=1),
        )

    assert invalid_snapshot_error.value.reason_code == "simulation_order_book_snapshot_invalid"

    with pytest.raises(SimulationInputError) as invalid_delta_error:
        apply_order_book_delta(_snapshot(), "delta")  # type: ignore[arg-type]

    assert invalid_delta_error.value.reason_code == "simulation_order_book_delta_invalid"

    with pytest.raises(SimulationInputError) as market_error:
        apply_order_book_delta(
            _snapshot(),
            _delta(sequence=2, previous_sequence=1, market_id="mkt_other"),
        )

    assert market_error.value.reason_code == "simulation_order_book_market_mismatch"

    with pytest.raises(SimulationInputError) as ambiguous_error:
        apply_order_book_delta(
            _snapshot(sequence=None),
            _delta(sequence=2, previous_sequence=1),
        )

    assert ambiguous_error.value.reason_code == "simulation_order_book_sequence_ambiguous"

    with pytest.raises(SimulationInputError) as sequenced_delta_error:
        apply_order_book_delta(
            _snapshot(sequence=None),
            _delta(sequence=2, previous_sequence=None),
        )

    assert sequenced_delta_error.value.reason_code == "simulation_order_book_sequence_ambiguous"

    with pytest.raises(SimulationInputError) as unsequenced_delta_error:
        apply_order_book_delta(
            _snapshot(),
            _delta(sequence=None, previous_sequence=None),
        )

    assert unsequenced_delta_error.value.reason_code == "simulation_order_book_sequence_ambiguous"

    with pytest.raises(SimulationInputError) as sequence_error:
        apply_order_book_delta(
            _snapshot(),
            _delta(sequence=2, previous_sequence=0),
        )

    assert sequence_error.value.reason_code == "simulation_order_book_sequence_mismatch"

    with pytest.raises(SimulationInputError) as missing_previous_gap_error:
        apply_order_book_delta(
            _snapshot(),
            _delta(sequence=3, previous_sequence=None),
        )

    assert missing_previous_gap_error.value.reason_code == "simulation_order_book_sequence_gap"

    with pytest.raises(SimulationInputError) as previous_gap_error:
        apply_order_book_delta(
            _snapshot(),
            _delta(sequence=3, previous_sequence=1),
        )

    assert previous_gap_error.value.reason_code == "simulation_order_book_sequence_gap"

    with pytest.raises(SimulationInputError) as stale_error:
        apply_order_book_delta(
            _snapshot(),
            _delta(sequence=1, previous_sequence=None),
        )

    assert stale_error.value.reason_code == "simulation_order_book_sequence_stale"

    with pytest.raises(ValueError, match="snapshot_reason"):
        apply_order_book_delta(
            _snapshot(),
            _delta(sequence=2, previous_sequence=1),
            snapshot_reason=" invalid ",
        )


def _snapshot(
    *,
    market_id: str = "mkt_order_book_projection_test",
    contract_id: str = "ctr_order_book_projection_test",
    exchange: str = "kalshi",
    sequence: int | None = 1,
    bids: tuple[dict[str, object], ...] = (
        {"price": "0.41", "quantity": "10", "order_count": 1},
        {"price": "0.40", "quantity": "20", "order_count": 2},
    ),
    asks: tuple[dict[str, object], ...] = ({"price": "0.44", "quantity": "18", "order_count": 2},),
    is_valid: bool = True,
) -> OrderBookSnapshot:
    return OrderBookSnapshot.model_validate(
        {
            "market_id": market_id,
            "contract_id": contract_id,
            "exchange": exchange,
            "sequence": sequence,
            "exchange_occurred_at": NOW,
            "received_at": NOW,
            "bids": bids,
            "asks": asks,
            "is_valid": is_valid,
            "snapshot_reason": "order_book_projection_test",
        }
    )


def _delta(
    *,
    market_id: str = "mkt_order_book_projection_test",
    contract_id: str = "ctr_order_book_projection_test",
    exchange: str = "kalshi",
    sequence: int | None = 2,
    previous_sequence: int | None = 1,
    received_at: datetime = LATER,
    changes: tuple[dict[str, object], ...] = (
        {"side": Side.BUY, "price": "0.42", "quantity": "7", "action": "upsert"},
    ),
) -> OrderBookDelta:
    return OrderBookDelta.model_validate(
        {
            "market_id": market_id,
            "contract_id": contract_id,
            "exchange": exchange,
            "sequence": sequence,
            "previous_sequence": previous_sequence,
            "exchange_occurred_at": received_at,
            "received_at": received_at,
            "changes": _strict_changes(changes),
        }
    )


def _strict_changes(
    changes: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    strict_changes: list[dict[str, object]] = []
    for change in changes:
        strict_change = dict(change)
        action = strict_change["action"]
        if isinstance(action, str):
            strict_change["action"] = OrderBookDeltaAction(action)
        strict_changes.append(strict_change)
    return tuple(strict_changes)
