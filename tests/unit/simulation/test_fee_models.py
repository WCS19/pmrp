"""Simulation fee model tests."""

from __future__ import annotations

from decimal import Decimal, localcontext

import pytest

from pmrp.schemas.enums import LiquidityRole
from pmrp.simulation import (
    FeeModel,
    FeeRule,
    FeeTableModel,
    SimulationConfigurationError,
    SimulationInputError,
)

pytestmark = pytest.mark.unit


def test_fee_table_model_calculates_configured_taker_fee() -> None:
    model = FeeTableModel.from_rules(
        FeeRule(
            exchange="kalshi",
            liquidity_role=LiquidityRole.TAKER,
            fee_rate_bps=Decimal("10"),
            fixed_fee=Decimal("0.01"),
        )
    )

    estimate = model.estimate(
        exchange="kalshi",
        price=Decimal("0.50"),
        quantity=Decimal("100"),
        liquidity_role=LiquidityRole.TAKER,
    )

    assert isinstance(model, FeeModel)
    assert estimate.exchange == "kalshi"
    assert estimate.liquidity_role is LiquidityRole.TAKER
    assert estimate.currency == "USD"
    assert estimate.notional == Decimal("50.00")
    assert estimate.fee_amount == Decimal("0.060")
    assert estimate.rebate_amount == Decimal("0")
    assert estimate.net_fee_amount == Decimal("0.060")


def test_fee_table_model_selects_exchange_and_liquidity_role_rule() -> None:
    model = FeeTableModel.from_rules(
        FeeRule(
            exchange="kalshi",
            liquidity_role=LiquidityRole.TAKER,
            fee_rate_bps=Decimal("10"),
        ),
        FeeRule(
            exchange="kalshi",
            liquidity_role=LiquidityRole.MAKER,
            rebate_rate_bps=Decimal("2.5"),
            fixed_rebate=Decimal("0.005"),
        ),
        FeeRule(
            exchange="polymarket",
            liquidity_role=LiquidityRole.MAKER,
            fee_rate_bps=Decimal("1"),
        ),
    )

    estimate = model.estimate(
        exchange="kalshi",
        price=Decimal("0.40"),
        quantity=Decimal("250"),
        liquidity_role=LiquidityRole.MAKER,
    )

    assert estimate.notional == Decimal("100.00")
    assert estimate.fee_amount == Decimal("0")
    assert estimate.rebate_amount == Decimal("0.03000")
    assert estimate.net_fee_amount == Decimal("-0.03000")


def test_fee_table_model_supports_explicit_zero_fee_rule() -> None:
    model = FeeTableModel.from_rules(
        FeeRule.zero(exchange="kalshi", liquidity_role=LiquidityRole.TAKER)
    )

    estimate = model.estimate(
        exchange="kalshi",
        price=Decimal("0.61"),
        quantity=Decimal("17"),
        liquidity_role=LiquidityRole.TAKER,
    )

    assert estimate.notional == Decimal("10.37")
    assert estimate.fee_amount == Decimal("0")
    assert estimate.rebate_amount == Decimal("0")
    assert estimate.net_fee_amount == Decimal("0")


def test_fee_table_model_uses_explicit_decimal_arithmetic_context() -> None:
    model = FeeTableModel.from_rules(
        FeeRule(
            exchange="kalshi",
            liquidity_role=LiquidityRole.TAKER,
            fee_rate_bps=Decimal("0.123456789012"),
            fixed_fee=Decimal("0.000000000001"),
            rebate_rate_bps=Decimal("0.012345678901"),
        )
    )
    price = Decimal("0.123456789012")
    quantity = Decimal("0.987654321098")

    with localcontext() as context:
        context.prec = 12
        low_precision_estimate = model.estimate(
            exchange="kalshi",
            price=price,
            quantity=quantity,
            liquidity_role=LiquidityRole.TAKER,
        )
        context_sensitive_product = price * quantity

    with localcontext() as context:
        context.prec = 28
        default_precision_estimate = model.estimate(
            exchange="kalshi",
            price=price,
            quantity=quantity,
            liquidity_role=LiquidityRole.TAKER,
        )

    assert low_precision_estimate == default_precision_estimate
    assert low_precision_estimate.notional != context_sensitive_product


def test_fee_table_model_rejects_missing_and_duplicate_rules() -> None:
    model = FeeTableModel.from_rules(FeeRule(exchange="kalshi", liquidity_role=LiquidityRole.TAKER))

    with pytest.raises(SimulationConfigurationError) as missing_error:
        model.estimate(
            exchange="kalshi",
            price=Decimal("0.50"),
            quantity=Decimal("10"),
            liquidity_role=LiquidityRole.MAKER,
        )

    assert missing_error.value.reason_code == "simulation_fee_rule_missing"
    assert missing_error.value.context["exchange"] == "kalshi"
    assert missing_error.value.context["liquidity_role"] == "maker"

    with pytest.raises(SimulationConfigurationError) as duplicate_error:
        FeeTableModel.from_rules(
            FeeRule(exchange="kalshi", liquidity_role=LiquidityRole.TAKER),
            FeeRule(exchange="kalshi", liquidity_role=LiquidityRole.TAKER),
        )

    assert duplicate_error.value.reason_code == "simulation_fee_rule_duplicate"


def test_fee_rules_reject_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="at least one rule"):
        FeeTableModel.from_rules()

    with pytest.raises(TypeError, match="FeeRule"):
        FeeTableModel(rules=("not-a-rule",))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="currency"):
        FeeRule(exchange="kalshi", liquidity_role=LiquidityRole.TAKER, currency="usd")

    with pytest.raises(TypeError, match="float input"):
        FeeRule(
            exchange="kalshi",
            liquidity_role=LiquidityRole.TAKER,
            fee_rate_bps=1.5,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="nonnegative"):
        FeeRule(
            exchange="kalshi",
            liquidity_role=LiquidityRole.TAKER,
            fixed_fee=Decimal("-0.01"),
        )

    with pytest.raises(ValueError, match="significant digits"):
        FeeRule(
            exchange="kalshi",
            liquidity_role=LiquidityRole.TAKER,
            fee_rate_bps=Decimal("0.12345678901234567890123456789"),
        )

    with pytest.raises(ValueError, match="fractional digits"):
        FeeRule(
            exchange="kalshi",
            liquidity_role=LiquidityRole.TAKER,
            fixed_rebate=Decimal("0.0000000000000000001"),
        )


def test_fee_table_model_rejects_invalid_estimate_inputs() -> None:
    model = FeeTableModel.from_rules(FeeRule(exchange="kalshi", liquidity_role=LiquidityRole.TAKER))

    with pytest.raises(SimulationInputError) as role_error:
        model.estimate(
            exchange="kalshi",
            price=Decimal("0.50"),
            quantity=Decimal("10"),
            liquidity_role="taker",  # type: ignore[arg-type]
        )

    assert role_error.value.reason_code == "simulation_fee_liquidity_role_invalid"

    with pytest.raises(TypeError, match="float input"):
        model.estimate(
            exchange="kalshi",
            price=0.50,  # type: ignore[arg-type]
            quantity=Decimal("10"),
            liquidity_role=LiquidityRole.TAKER,
        )

    with pytest.raises(ValueError, match="positive"):
        model.estimate(
            exchange="kalshi",
            price=Decimal("0.50"),
            quantity=Decimal("0"),
            liquidity_role=LiquidityRole.TAKER,
        )

    with pytest.raises(ValueError, match="adjusted exponent"):
        model.estimate(
            exchange="kalshi",
            price=Decimal("1E+37"),
            quantity=Decimal("1"),
            liquidity_role=LiquidityRole.TAKER,
        )
