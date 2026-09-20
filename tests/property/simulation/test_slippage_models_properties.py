"""Property tests for simulation slippage models."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.simulation import BpsSlippageModel, NoSlippageModel

pytestmark = pytest.mark.property

_PRICE = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_QUANTITY = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_BPS = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(price=_PRICE, quantity=_QUANTITY, bps=_BPS)
def test_bps_slippage_model_worsens_buy_taker_prices(
    price: Decimal,
    quantity: Decimal,
    bps: Decimal,
) -> None:
    estimate = BpsSlippageModel.from_bps(bps).estimate(
        side=Side.BUY,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.TAKER,
    )

    assert estimate.adjusted_price >= price
    assert estimate.slippage_amount_per_unit == estimate.adjusted_price - price
    assert estimate.total_slippage == estimate.slippage_amount_per_unit * quantity


@given(price=_PRICE, quantity=_QUANTITY, bps=_BPS)
def test_bps_slippage_model_worsens_sell_taker_prices(
    price: Decimal,
    quantity: Decimal,
    bps: Decimal,
) -> None:
    estimate = BpsSlippageModel.from_bps(bps).estimate(
        side=Side.SELL,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.TAKER,
    )

    assert Decimal("0") <= estimate.adjusted_price <= price
    assert estimate.slippage_amount_per_unit == price - estimate.adjusted_price
    assert estimate.total_slippage == estimate.slippage_amount_per_unit * quantity


@given(price=_PRICE, quantity=_QUANTITY, bps=_BPS)
def test_bps_slippage_model_is_deterministic(
    price: Decimal,
    quantity: Decimal,
    bps: Decimal,
) -> None:
    model = BpsSlippageModel.from_bps(bps)

    first = model.estimate(
        side=Side.BUY,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.TAKER,
    )
    second = model.estimate(
        side=Side.BUY,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.TAKER,
    )

    assert first == second


@given(price=_PRICE, quantity=_QUANTITY, bps=_BPS)
def test_bps_slippage_model_leaves_maker_prices_unchanged(
    price: Decimal,
    quantity: Decimal,
    bps: Decimal,
) -> None:
    estimate = BpsSlippageModel.from_bps(bps).estimate(
        side=Side.BUY,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.MAKER,
    )

    assert estimate.adjusted_price == price
    assert estimate.total_slippage == Decimal("0")


@given(price=_PRICE, quantity=_QUANTITY)
def test_no_slippage_model_is_deterministic_and_zero(
    price: Decimal,
    quantity: Decimal,
) -> None:
    model = NoSlippageModel()

    first = model.estimate(
        side=Side.SELL,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.TAKER,
    )
    second = model.estimate(
        side=Side.SELL,
        price=price,
        quantity=quantity,
        liquidity_role=LiquidityRole.TAKER,
    )

    assert first == second
    assert first.adjusted_price == price
    assert first.total_slippage == Decimal("0")
