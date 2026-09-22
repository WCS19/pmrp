"""Unit tests for the RISK-010 portfolio gross-exposure limit rule."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_PORTFOLIO_GROSS_ABOVE_MAX_REASON,
    RISK_PORTFOLIO_GROSS_LIMIT_RULE_ID,
    RISK_PORTFOLIO_GROSS_LIMIT_RULE_VERSION,
    RISK_PORTFOLIO_GROSS_PRICE_MISSING_REASON,
    RISK_PORTFOLIO_GROSS_STATE_FUTURE_REASON,
    RISK_PORTFOLIO_GROSS_STATE_MISSING_REASON,
    RISK_PORTFOLIO_GROSS_STATE_STALE_REASON,
    RISK_PORTFOLIO_GROSS_VALID_REASON,
    PortfolioGrossLimitRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskPortfolioGrossExposureState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_portfolio_gross")
CONTRACT_ID = ContractId("ctr_risk_portfolio_gross")
STRATEGY_ID = StrategyId("strat_risk_portfolio_gross")


async def test_portfolio_gross_limit_rule_passes_projected_exposure_under_cap() -> None:
    rule = PortfolioGrossLimitRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(quantity="10", limit_price="0.40"),
        RiskContext(
            evaluated_at=NOW,
            portfolio_gross_exposure=RiskPortfolioGrossExposureState(
                current_gross_exposure=Decimal("15"),
                max_gross_exposure=Decimal("25"),
                observed_at=NOW - timedelta(seconds=1),
            ),
        ),
    )

    assert rule.rule_id == RISK_PORTFOLIO_GROSS_LIMIT_RULE_ID
    assert rule.version == RISK_PORTFOLIO_GROSS_LIMIT_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-010"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_PORTFOLIO_GROSS_VALID_REASON
    assert result.observed_value == Decimal("19.00")
    assert result.limit_value == Decimal("25")
    assert result.unit == "gross_exposure"
    assert result.evaluated_at == NOW


async def test_portfolio_gross_limit_rule_allows_exact_cap_boundary() -> None:
    result = await PortfolioGrossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            portfolio_gross_exposure=RiskPortfolioGrossExposureState(
                current_gross_exposure=Decimal("15"),
                max_gross_exposure=Decimal("20"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_PORTFOLIO_GROSS_VALID_REASON
    assert result.observed_value == Decimal("20.00")
    assert result.limit_value == Decimal("20")


async def test_portfolio_gross_limit_rule_includes_open_orders_and_reservations() -> None:
    result = await PortfolioGrossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            portfolio_gross_exposure=RiskPortfolioGrossExposureState(
                current_gross_exposure=Decimal("10"),
                open_order_gross_exposure=Decimal("3"),
                reserved_gross_exposure=Decimal("2"),
                max_gross_exposure=Decimal("20"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_PORTFOLIO_GROSS_VALID_REASON
    assert result.observed_value == Decimal("20.00")
    assert result.limit_value == Decimal("20")


async def test_portfolio_gross_limit_rule_rejects_missing_limit_price() -> None:
    result = await PortfolioGrossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price=None, order_type=OrderType.MARKET),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_GROSS_PRICE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "gross_exposure"


async def test_portfolio_gross_limit_rule_rejects_missing_exposure_state() -> None:
    result = await PortfolioGrossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_GROSS_STATE_MISSING_REASON
    assert result.observed_value == Decimal("5.00")
    assert result.limit_value is None
    assert result.unit == "gross_exposure"


async def test_portfolio_gross_limit_rule_rejects_stale_exposure_state() -> None:
    result = await PortfolioGrossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            portfolio_gross_exposure=RiskPortfolioGrossExposureState(
                current_gross_exposure=Decimal("15"),
                max_gross_exposure=Decimal("25"),
                observed_at=NOW - timedelta(seconds=5, milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_GROSS_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_portfolio_gross_limit_rule_rejects_future_exposure_state() -> None:
    result = await PortfolioGrossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50"),
        RiskContext(
            evaluated_at=NOW,
            portfolio_gross_exposure=RiskPortfolioGrossExposureState(
                current_gross_exposure=Decimal("15"),
                max_gross_exposure=Decimal("25"),
                observed_at=NOW + timedelta(milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_GROSS_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


async def test_portfolio_gross_limit_rule_rejects_exposure_above_cap() -> None:
    result = await PortfolioGrossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.51"),
        RiskContext(
            evaluated_at=NOW,
            portfolio_gross_exposure=RiskPortfolioGrossExposureState(
                current_gross_exposure=Decimal("15"),
                max_gross_exposure=Decimal("20"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_GROSS_ABOVE_MAX_REASON
    assert result.observed_value == Decimal("20.10")
    assert result.limit_value == Decimal("20")
    assert result.unit == "gross_exposure"


def test_risk_context_portfolio_gross_exposure_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        portfolio_gross_exposure=RiskPortfolioGrossExposureState(
            current_gross_exposure=Decimal("15"),
            max_gross_exposure=Decimal("25"),
            observed_at=NOW,
        ),
    )

    assert context.portfolio_gross_exposure_state() == context.portfolio_gross_exposure
    with pytest.raises(FrozenInstanceError):
        context.portfolio_gross_exposure = RiskPortfolioGrossExposureState(
            current_gross_exposure=Decimal("15"),
            max_gross_exposure=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="RiskPortfolioGrossExposureState"):
        RiskContext(evaluated_at=NOW, portfolio_gross_exposure=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="float"):
        RiskPortfolioGrossExposureState(
            current_gross_exposure=15.0,  # type: ignore[arg-type]
            max_gross_exposure=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="float"):
        RiskPortfolioGrossExposureState(
            current_gross_exposure=Decimal("15"),
            max_gross_exposure=Decimal("25"),
            open_order_gross_exposure=1.0,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="current_gross_exposure"):
        RiskPortfolioGrossExposureState(
            current_gross_exposure=Decimal("-0.01"),
            max_gross_exposure=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="open_order_gross_exposure"):
        RiskPortfolioGrossExposureState(
            current_gross_exposure=Decimal("15"),
            open_order_gross_exposure=Decimal("-0.01"),
            max_gross_exposure=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="reserved_gross_exposure"):
        RiskPortfolioGrossExposureState(
            current_gross_exposure=Decimal("15"),
            reserved_gross_exposure=Decimal("-0.01"),
            max_gross_exposure=Decimal("25"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_gross_exposure"):
        RiskPortfolioGrossExposureState(
            current_gross_exposure=Decimal("15"),
            max_gross_exposure=Decimal("0"),
            observed_at=NOW,
        )


async def test_portfolio_gross_limit_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = PortfolioGrossLimitRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        PortfolioGrossLimitRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        PortfolioGrossLimitRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(quantity="10", limit_price="0.50"), object())  # type: ignore[arg-type]


def _intent(
    *,
    quantity: str,
    limit_price: str | None,
    order_type: OrderType = OrderType.LIMIT,
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_portfolio_gross",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": quantity,
            "limit_price": limit_price,
            "order_type": order_type,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_portfolio_gross",
            "idempotency_key": "idem-risk-portfolio-gross",
        }
    )
