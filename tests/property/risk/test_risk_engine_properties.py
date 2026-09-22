"""Property tests for central risk decision engine invariants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pmrp.risk import RiskContext, RiskEngine
from pmrp.schemas.enums import OrderType, RiskDecisionStatus, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_engine_property")
CONTRACT_ID = ContractId("ctr_risk_engine_property")
STRATEGY_ID = StrategyId("strat_risk_engine_property")
INPUT_SNAPSHOT_ID = "risk_input_01j0000000000000000000"


@given(rule_outcomes=st.lists(st.booleans(), min_size=1, max_size=10))
@settings(deadline=None)
async def test_risk_engine_status_matches_rule_outcomes(rule_outcomes: list[bool]) -> None:
    decision = await RiskEngine(
        rules=tuple(
            _StaticRule(f"RISK-PROP-{index:03d}", passed=passed)
            for index, passed in enumerate(rule_outcomes)
        )
    ).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
    )

    assert tuple(result.passed for result in decision.rule_results) == tuple(rule_outcomes)
    if all(rule_outcomes):
        assert decision.status is RiskDecisionStatus.APPROVED
        assert decision.approved_quantity == Decimal("10")
        assert decision.approved_limit_price == Decimal("0.50")
    else:
        assert decision.status is RiskDecisionStatus.REJECTED
        assert decision.approved_quantity is None
        assert decision.approved_limit_price is None


@given(rule_outcomes=st.lists(st.booleans(), min_size=1, max_size=10))
@settings(deadline=None)
async def test_risk_engine_decision_ids_are_deterministic(rule_outcomes: list[bool]) -> None:
    rules = tuple(
        _StaticRule(f"RISK-PROP-{index:03d}", passed=passed)
        for index, passed in enumerate(rule_outcomes)
    )
    engine = RiskEngine(rules=rules)
    intent = _intent()
    context = RiskContext(evaluated_at=NOW)

    first = await engine.evaluate(intent, context, input_snapshot_id=INPUT_SNAPSHOT_ID)
    second = await engine.evaluate(intent, context, input_snapshot_id=INPUT_SNAPSHOT_ID)

    assert first == second
    assert first.risk_decision_id == second.risk_decision_id


@dataclass(frozen=True, slots=True)
class _StaticRule:
    rule_id: str
    passed: bool
    version: str = "1.0"

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        del intent
        return RiskRuleResult(
            rule_id=self.rule_id,
            rule_version=self.version,
            passed=self.passed,
            reason_code=f"{self.rule_id}_PASS" if self.passed else f"{self.rule_id}_FAIL",
            reason_text=None,
            observed_value=Decimal("1") if self.passed else Decimal("0"),
            limit_value=Decimal("1"),
            unit="flag",
            evaluated_at=context.evaluated_at,
        )


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_engine_property",
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
            "correlation_id": "corr_risk_engine_property",
            "idempotency_key": "idem-risk-engine-property",
        }
    )
