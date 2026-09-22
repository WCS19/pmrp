"""Unit tests for the RISK-011 portfolio net-exposure limit rule."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_PORTFOLIO_NET_ABOVE_MAX_REASON,
    RISK_PORTFOLIO_NET_LIMIT_RULE_ID,
    RISK_PORTFOLIO_NET_LIMIT_RULE_VERSION,
    RISK_PORTFOLIO_NET_PRICE_MISSING_REASON,
    RISK_PORTFOLIO_NET_STATE_FUTURE_REASON,
    RISK_PORTFOLIO_NET_STATE_MISSING_REASON,
    RISK_PORTFOLIO_NET_STATE_STALE_REASON,
    RISK_PORTFOLIO_NET_VALID_REASON,
    PortfolioNetLimitRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskPortfolioNetExposureState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_portfolio_net")
CONTRACT_ID = ContractId("ctr_risk_portfolio_net")
STRATEGY_ID = StrategyId("strat_risk_portfolio_net")


async def test_portfolio_net_limit_rule_passes_projected_net_under_cap() -> None:
    rule = PortfolioNetLimitRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(quantity="10", limit_price="0.40", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            portfolio_net_exposure=RiskPortfolioNetExposureState(
                current_net_exposure=Decimal("3"),
                max_net_exposure=Decimal("10"),
                observed_at=NOW - timedelta(seconds=1),
            ),
        ),
    )

    assert rule.rule_id == RISK_PORTFOLIO_NET_LIMIT_RULE_ID
    assert rule.version == RISK_PORTFOLIO_NET_LIMIT_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-011"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_PORTFOLIO_NET_VALID_REASON
    assert result.observed_value == Decimal("7.00")
    assert result.limit_value == Decimal("10")
    assert result.unit == "net_exposure"
    assert result.evaluated_at == NOW


async def test_portfolio_net_limit_rule_allows_exact_long_cap_boundary() -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            portfolio_net_exposure=RiskPortfolioNetExposureState(
                current_net_exposure=Decimal("5"),
                max_net_exposure=Decimal("10"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_PORTFOLIO_NET_VALID_REASON
    assert result.observed_value == Decimal("10.00")
    assert result.limit_value == Decimal("10")


async def test_portfolio_net_limit_rule_allows_sell_that_reduces_long_net() -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.SELL),
        RiskContext(
            evaluated_at=NOW,
            portfolio_net_exposure=RiskPortfolioNetExposureState(
                current_net_exposure=Decimal("8"),
                max_net_exposure=Decimal("10"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_PORTFOLIO_NET_VALID_REASON
    assert result.observed_value == Decimal("3.00")
    assert result.limit_value == Decimal("10")


async def test_portfolio_net_limit_rule_rejects_sell_that_increases_short_net() -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.SELL),
        RiskContext(
            evaluated_at=NOW,
            portfolio_net_exposure=RiskPortfolioNetExposureState(
                current_net_exposure=Decimal("-8"),
                max_net_exposure=Decimal("10"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_NET_ABOVE_MAX_REASON
    assert result.observed_value == Decimal("13.00")
    assert result.limit_value == Decimal("10")
    assert result.unit == "net_exposure"


async def test_portfolio_net_limit_rule_includes_open_orders_and_reservations() -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            portfolio_net_exposure=RiskPortfolioNetExposureState(
                current_net_exposure=Decimal("2"),
                open_order_net_exposure_delta=Decimal("2"),
                reserved_net_exposure_delta=Decimal("1"),
                max_net_exposure=Decimal("10"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_PORTFOLIO_NET_VALID_REASON
    assert result.observed_value == Decimal("10.00")
    assert result.limit_value == Decimal("10")


async def test_portfolio_net_limit_rule_rejects_missing_limit_price() -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price=None, side=Side.BUY, order_type=OrderType.MARKET),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_NET_PRICE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "net_exposure"


async def test_portfolio_net_limit_rule_rejects_missing_exposure_state() -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.SELL),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_NET_STATE_MISSING_REASON
    assert result.observed_value == Decimal("5.00")
    assert result.limit_value is None
    assert result.unit == "net_exposure"


async def test_portfolio_net_limit_rule_rejects_stale_exposure_state() -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            portfolio_net_exposure=RiskPortfolioNetExposureState(
                current_net_exposure=Decimal("3"),
                max_net_exposure=Decimal("10"),
                observed_at=NOW - timedelta(seconds=5, milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_NET_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_portfolio_net_limit_rule_rejects_future_exposure_state() -> None:
    result = await PortfolioNetLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="10", limit_price="0.50", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            portfolio_net_exposure=RiskPortfolioNetExposureState(
                current_net_exposure=Decimal("3"),
                max_net_exposure=Decimal("10"),
                observed_at=NOW + timedelta(milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_PORTFOLIO_NET_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


def test_risk_context_portfolio_net_exposure_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        portfolio_net_exposure=RiskPortfolioNetExposureState(
            current_net_exposure=Decimal("3"),
            max_net_exposure=Decimal("10"),
            observed_at=NOW,
        ),
    )

    assert context.portfolio_net_exposure_state() == context.portfolio_net_exposure
    with pytest.raises(FrozenInstanceError):
        context.portfolio_net_exposure = RiskPortfolioNetExposureState(
            current_net_exposure=Decimal("3"),
            max_net_exposure=Decimal("10"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="RiskPortfolioNetExposureState"):
        RiskContext(evaluated_at=NOW, portfolio_net_exposure=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="float"):
        RiskPortfolioNetExposureState(
            current_net_exposure=3.0,  # type: ignore[arg-type]
            max_net_exposure=Decimal("10"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="float"):
        RiskPortfolioNetExposureState(
            current_net_exposure=Decimal("3"),
            max_net_exposure=Decimal("10"),
            open_order_net_exposure_delta=1.0,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_net_exposure"):
        RiskPortfolioNetExposureState(
            current_net_exposure=Decimal("0"),
            max_net_exposure=Decimal("0"),
            observed_at=NOW,
        )


async def test_portfolio_net_limit_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = PortfolioNetLimitRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        PortfolioNetLimitRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        PortfolioNetLimitRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(quantity="10", limit_price="0.50", side=Side.BUY), object())  # type: ignore[arg-type]


def _intent(
    *,
    quantity: str,
    limit_price: str | None,
    side: Side,
    order_type: OrderType = OrderType.LIMIT,
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_portfolio_net",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": side,
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
            "correlation_id": "corr_risk_portfolio_net",
            "idempotency_key": "idem-risk-portfolio-net",
        }
    )
