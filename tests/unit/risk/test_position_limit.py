"""Unit tests for the RISK-009 market-position limit rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_MARKET_POSITION_ABOVE_MAX_REASON,
    RISK_MARKET_POSITION_LIMIT_RULE_ID,
    RISK_MARKET_POSITION_LIMIT_RULE_VERSION,
    RISK_MARKET_POSITION_STATE_FUTURE_REASON,
    RISK_MARKET_POSITION_STATE_MISSING_REASON,
    RISK_MARKET_POSITION_STATE_STALE_REASON,
    RISK_MARKET_POSITION_VALID_REASON,
    MarketPositionLimitRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskMarketPositionState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_position_limit")
CONTRACT_ID = ContractId("ctr_risk_position_limit")
STRATEGY_ID = StrategyId("strat_risk_position_limit")


async def test_market_position_limit_rule_passes_projected_position_under_cap() -> None:
    rule = MarketPositionLimitRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(quantity="2", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            market_positions={
                MARKET_ID: RiskMarketPositionState(
                    current_position=Decimal("3"),
                    max_position=Decimal("10"),
                    observed_at=NOW - timedelta(seconds=1),
                )
            },
        ),
    )

    assert rule.rule_id == RISK_MARKET_POSITION_LIMIT_RULE_ID
    assert rule.version == RISK_MARKET_POSITION_LIMIT_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-009"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_MARKET_POSITION_VALID_REASON
    assert result.observed_value == Decimal("5")
    assert result.limit_value == Decimal("10")
    assert result.unit == "position"
    assert result.evaluated_at == NOW


async def test_market_position_limit_rule_allows_exact_cap_boundary() -> None:
    result = await MarketPositionLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="3", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            market_positions={
                MARKET_ID: RiskMarketPositionState(
                    current_position=Decimal("7"),
                    max_position=Decimal("10"),
                    observed_at=NOW,
                )
            },
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_MARKET_POSITION_VALID_REASON
    assert result.observed_value == Decimal("10")
    assert result.limit_value == Decimal("10")


async def test_market_position_limit_rule_allows_sell_that_reduces_long_position() -> None:
    result = await MarketPositionLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="3", side=Side.SELL),
        RiskContext(
            evaluated_at=NOW,
            market_positions={
                MARKET_ID: RiskMarketPositionState(
                    current_position=Decimal("7"),
                    max_position=Decimal("10"),
                    observed_at=NOW,
                )
            },
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_MARKET_POSITION_VALID_REASON
    assert result.observed_value == Decimal("4")
    assert result.limit_value == Decimal("10")


async def test_market_position_limit_rule_rejects_sell_that_increases_short_position() -> None:
    result = await MarketPositionLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="3", side=Side.SELL),
        RiskContext(
            evaluated_at=NOW,
            market_positions={
                MARKET_ID: RiskMarketPositionState(
                    current_position=Decimal("-8"),
                    max_position=Decimal("10"),
                    observed_at=NOW,
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_POSITION_ABOVE_MAX_REASON
    assert result.observed_value == Decimal("11")
    assert result.limit_value == Decimal("10")
    assert result.unit == "position"


async def test_market_position_limit_rule_includes_open_orders_and_reservations() -> None:
    result = await MarketPositionLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="4", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            market_positions={
                MARKET_ID: RiskMarketPositionState(
                    current_position=Decimal("2"),
                    open_order_position_delta=Decimal("3"),
                    reserved_position_delta=Decimal("1"),
                    max_position=Decimal("10"),
                    observed_at=NOW,
                )
            },
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_MARKET_POSITION_VALID_REASON
    assert result.observed_value == Decimal("10")
    assert result.limit_value == Decimal("10")


async def test_market_position_limit_rule_rejects_missing_position_state() -> None:
    result = await MarketPositionLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="2", side=Side.BUY),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_POSITION_STATE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "position"


async def test_market_position_limit_rule_rejects_stale_position_state() -> None:
    result = await MarketPositionLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="2", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            market_positions={
                MARKET_ID: RiskMarketPositionState(
                    current_position=Decimal("3"),
                    max_position=Decimal("10"),
                    observed_at=NOW - timedelta(seconds=5, milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_POSITION_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_market_position_limit_rule_rejects_future_position_state() -> None:
    result = await MarketPositionLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(quantity="2", side=Side.BUY),
        RiskContext(
            evaluated_at=NOW,
            market_positions={
                MARKET_ID: RiskMarketPositionState(
                    current_position=Decimal("3"),
                    max_position=Decimal("10"),
                    observed_at=NOW + timedelta(milliseconds=1),
                )
            },
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_MARKET_POSITION_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


def test_risk_context_market_positions_are_immutable_and_validate_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        market_positions={
            MARKET_ID: RiskMarketPositionState(
                current_position=Decimal("3"),
                max_position=Decimal("10"),
                observed_at=NOW,
            )
        },
    )

    with pytest.raises(TypeError, match="does not support item assignment"):
        context.market_positions[MARKET_ID] = RiskMarketPositionState(
            current_position=Decimal("3"),
            max_position=Decimal("10"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="market_positions"):
        RiskContext(evaluated_at=NOW, market_positions=())  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="MarketId"):
        RiskContext(
            evaluated_at=NOW,
            market_positions={
                "mkt_risk_position_limit": RiskMarketPositionState(
                    current_position=Decimal("3"),
                    max_position=Decimal("10"),
                    observed_at=NOW,
                )
            },  # type: ignore[dict-item]
        )
    with pytest.raises(RiskConfigurationError, match="RiskMarketPositionState"):
        RiskContext(
            evaluated_at=NOW,
            market_positions={MARKET_ID: True},  # type: ignore[dict-item]
        )
    with pytest.raises(TypeError, match="float"):
        RiskMarketPositionState(
            current_position=3.0,  # type: ignore[arg-type]
            max_position=Decimal("10"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="float"):
        RiskMarketPositionState(
            current_position=Decimal("3"),
            max_position=Decimal("10"),
            open_order_position_delta=1.0,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_position"):
        RiskMarketPositionState(
            current_position=Decimal("0"),
            max_position=Decimal("0"),
            observed_at=NOW,
        )


async def test_market_position_limit_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = MarketPositionLimitRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        MarketPositionLimitRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        MarketPositionLimitRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(quantity="2", side=Side.BUY), object())  # type: ignore[arg-type]


def _intent(*, quantity: str, side: Side) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_position_limit",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": side,
            "quantity": quantity,
            "limit_price": "0.50",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_position_limit",
            "idempotency_key": "idem-risk-position-limit",
        }
    )
