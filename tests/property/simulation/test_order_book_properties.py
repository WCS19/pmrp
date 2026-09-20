"""Property tests for simulation order-book projection."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.enums import Side
from pmrp.schemas.market_data import OrderBookDelta, OrderBookDeltaAction, OrderBookSnapshot
from pmrp.simulation import apply_order_book_delta

pytestmark = pytest.mark.property

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)

_PRICE = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("0.9999"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_QUANTITY = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(side=st.sampled_from((Side.BUY, Side.SELL)), price=_PRICE, quantity=_QUANTITY)
def test_order_book_projection_is_deterministic(
    side: Side,
    price: Decimal,
    quantity: Decimal,
) -> None:
    snapshot = _snapshot()
    delta = _delta(
        sequence=2,
        previous_sequence=1,
        changes=(
            {
                "side": side,
                "price": str(price),
                "quantity": str(quantity),
                "action": "upsert",
            },
        ),
    )

    first = apply_order_book_delta(snapshot, delta)
    second = apply_order_book_delta(snapshot, delta)

    assert first == second


@given(side=st.sampled_from((Side.BUY, Side.SELL)), price=_PRICE)
def test_order_book_delete_projection_is_idempotent_without_sequences(
    side: Side,
    price: Decimal,
) -> None:
    snapshot = _snapshot(
        sequence=None,
        bids=(({"price": str(price), "quantity": "10"},) if side is Side.BUY else ()),
        asks=(({"price": str(price), "quantity": "10"},) if side is Side.SELL else ()),
    )
    delta = _delta(
        sequence=None,
        previous_sequence=None,
        changes=(
            {
                "side": side,
                "price": str(price),
                "quantity": "0",
                "action": "delete",
            },
        ),
    )

    once = apply_order_book_delta(snapshot, delta)
    twice = apply_order_book_delta(once, delta)

    assert once == twice


@given(
    bid_prices=st.lists(_PRICE, min_size=1, max_size=8, unique=True),
    ask_prices=st.lists(_PRICE, min_size=1, max_size=8, unique=True),
    quantity=_QUANTITY.filter(lambda value: value > Decimal("0")),
)
def test_order_book_projection_sorts_arbitrary_upserts(
    bid_prices: list[Decimal],
    ask_prices: list[Decimal],
    quantity: Decimal,
) -> None:
    changes = tuple(
        {
            "side": Side.BUY,
            "price": str(price),
            "quantity": str(quantity),
            "action": "upsert",
        }
        for price in bid_prices
    ) + tuple(
        {
            "side": Side.SELL,
            "price": str(price),
            "quantity": str(quantity),
            "action": "upsert",
        }
        for price in ask_prices
    )

    projected = apply_order_book_delta(
        _snapshot(sequence=None, bids=(), asks=()),
        _delta(sequence=None, previous_sequence=None, changes=changes),
    )

    assert [level.price for level in projected.bids] == sorted(
        set(bid_prices),
        reverse=True,
    )
    assert [level.price for level in projected.asks] == sorted(set(ask_prices))


def _snapshot(
    *,
    sequence: int | None = 1,
    bids: tuple[dict[str, object], ...] = (
        {"price": "0.41", "quantity": "10"},
        {"price": "0.40", "quantity": "20"},
    ),
    asks: tuple[dict[str, object], ...] = (
        {"price": "0.43", "quantity": "12"},
        {"price": "0.44", "quantity": "18"},
    ),
) -> OrderBookSnapshot:
    return OrderBookSnapshot.model_validate(
        {
            "market_id": "mkt_order_book_projection_property",
            "contract_id": "ctr_order_book_projection_property",
            "exchange": "kalshi",
            "sequence": sequence,
            "exchange_occurred_at": NOW,
            "received_at": NOW,
            "bids": bids,
            "asks": asks,
            "is_valid": True,
            "snapshot_reason": "order_book_projection_property",
        }
    )


def _delta(
    *,
    sequence: int | None,
    previous_sequence: int | None,
    changes: tuple[dict[str, object], ...],
) -> OrderBookDelta:
    return OrderBookDelta.model_validate(
        {
            "market_id": "mkt_order_book_projection_property",
            "contract_id": "ctr_order_book_projection_property",
            "exchange": "kalshi",
            "sequence": sequence,
            "previous_sequence": previous_sequence,
            "exchange_occurred_at": NOW,
            "received_at": NOW,
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
