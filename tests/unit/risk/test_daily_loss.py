"""Unit tests for the RISK-014 daily-loss limit rule."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_DAILY_LOSS_ABOVE_MAX_REASON,
    RISK_DAILY_LOSS_LIMIT_RULE_ID,
    RISK_DAILY_LOSS_LIMIT_RULE_VERSION,
    RISK_DAILY_LOSS_STATE_FUTURE_REASON,
    RISK_DAILY_LOSS_STATE_MISSING_REASON,
    RISK_DAILY_LOSS_STATE_STALE_REASON,
    RISK_DAILY_LOSS_VALID_REASON,
    DailyLossLimitRule,
    RiskConfigurationError,
    RiskContext,
    RiskDailyLossState,
    RiskInputError,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_daily_loss")
CONTRACT_ID = ContractId("ctr_risk_daily_loss")
STRATEGY_ID = StrategyId("strat_risk_daily_loss")


async def test_daily_loss_limit_rule_passes_when_loss_is_below_cap() -> None:
    rule = DailyLossLimitRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            daily_loss=RiskDailyLossState(
                daily_realized_pnl=Decimal("-75"),
                daily_unrealized_pnl=Decimal("10"),
                max_daily_loss=Decimal("100"),
                observed_at=NOW - timedelta(seconds=1),
            ),
        ),
    )

    assert rule.rule_id == RISK_DAILY_LOSS_LIMIT_RULE_ID
    assert rule.version == RISK_DAILY_LOSS_LIMIT_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-014"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_DAILY_LOSS_VALID_REASON
    assert result.observed_value == Decimal("65")
    assert result.limit_value == Decimal("100")
    assert result.unit == "loss"
    assert result.evaluated_at == NOW


async def test_daily_loss_limit_rule_treats_positive_pnl_as_zero_loss() -> None:
    result = await DailyLossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(limit_price=None, order_type=OrderType.MARKET),
        RiskContext(
            evaluated_at=NOW,
            daily_loss=RiskDailyLossState(
                daily_realized_pnl=Decimal("40"),
                daily_unrealized_pnl=Decimal("2.50"),
                max_daily_loss=Decimal("100"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_DAILY_LOSS_VALID_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("100")


async def test_daily_loss_limit_rule_allows_exact_cap_boundary() -> None:
    result = await DailyLossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            daily_loss=RiskDailyLossState(
                daily_realized_pnl=Decimal("-125"),
                daily_unrealized_pnl=Decimal("25"),
                max_daily_loss=Decimal("100"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is True
    assert result.reason_code == RISK_DAILY_LOSS_VALID_REASON
    assert result.observed_value == Decimal("100")
    assert result.limit_value == Decimal("100")


async def test_daily_loss_limit_rule_rejects_missing_daily_loss_state() -> None:
    result = await DailyLossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DAILY_LOSS_STATE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value is None
    assert result.unit == "loss"


async def test_daily_loss_limit_rule_rejects_stale_daily_loss_state() -> None:
    result = await DailyLossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            daily_loss=RiskDailyLossState(
                daily_realized_pnl=Decimal("-75"),
                daily_unrealized_pnl=Decimal("10"),
                max_daily_loss=Decimal("100"),
                observed_at=NOW - timedelta(seconds=5, milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DAILY_LOSS_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_daily_loss_limit_rule_rejects_future_daily_loss_state() -> None:
    result = await DailyLossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            daily_loss=RiskDailyLossState(
                daily_realized_pnl=Decimal("-75"),
                daily_unrealized_pnl=Decimal("10"),
                max_daily_loss=Decimal("100"),
                observed_at=NOW + timedelta(milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DAILY_LOSS_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


async def test_daily_loss_limit_rule_rejects_loss_above_cap() -> None:
    result = await DailyLossLimitRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            daily_loss=RiskDailyLossState(
                daily_realized_pnl=Decimal("-125.10"),
                daily_unrealized_pnl=Decimal("25"),
                max_daily_loss=Decimal("100"),
                observed_at=NOW,
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DAILY_LOSS_ABOVE_MAX_REASON
    assert result.observed_value == Decimal("100.10")
    assert result.limit_value == Decimal("100")
    assert result.unit == "loss"


def test_risk_context_daily_loss_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        daily_loss=RiskDailyLossState(
            daily_realized_pnl=Decimal("-75"),
            daily_unrealized_pnl=Decimal("10"),
            max_daily_loss=Decimal("100"),
            observed_at=NOW,
        ),
    )

    assert context.daily_loss_state() == context.daily_loss
    assert context.daily_loss_state().total_daily_pnl == Decimal("-65")
    assert context.daily_loss_state().current_daily_loss == Decimal("65")
    with pytest.raises(FrozenInstanceError):
        context.daily_loss = RiskDailyLossState(
            daily_realized_pnl=Decimal("-75"),
            daily_unrealized_pnl=Decimal("10"),
            max_daily_loss=Decimal("100"),
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="RiskDailyLossState"):
        RiskContext(evaluated_at=NOW, daily_loss=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="float"):
        RiskDailyLossState(
            daily_realized_pnl=-75.0,  # type: ignore[arg-type]
            daily_unrealized_pnl=Decimal("10"),
            max_daily_loss=Decimal("100"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="float"):
        RiskDailyLossState(
            daily_realized_pnl=Decimal("-75"),
            daily_unrealized_pnl=10.0,  # type: ignore[arg-type]
            max_daily_loss=Decimal("100"),
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="float"):
        RiskDailyLossState(
            daily_realized_pnl=Decimal("-75"),
            daily_unrealized_pnl=Decimal("10"),
            max_daily_loss=100.0,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="max_daily_loss"):
        RiskDailyLossState(
            daily_realized_pnl=Decimal("-75"),
            daily_unrealized_pnl=Decimal("10"),
            max_daily_loss=Decimal("0"),
            observed_at=NOW,
        )


async def test_daily_loss_limit_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = DailyLossLimitRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        DailyLossLimitRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        DailyLossLimitRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), object())  # type: ignore[arg-type]


def _intent(
    *,
    limit_price: str | None = "0.50",
    order_type: OrderType = OrderType.LIMIT,
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_daily_loss",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": "10",
            "limit_price": limit_price,
            "order_type": order_type,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_daily_loss",
            "idempotency_key": "idem-risk-daily-loss",
        }
    )
