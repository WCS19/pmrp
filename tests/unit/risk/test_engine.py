"""Unit tests for the central risk decision engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_ENGINE_APPROVAL_LIMIT_PRICE_MISSING_REASON,
    RISK_ENGINE_RULE_ERROR_REASON,
    RISK_ENGINE_RULE_ID,
    RISK_ENGINE_RULE_RESULT_INVALID_REASON,
    RISK_ENGINE_RULE_VERSION,
    RiskConfigurationError,
    RiskContext,
    RiskEngine,
    RiskInputError,
)
from pmrp.schemas.enums import OrderType, RiskDecisionStatus, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult
from pmrp.schemas.serialization import canonical_sha256

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_engine")
CONTRACT_ID = ContractId("ctr_risk_engine")
STRATEGY_ID = StrategyId("strat_risk_engine")
INPUT_SNAPSHOT_ID = "risk_input_01j0000000000000000000"


async def test_risk_engine_returns_approved_decision_when_all_rules_pass() -> None:
    engine = RiskEngine(
        rules=(
            _StaticRule("RISK-TEST-001", passed=True),
            _StaticRule("RISK-TEST-002", passed=True),
        ),
        approval_ttl=timedelta(seconds=2),
    )

    decision = await engine.evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
    )

    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.intent_id == "intent_risk_engine"
    assert decision.evaluated_at == NOW
    assert decision.input_snapshot_id == INPUT_SNAPSHOT_ID
    assert [result.rule_id for result in decision.rule_results] == [
        "RISK-TEST-001",
        "RISK-TEST-002",
    ]
    assert all(result.passed for result in decision.rule_results)
    assert decision.approved_quantity == Decimal("10")
    assert decision.approved_limit_price == Decimal("0.50")
    assert decision.approval_expires_at == NOW + timedelta(seconds=2)
    assert decision.configuration_hash == canonical_sha256(
        (
            {"rule_id": "RISK-TEST-001", "rule_version": "1.0"},
            {"rule_id": "RISK-TEST-002", "rule_version": "1.0"},
        )
    )
    assert str(decision.risk_decision_id).startswith("risk_")


async def test_risk_engine_returns_rejected_decision_when_any_rule_fails() -> None:
    decision = await RiskEngine(
        rules=(
            _StaticRule("RISK-TEST-001", passed=True),
            _StaticRule("RISK-TEST-002", passed=False),
            _StaticRule("RISK-TEST-003", passed=True),
        )
    ).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert [result.rule_id for result in decision.rule_results] == [
        "RISK-TEST-001",
        "RISK-TEST-002",
        "RISK-TEST-003",
    ]
    assert [result.passed for result in decision.rule_results] == [True, False, True]
    assert decision.approved_quantity is None
    assert decision.approved_limit_price is None
    assert decision.approval_expires_at is None


async def test_risk_engine_fails_closed_when_rule_raises() -> None:
    decision = await RiskEngine(
        rules=(
            _StaticRule("RISK-TEST-001", passed=True),
            _RaisingRule("RISK-TEST-002"),
            _StaticRule("RISK-TEST-003", passed=True),
        )
    ).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
    )

    assert decision.status is RiskDecisionStatus.ERROR
    assert [result.rule_id for result in decision.rule_results] == [
        "RISK-TEST-001",
        "RISK-TEST-002",
    ]
    error_result = decision.rule_results[-1]
    assert error_result.passed is False
    assert error_result.reason_code == RISK_ENGINE_RULE_ERROR_REASON
    assert error_result.reason_text == "rule evaluation raised RuntimeError"


async def test_risk_engine_fails_closed_when_rule_returns_invalid_result() -> None:
    decision = await RiskEngine(rules=(_InvalidResultRule("RISK-TEST-001"),)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
    )

    assert decision.status is RiskDecisionStatus.ERROR
    assert decision.rule_results[0].rule_id == "RISK-TEST-001"
    assert decision.rule_results[0].reason_code == RISK_ENGINE_RULE_RESULT_INVALID_REASON
    assert decision.rule_results[0].reason_text == "rule returned non-RiskRuleResult"


async def test_risk_engine_rejects_market_order_that_otherwise_passes() -> None:
    decision = await RiskEngine(rules=(_StaticRule("RISK-TEST-001", passed=True),)).evaluate(
        _intent(order_type=OrderType.MARKET, limit_price=None),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert decision.rule_results[-1].rule_id == RISK_ENGINE_RULE_ID
    assert decision.rule_results[-1].rule_version == RISK_ENGINE_RULE_VERSION
    assert decision.rule_results[-1].reason_code == RISK_ENGINE_APPROVAL_LIMIT_PRICE_MISSING_REASON
    assert decision.approved_quantity is None
    assert decision.approved_limit_price is None


async def test_risk_engine_generates_stable_decision_ids() -> None:
    engine = RiskEngine(rules=(_StaticRule("RISK-TEST-001", passed=True),))
    context = RiskContext(evaluated_at=NOW)
    intent = _intent()

    first = await engine.evaluate(intent, context, input_snapshot_id=INPUT_SNAPSHOT_ID)
    second = await engine.evaluate(intent, context, input_snapshot_id=INPUT_SNAPSHOT_ID)

    assert first == second
    assert first.risk_decision_id == second.risk_decision_id


async def test_risk_engine_validates_configuration_and_inputs() -> None:
    with pytest.raises(RiskConfigurationError, match="at least one rule"):
        RiskEngine(rules=())
    with pytest.raises(RiskConfigurationError, match="unique"):
        RiskEngine(
            rules=(
                _StaticRule("RISK-TEST-001", passed=True),
                _StaticRule("RISK-TEST-001", passed=True),
            )
        )
    with pytest.raises(RiskConfigurationError, match="configuration_hash"):
        RiskEngine(rules=(_StaticRule("RISK-TEST-001", passed=True),), configuration_hash="")
    with pytest.raises(TypeError, match="configuration_hash"):
        RiskEngine(  # type: ignore[arg-type]
            rules=(_StaticRule("RISK-TEST-001", passed=True),),
            configuration_hash=123,
        )
    with pytest.raises(RiskConfigurationError, match="approval_ttl"):
        RiskEngine(
            rules=(_StaticRule("RISK-TEST-001", passed=True),),
            approval_ttl=timedelta(0),
        )
    with pytest.raises(TypeError, match="approval_ttl"):
        RiskEngine(  # type: ignore[arg-type]
            rules=(_StaticRule("RISK-TEST-001", passed=True),),
            approval_ttl=1,
        )
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await RiskEngine(rules=(_StaticRule("RISK-TEST-001", passed=True),)).evaluate(
            object(),  # type: ignore[arg-type]
            RiskContext(evaluated_at=NOW),
            input_snapshot_id=INPUT_SNAPSHOT_ID,
        )
    with pytest.raises(RiskInputError, match="RiskContext"):
        await RiskEngine(rules=(_StaticRule("RISK-TEST-001", passed=True),)).evaluate(
            _intent(),
            object(),  # type: ignore[arg-type]
            input_snapshot_id=INPUT_SNAPSHOT_ID,
        )
    with pytest.raises(RiskInputError, match="input_snapshot_id"):
        await RiskEngine(rules=(_StaticRule("RISK-TEST-001", passed=True),)).evaluate(
            _intent(),
            RiskContext(evaluated_at=NOW),
            input_snapshot_id="",
        )


@dataclass(frozen=True, slots=True)
class _StaticRule:
    rule_id: str
    passed: bool
    version: str = "1.0"

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        del intent
        return _result(
            rule_id=self.rule_id,
            rule_version=self.version,
            passed=self.passed,
            evaluated_at=context.evaluated_at,
        )


@dataclass(frozen=True, slots=True)
class _RaisingRule:
    rule_id: str
    version: str = "1.0"

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        del intent, context
        raise RuntimeError("sensitive payload that must not be surfaced")


@dataclass(frozen=True, slots=True)
class _InvalidResultRule:
    rule_id: str
    version: str = "1.0"

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> object:
        del intent, context
        return object()


def _result(
    *,
    rule_id: str,
    rule_version: str,
    passed: bool,
    evaluated_at: datetime,
) -> RiskRuleResult:
    return RiskRuleResult(
        rule_id=rule_id,
        rule_version=rule_version,
        passed=passed,
        reason_code=f"{rule_id}_PASS" if passed else f"{rule_id}_FAIL",
        reason_text=None,
        observed_value=Decimal("1") if passed else Decimal("0"),
        limit_value=Decimal("1"),
        unit="flag",
        evaluated_at=evaluated_at,
    )


def _intent(
    *,
    order_type: OrderType = OrderType.LIMIT,
    limit_price: str | None = "0.50",
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_engine",
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
            "correlation_id": "corr_risk_engine",
            "idempotency_key": "idem-risk-engine",
        }
    )
