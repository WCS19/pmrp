"""Simulation slippage model tests."""

from __future__ import annotations

from decimal import Decimal, localcontext

import pytest

from pmrp.schemas.enums import LiquidityRole, Side
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation import (
    BPS_SLIPPAGE_MODEL_NAME,
    NO_SLIPPAGE_MODEL_NAME,
    BpsSlippageModel,
    NoSlippageModel,
    SimulationConfigurationError,
    SimulationInputError,
    SlippageModel,
)

pytestmark = pytest.mark.unit


def test_no_slippage_model_returns_unchanged_price() -> None:
    model = NoSlippageModel()

    estimate = model.estimate(
        side=Side.BUY,
        price=Decimal("0.42"),
        quantity=Decimal("10"),
        liquidity_role=LiquidityRole.TAKER,
    )

    assert isinstance(model, SlippageModel)
    assert estimate.side is Side.BUY
    assert estimate.liquidity_role is LiquidityRole.TAKER
    assert estimate.input_price == Decimal("0.42")
    assert estimate.adjusted_price == Decimal("0.42")
    assert estimate.quantity == Decimal("10")
    assert estimate.slippage_bps == Decimal("0")
    assert estimate.slippage_amount_per_unit == Decimal("0")
    assert estimate.total_slippage == Decimal("0")


def test_bps_slippage_model_worsens_taker_buy_and_sell_prices() -> None:
    model = BpsSlippageModel.from_bps(Decimal("10"))

    buy_estimate = model.estimate(
        side=Side.BUY,
        price=Decimal("0.50"),
        quantity=Decimal("100"),
        liquidity_role=LiquidityRole.TAKER,
    )
    sell_estimate = model.estimate(
        side=Side.SELL,
        price=Decimal("0.50"),
        quantity=Decimal("100"),
        liquidity_role=LiquidityRole.TAKER,
    )

    assert buy_estimate.adjusted_price == Decimal("0.5005")
    assert buy_estimate.slippage_amount_per_unit == Decimal("0.0005")
    assert buy_estimate.total_slippage == Decimal("0.0500")
    assert buy_estimate.slippage_bps == Decimal("10")
    assert sell_estimate.adjusted_price == Decimal("0.4995")
    assert sell_estimate.slippage_amount_per_unit == Decimal("0.0005")
    assert sell_estimate.total_slippage == Decimal("0.0500")


def test_bps_slippage_model_does_not_apply_to_non_taker_liquidity() -> None:
    model = BpsSlippageModel.from_bps(Decimal("25"))

    maker_estimate = model.estimate(
        side=Side.BUY,
        price=Decimal("0.50"),
        quantity=Decimal("100"),
        liquidity_role=LiquidityRole.MAKER,
    )
    unknown_estimate = model.estimate(
        side=Side.SELL,
        price=Decimal("0.50"),
        quantity=Decimal("100"),
        liquidity_role=LiquidityRole.UNKNOWN,
    )

    assert maker_estimate.adjusted_price == Decimal("0.50")
    assert maker_estimate.slippage_bps == Decimal("0")
    assert maker_estimate.total_slippage == Decimal("0")
    assert unknown_estimate.adjusted_price == Decimal("0.50")
    assert unknown_estimate.total_slippage == Decimal("0")


def test_bps_slippage_model_floors_sell_price_at_zero() -> None:
    estimate = BpsSlippageModel.from_bps(Decimal("20000")).estimate(
        side=Side.SELL,
        price=Decimal("0.50"),
        quantity=Decimal("3"),
        liquidity_role=LiquidityRole.TAKER,
    )

    assert estimate.adjusted_price == Decimal("0")
    assert estimate.slippage_amount_per_unit == Decimal("0.50")
    assert estimate.total_slippage == Decimal("1.50")


def test_slippage_models_load_from_simulation_configuration() -> None:
    bps_model = BpsSlippageModel.from_configuration(
        _configuration(
            slippage_model=BPS_SLIPPAGE_MODEL_NAME,
            taker_slippage_bps=Decimal("1.50"),
        )
    )
    no_model = NoSlippageModel.from_configuration(
        _configuration(slippage_model=NO_SLIPPAGE_MODEL_NAME, taker_slippage_bps=None)
    )

    assert bps_model.taker_slippage_bps == Decimal("1.50")
    assert isinstance(no_model, NoSlippageModel)


def test_slippage_models_reject_unsupported_configuration() -> None:
    with pytest.raises(SimulationConfigurationError) as unsupported_error:
        BpsSlippageModel.from_configuration(_configuration(slippage_model="sampled_slippage_v1"))

    assert unsupported_error.value.reason_code == "simulation_slippage_model_unsupported"
    assert unsupported_error.value.context["slippage_model"] == "sampled_slippage_v1"

    with pytest.raises(SimulationConfigurationError) as missing_error:
        BpsSlippageModel.from_configuration(
            _configuration(slippage_model=BPS_SLIPPAGE_MODEL_NAME, taker_slippage_bps=None)
        )

    assert missing_error.value.reason_code == "simulation_taker_slippage_missing"

    with pytest.raises(SimulationConfigurationError):
        NoSlippageModel.from_configuration(_configuration(slippage_model=BPS_SLIPPAGE_MODEL_NAME))


def test_bps_slippage_model_uses_explicit_decimal_arithmetic_context() -> None:
    model = BpsSlippageModel.from_bps(Decimal("0.123456789012"))
    price = Decimal("0.123456789012")
    quantity = Decimal("0.987654321098")

    with localcontext() as context:
        context.prec = 12
        low_precision_estimate = model.estimate(
            side=Side.BUY,
            price=price,
            quantity=quantity,
            liquidity_role=LiquidityRole.TAKER,
        )
        context_sensitive_adjusted_price = price + (
            price * model.taker_slippage_bps / Decimal("10000")
        )

    with localcontext() as context:
        context.prec = 28
        default_precision_estimate = model.estimate(
            side=Side.BUY,
            price=price,
            quantity=quantity,
            liquidity_role=LiquidityRole.TAKER,
        )

    assert low_precision_estimate == default_precision_estimate
    assert low_precision_estimate.adjusted_price != context_sensitive_adjusted_price


def test_slippage_models_reject_invalid_inputs() -> None:
    model = BpsSlippageModel.from_bps(Decimal("10"))

    with pytest.raises(SimulationInputError) as side_error:
        model.estimate(
            side="buy",  # type: ignore[arg-type]
            price=Decimal("0.50"),
            quantity=Decimal("100"),
            liquidity_role=LiquidityRole.TAKER,
        )

    assert side_error.value.reason_code == "simulation_slippage_side_invalid"

    with pytest.raises(SimulationInputError) as role_error:
        model.estimate(
            side=Side.BUY,
            price=Decimal("0.50"),
            quantity=Decimal("100"),
            liquidity_role="taker",  # type: ignore[arg-type]
        )

    assert role_error.value.reason_code == "simulation_slippage_liquidity_role_invalid"

    with pytest.raises(TypeError, match="float input"):
        BpsSlippageModel.from_bps(1.5)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="nonnegative"):
        BpsSlippageModel.from_bps(Decimal("-1"))

    with pytest.raises(TypeError, match="float input"):
        model.estimate(
            side=Side.BUY,
            price=0.50,  # type: ignore[arg-type]
            quantity=Decimal("100"),
            liquidity_role=LiquidityRole.TAKER,
        )

    with pytest.raises(ValueError, match="positive"):
        model.estimate(
            side=Side.BUY,
            price=Decimal("0.50"),
            quantity=Decimal("0"),
            liquidity_role=LiquidityRole.TAKER,
        )

    with pytest.raises(ValueError, match="significant digits"):
        BpsSlippageModel.from_bps(Decimal("0.12345678901234567890123456789"))


def _configuration(
    *,
    slippage_model: str = BPS_SLIPPAGE_MODEL_NAME,
    taker_slippage_bps: Decimal | None = Decimal("1.50"),
) -> SimulationConfiguration:
    return SimulationConfiguration.model_validate(
        {
            "simulation_version": "sim-v1",
            "fill_model": "touch_fill_v1",
            "queue_model": "immediate_touch_v1",
            "latency_model": "fixed_latency_v1",
            "fee_model": "fee_table_v1",
            "rejection_model": "bounded_rejection_v1",
            "slippage_model": slippage_model,
            "settlement_model": "none_v1",
            "random_seed": 42,
            "fixed_latency_ms": 125,
            "taker_slippage_bps": None if taker_slippage_bps is None else str(taker_slippage_bps),
            "parameters": {},
        }
    )
