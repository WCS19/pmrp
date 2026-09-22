"""Unit tests for the RISK-018 reconciliation-health rule."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_RECONCILIATION_GATE_HELD_REASON,
    RISK_RECONCILIATION_HEALTH_RULE_ID,
    RISK_RECONCILIATION_HEALTH_RULE_VERSION,
    RISK_RECONCILIATION_HEALTH_STATE_FUTURE_REASON,
    RISK_RECONCILIATION_HEALTH_STATE_MISSING_REASON,
    RISK_RECONCILIATION_HEALTH_STATE_STALE_REASON,
    RISK_RECONCILIATION_HEALTHY_REASON,
    RISK_RECONCILIATION_MANUAL_REVIEW_REQUIRED_REASON,
    RISK_RECONCILIATION_MISMATCHES_PRESENT_REASON,
    RISK_RECONCILIATION_UNHEALTHY_STATUS_REASON,
    ReconciliationHealthRule,
    RiskConfigurationError,
    RiskContext,
    RiskInputError,
    RiskReconciliationHealthState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.portfolio import ReconciliationStatus

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_reconciliation_health")
CONTRACT_ID = ContractId("ctr_risk_reconciliation_health")
STRATEGY_ID = StrategyId("strat_risk_reconciliation_health")


async def test_reconciliation_health_rule_passes_when_state_is_healthy() -> None:
    rule = ReconciliationHealthRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            reconciliation_health=RiskReconciliationHealthState(
                status=ReconciliationStatus.HEALTHY,
                trading_gate_released=True,
                observed_at=NOW - timedelta(seconds=1),
            ),
        ),
    )

    assert rule.rule_id == RISK_RECONCILIATION_HEALTH_RULE_ID
    assert rule.version == RISK_RECONCILIATION_HEALTH_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-018"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_RECONCILIATION_HEALTHY_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("1")
    assert result.unit == "healthy_flag"
    assert result.evaluated_at == NOW


@pytest.mark.parametrize(
    "status",
    [
        ReconciliationStatus.MISMATCH,
        ReconciliationStatus.UNKNOWN,
        ReconciliationStatus.FAILED,
    ],
)
async def test_reconciliation_health_rule_rejects_unhealthy_status(
    status: ReconciliationStatus,
) -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        _context(status=status),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_UNHEALTHY_STATUS_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("1")
    assert result.unit == "healthy_flag"


async def test_reconciliation_health_rule_rejects_held_trading_gate() -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        _context(trading_gate_released=False),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_GATE_HELD_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("1")
    assert result.unit == "healthy_flag"


async def test_reconciliation_health_rule_rejects_manual_reviews() -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        _context(manual_review_count=1),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_MANUAL_REVIEW_REQUIRED_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "manual_review_count"


async def test_reconciliation_health_rule_rejects_unresolved_mismatches() -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        _context(unresolved_mismatch_count=2),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_MISMATCHES_PRESENT_REASON
    assert result.observed_value == Decimal("2")
    assert result.limit_value == Decimal("0")
    assert result.unit == "mismatch_count"


async def test_reconciliation_health_rule_rejects_missing_state() -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_HEALTH_STATE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value == Decimal("1")
    assert result.unit == "healthy_flag"


async def test_reconciliation_health_rule_rejects_stale_state() -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        _context(observed_at=NOW - timedelta(seconds=5, milliseconds=1)),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_HEALTH_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_reconciliation_health_rule_rejects_future_state() -> None:
    result = await ReconciliationHealthRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        _context(observed_at=NOW + timedelta(milliseconds=1)),
    )

    assert result.passed is False
    assert result.reason_code == RISK_RECONCILIATION_HEALTH_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


def test_risk_context_reconciliation_health_validates_inputs() -> None:
    context = _context()
    state = context.reconciliation_health_state()

    assert state == context.reconciliation_health
    assert state is not None
    assert state.is_healthy is True
    with pytest.raises(FrozenInstanceError):
        context.reconciliation_health = RiskReconciliationHealthState(
            status=ReconciliationStatus.HEALTHY,
            trading_gate_released=True,
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="RiskReconciliationHealthState"):
        RiskContext(evaluated_at=NOW, reconciliation_health=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ReconciliationStatus"):
        RiskReconciliationHealthState(
            status="healthy",  # type: ignore[arg-type]
            trading_gate_released=True,
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="trading_gate_released"):
        RiskReconciliationHealthState(
            status=ReconciliationStatus.HEALTHY,
            trading_gate_released=1,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(TypeError, match="unresolved_mismatch_count"):
        RiskReconciliationHealthState(
            status=ReconciliationStatus.HEALTHY,
            trading_gate_released=True,
            unresolved_mismatch_count=True,  # type: ignore[arg-type]
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="unresolved_mismatch_count"):
        RiskReconciliationHealthState(
            status=ReconciliationStatus.HEALTHY,
            trading_gate_released=True,
            unresolved_mismatch_count=-1,
            observed_at=NOW,
        )
    with pytest.raises(RiskConfigurationError, match="manual_review_count"):
        RiskReconciliationHealthState(
            status=ReconciliationStatus.HEALTHY,
            trading_gate_released=True,
            manual_review_count=-1,
            observed_at=NOW,
        )


async def test_reconciliation_health_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = ReconciliationHealthRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        ReconciliationHealthRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        ReconciliationHealthRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), object())  # type: ignore[arg-type]


def _context(
    *,
    status: ReconciliationStatus = ReconciliationStatus.HEALTHY,
    trading_gate_released: bool = True,
    unresolved_mismatch_count: int = 0,
    manual_review_count: int = 0,
    observed_at: datetime = NOW,
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        reconciliation_health=RiskReconciliationHealthState(
            status=status,
            trading_gate_released=trading_gate_released,
            unresolved_mismatch_count=unresolved_mismatch_count,
            manual_review_count=manual_review_count,
            observed_at=observed_at,
        ),
    )


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_reconciliation_health",
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": "10",
            "limit_price": "0.50",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_reconciliation_health",
            "idempotency_key": "idem-risk-reconciliation-health",
        }
    )
