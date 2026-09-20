"""Property tests for simulation fill models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.enums import Side
from pmrp.schemas.market_data import OrderBookSnapshot
from pmrp.simulation import TouchFillModel, TradeThroughFillModel

pytestmark = pytest.mark.property

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)
_QUANTITY = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(order_quantity=_QUANTITY, first_ask_quantity=_QUANTITY, second_ask_quantity=_QUANTITY)
def test_touch_fill_model_preserves_quantity_invariant(
    order_quantity: Decimal,
    first_ask_quantity: Decimal,
    second_ask_quantity: Decimal,
) -> None:
    snapshot = _snapshot(
        asks=(
            {"price": "0.43", "quantity": str(first_ask_quantity), "order_count": 1},
            {"price": "0.44", "quantity": str(second_ask_quantity), "order_count": 1},
        )
    )

    estimate = TouchFillModel().evaluate(
        snapshot=snapshot,
        side=Side.BUY,
        limit_price=Decimal("0.44"),
        quantity=order_quantity,
    )

    assert estimate.filled_quantity + estimate.remaining_quantity == order_quantity
    assert Decimal("0") <= estimate.filled_quantity <= order_quantity
    assert Decimal("0") <= estimate.remaining_quantity <= order_quantity
    assert sum((component.quantity for component in estimate.components), Decimal("0")) == (
        estimate.filled_quantity
    )


@given(order_quantity=_QUANTITY, touch_quantity=_QUANTITY)
def test_trade_through_fill_model_never_fills_touch_only_depth(
    order_quantity: Decimal,
    touch_quantity: Decimal,
) -> None:
    snapshot = _snapshot(
        asks=({"price": "0.43", "quantity": str(touch_quantity), "order_count": 1},)
    )

    estimate = TradeThroughFillModel().evaluate(
        snapshot=snapshot,
        side=Side.BUY,
        limit_price=Decimal("0.43"),
        quantity=order_quantity,
    )

    assert estimate.filled_quantity == Decimal("0")
    assert estimate.remaining_quantity == order_quantity
    assert estimate.components == ()
    assert estimate.reason_code == "simulation_trade_through_no_fill"


@given(order_quantity=_QUANTITY, ask_quantity=_QUANTITY)
def test_touch_fill_model_is_deterministic(
    order_quantity: Decimal,
    ask_quantity: Decimal,
) -> None:
    snapshot = _snapshot(asks=({"price": "0.43", "quantity": str(ask_quantity), "order_count": 1},))
    model = TouchFillModel()

    first = model.evaluate(
        snapshot=snapshot,
        side=Side.BUY,
        limit_price=Decimal("0.43"),
        quantity=order_quantity,
    )
    second = model.evaluate(
        snapshot=snapshot,
        side=Side.BUY,
        limit_price=Decimal("0.43"),
        quantity=order_quantity,
    )

    assert first == second


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
            "market_id": "mkt_fill_model_property",
            "contract_id": "ctr_fill_model_property",
            "exchange": "kalshi",
            "sequence": 1,
            "exchange_occurred_at": NOW,
            "received_at": NOW,
            "bids": bids,
            "asks": asks,
            "is_valid": True,
            "snapshot_reason": "fill_model_property",
        }
    )
