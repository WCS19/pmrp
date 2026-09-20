"""Simulation fill model tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.market_data import OrderBookSnapshot
from pmrp.simulation import (
    FillModel,
    SimulationInputError,
    TouchFillModel,
    TradeThroughFillModel,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def test_touch_fill_model_fills_marketable_buy_at_touch() -> None:
    model = TouchFillModel()

    estimate = model.evaluate(
        snapshot=_snapshot(),
        side=Side.BUY,
        limit_price=Decimal("0.43"),
        quantity=Decimal("5"),
    )

    assert isinstance(model, FillModel)
    assert estimate.side is Side.BUY
    assert estimate.limit_price == Decimal("0.43")
    assert estimate.order_quantity == Decimal("5")
    assert estimate.filled_quantity == Decimal("5")
    assert estimate.remaining_quantity == Decimal("0")
    assert estimate.average_fill_price == Decimal("0.43")
    assert estimate.liquidity_role is LiquidityRole.TAKER
    assert estimate.reason_code == "simulation_touch_full_fill"
    assert estimate.has_fill
    assert estimate.is_full
    assert not estimate.is_partial
    assert len(estimate.components) == 1
    assert estimate.components[0].price == Decimal("0.43")
    assert estimate.components[0].quantity == Decimal("5")


def test_touch_fill_model_fills_marketable_sell_at_touch() -> None:
    estimate = TouchFillModel().evaluate(
        snapshot=_snapshot(),
        side=Side.SELL,
        limit_price=Decimal("0.41"),
        quantity=Decimal("6"),
    )

    assert estimate.filled_quantity == Decimal("6")
    assert estimate.remaining_quantity == Decimal("0")
    assert estimate.average_fill_price == Decimal("0.41")
    assert estimate.reason_code == "simulation_touch_full_fill"
    assert estimate.components[0].price == Decimal("0.41")


def test_touch_fill_model_consumes_visible_depth_for_partial_fill() -> None:
    estimate = TouchFillModel().evaluate(
        snapshot=_snapshot(),
        side=Side.BUY,
        limit_price=Decimal("0.44"),
        quantity=Decimal("40"),
    )

    assert estimate.filled_quantity == Decimal("30")
    assert estimate.remaining_quantity == Decimal("10")
    assert estimate.average_fill_price == Decimal("0.436")
    assert estimate.reason_code == "simulation_touch_partial_fill"
    assert estimate.has_fill
    assert estimate.is_partial
    assert not estimate.is_full
    assert [(fill.price, fill.quantity) for fill in estimate.components] == [
        (Decimal("0.43"), Decimal("12")),
        (Decimal("0.44"), Decimal("18")),
    ]


def test_touch_fill_model_returns_no_fill_for_passive_order() -> None:
    estimate = TouchFillModel().evaluate(
        snapshot=_snapshot(),
        side=Side.BUY,
        limit_price=Decimal("0.42"),
        quantity=Decimal("5"),
    )

    assert estimate.filled_quantity == Decimal("0")
    assert estimate.remaining_quantity == Decimal("5")
    assert estimate.average_fill_price is None
    assert estimate.liquidity_role is LiquidityRole.UNKNOWN
    assert estimate.reason_code == "simulation_touch_no_fill"
    assert not estimate.has_fill
    assert not estimate.is_partial
    assert not estimate.is_full
    assert estimate.components == ()


def test_trade_through_fill_model_requires_strict_price_improvement() -> None:
    model = TradeThroughFillModel()

    touch_only = model.evaluate(
        snapshot=_snapshot(),
        side=Side.BUY,
        limit_price=Decimal("0.43"),
        quantity=Decimal("5"),
    )
    through = model.evaluate(
        snapshot=_snapshot(),
        side=Side.BUY,
        limit_price=Decimal("0.44"),
        quantity=Decimal("20"),
    )
    sell_through = model.evaluate(
        snapshot=_snapshot(),
        side=Side.SELL,
        limit_price=Decimal("0.40"),
        quantity=Decimal("8"),
    )

    assert touch_only.filled_quantity == Decimal("0")
    assert touch_only.reason_code == "simulation_trade_through_no_fill"
    assert through.filled_quantity == Decimal("12")
    assert through.remaining_quantity == Decimal("8")
    assert through.reason_code == "simulation_trade_through_partial_fill"
    assert [(fill.price, fill.quantity) for fill in through.components] == [
        (Decimal("0.43"), Decimal("12")),
    ]
    assert sell_through.filled_quantity == Decimal("8")
    assert sell_through.average_fill_price == Decimal("0.41")
    assert sell_through.reason_code == "simulation_trade_through_full_fill"


def test_fill_models_reject_invalid_inputs() -> None:
    model = TouchFillModel()

    with pytest.raises(SimulationInputError) as invalid_snapshot_error:
        model.evaluate(
            snapshot=_snapshot(is_valid=False),
            side=Side.BUY,
            limit_price=Decimal("0.43"),
            quantity=Decimal("5"),
        )

    assert invalid_snapshot_error.value.reason_code == "simulation_fill_snapshot_invalid"

    with pytest.raises(SimulationInputError) as invalid_side_error:
        model.evaluate(
            snapshot=_snapshot(),
            side="buy",  # type: ignore[arg-type]
            limit_price=Decimal("0.43"),
            quantity=Decimal("5"),
        )

    assert invalid_side_error.value.reason_code == "simulation_fill_side_invalid"

    with pytest.raises(TypeError, match="float input"):
        model.evaluate(
            snapshot=_snapshot(),
            side=Side.BUY,
            limit_price=0.43,  # type: ignore[arg-type]
            quantity=Decimal("5"),
        )

    with pytest.raises(ValueError, match="positive"):
        model.evaluate(
            snapshot=_snapshot(),
            side=Side.BUY,
            limit_price=Decimal("0.43"),
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
            "market_id": "mkt_fill_model_test",
            "contract_id": "ctr_fill_model_test",
            "exchange": "kalshi",
            "sequence": 1,
            "exchange_occurred_at": NOW,
            "received_at": NOW,
            "bids": bids,
            "asks": asks,
            "is_valid": is_valid,
            "snapshot_reason": "fill_model_test",
        }
    )
