"""Unit tests for deterministic risk breach derivation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    HashingRiskBreachIdGenerator,
    RiskBreachFactory,
    RiskBreachPolicy,
    RiskConfigurationError,
    RiskInputError,
)
from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.risk import RiskDecision, RiskLimitScope, RiskRuleResult

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_breach_factory_builds_breaches_for_configured_failed_results() -> None:
    decision = _decision(
        rule_results=(
            _result(rule_id="RISK-STRATEGY-CAPITAL", passed=True),
            _result(
                rule_id="RISK-STRATEGY-CAPITAL",
                passed=False,
                reason_code="RISK_STRATEGY_CAPITAL_ABOVE_MAX",
                evaluated_at=NOW + timedelta(seconds=1),
            ),
        )
    )
    factory = RiskBreachFactory(
        policies=(
            RiskBreachPolicy(
                rule_id="RISK-STRATEGY-CAPITAL",
                reason_code="RISK_STRATEGY_CAPITAL_ABOVE_MAX",
                scope=RiskLimitScope.STRATEGY,
                scope_id="strat_risk_breach",
                severity="critical",
                action_taken="reject_order",
            ),
        )
    )

    breaches = factory.breaches_for_decision(decision)

    assert len(breaches) == 1
    breach = breaches[0]
    assert breach.breach_id.startswith("breach_")
    assert breach.rule_id == "RISK-STRATEGY-CAPITAL"
    assert breach.rule_version == "1.0"
    assert breach.scope is RiskLimitScope.STRATEGY
    assert breach.scope_id == "strat_risk_breach"
    assert breach.severity == "critical"
    assert breach.detected_at == NOW + timedelta(seconds=1)
    assert breach.observed_value == Decimal("125")
    assert breach.limit_value == Decimal("100")
    assert breach.unit == "usd"
    assert breach.action_taken == "reject_order"
    assert breach.correlation_id == decision.correlation_id


def test_breach_factory_uses_rule_level_policy_when_reason_specific_absent() -> None:
    decision = _decision(
        rule_results=(
            _result(
                rule_id="RISK-ORDER-NOTIONAL",
                passed=False,
                reason_code="RISK_ORDER_NOTIONAL_ABOVE_MAX",
            ),
        )
    )
    factory = RiskBreachFactory(
        policies=(
            RiskBreachPolicy(
                rule_id="RISK-ORDER-NOTIONAL",
                scope=RiskLimitScope.MARKET,
                scope_id="mkt_risk_breach",
                severity="warning",
                action_taken="reject_order",
            ),
        )
    )

    breaches = factory.breaches_for_decision(decision)

    assert len(breaches) == 1
    assert breaches[0].scope is RiskLimitScope.MARKET
    assert breaches[0].severity == "warning"


def test_breach_factory_prefers_reason_specific_policy() -> None:
    decision = _decision(
        rule_results=(
            _result(
                rule_id="RISK-PORTFOLIO-GROSS",
                passed=False,
                reason_code="RISK_PORTFOLIO_GROSS_ABOVE_MAX",
            ),
        )
    )
    factory = RiskBreachFactory(
        policies=(
            RiskBreachPolicy(
                rule_id="RISK-PORTFOLIO-GROSS",
                scope=RiskLimitScope.ACCOUNT,
                severity="warning",
                action_taken="reject_order",
            ),
            RiskBreachPolicy(
                rule_id="RISK-PORTFOLIO-GROSS",
                reason_code="RISK_PORTFOLIO_GROSS_ABOVE_MAX",
                scope=RiskLimitScope.ACCOUNT,
                severity="critical",
                action_taken="halt_account",
            ),
        )
    )

    breaches = factory.breaches_for_decision(decision)

    assert len(breaches) == 1
    assert breaches[0].severity == "critical"
    assert breaches[0].action_taken == "halt_account"


def test_breach_factory_skips_passed_and_unconfigured_results() -> None:
    decision = _decision(
        rule_results=(
            _result(rule_id="RISK-CONFIGURED", passed=True),
            _result(rule_id="RISK-UNCONFIGURED", passed=False),
        )
    )
    factory = RiskBreachFactory(
        policies=(
            RiskBreachPolicy(
                rule_id="RISK-CONFIGURED",
                scope=RiskLimitScope.GLOBAL,
                severity="warning",
                action_taken="none",
            ),
        )
    )

    assert factory.breaches_for_decision(decision) == ()


def test_breach_factory_generates_stable_distinct_ids() -> None:
    decision = _decision(
        rule_results=(
            _result(rule_id="RISK-LIMIT", passed=False, reason_code="RISK_LIMIT_A"),
            _result(rule_id="RISK-LIMIT", passed=False, reason_code="RISK_LIMIT_B"),
        )
    )
    factory = RiskBreachFactory(
        policies=(
            RiskBreachPolicy(
                rule_id="RISK-LIMIT",
                scope=RiskLimitScope.GLOBAL,
                severity="critical",
                action_taken="reject_order",
            ),
        )
    )

    first = factory.breaches_for_decision(decision)
    second = factory.breaches_for_decision(decision)

    assert first == second
    assert first[0].breach_id != first[1].breach_id


def test_hashing_breach_id_generator_is_stable() -> None:
    decision = _decision(rule_results=(_result(rule_id="RISK-LIMIT", passed=False),))
    policy = RiskBreachPolicy(
        rule_id="RISK-LIMIT",
        scope=RiskLimitScope.GLOBAL,
        severity="critical",
        action_taken="reject_order",
    )
    result = decision.rule_results[0]
    generator = HashingRiskBreachIdGenerator()

    first = generator.breach_id(decision=decision, result=result, result_index=0, policy=policy)
    second = generator.breach_id(decision=decision, result=result, result_index=0, policy=policy)

    assert first == second
    assert first.startswith("breach_")


def test_breach_factory_validates_configuration() -> None:
    policy = RiskBreachPolicy(
        rule_id="RISK-LIMIT",
        scope=RiskLimitScope.GLOBAL,
        severity="critical",
        action_taken="reject_order",
    )

    with pytest.raises(RiskConfigurationError, match="at least one policy"):
        RiskBreachFactory(policies=())
    with pytest.raises(RiskConfigurationError, match="unique"):
        RiskBreachFactory(policies=(policy, policy))
    with pytest.raises(TypeError, match="RiskBreachPolicy"):
        RiskBreachFactory(policies=(object(),))  # type: ignore[arg-type]
    with pytest.raises(RiskConfigurationError, match="id_generator"):
        RiskBreachFactory(policies=(policy,), id_generator=object())  # type: ignore[arg-type]


def test_breach_policy_validates_fields() -> None:
    with pytest.raises(RiskConfigurationError, match="rule_id"):
        RiskBreachPolicy(
            rule_id="",
            scope=RiskLimitScope.GLOBAL,
            severity="critical",
            action_taken="reject_order",
        )
    with pytest.raises(TypeError, match="RiskLimitScope"):
        RiskBreachPolicy(  # type: ignore[arg-type]
            rule_id="RISK-LIMIT",
            scope="global",
            severity="critical",
            action_taken="reject_order",
        )
    with pytest.raises(RiskConfigurationError, match="severity"):
        RiskBreachPolicy(
            rule_id="RISK-LIMIT",
            scope=RiskLimitScope.GLOBAL,
            severity="",
            action_taken="reject_order",
        )
    with pytest.raises(RiskConfigurationError, match="action_taken"):
        RiskBreachPolicy(
            rule_id="RISK-LIMIT",
            scope=RiskLimitScope.GLOBAL,
            severity="critical",
            action_taken="",
        )


def test_breach_factory_rejects_non_decision_input() -> None:
    factory = RiskBreachFactory(
        policies=(
            RiskBreachPolicy(
                rule_id="RISK-LIMIT",
                scope=RiskLimitScope.GLOBAL,
                severity="critical",
                action_taken="reject_order",
            ),
        )
    )

    with pytest.raises(RiskInputError, match="RiskDecision"):
        factory.breaches_for_decision(object())  # type: ignore[arg-type]


def _decision(*, rule_results: tuple[RiskRuleResult, ...]) -> RiskDecision:
    return RiskDecision(
        risk_decision_id="risk_01k00000000000000000000000",
        intent_id="intent_risk_breach",
        status=RiskDecisionStatus.REJECTED,
        evaluated_at=NOW,
        input_snapshot_id="risk_input_01k0000000000000000",
        rule_results=rule_results,
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
        configuration_hash="sha256:config",
        correlation_id="corr_risk_breach",
    )


def _result(
    *,
    rule_id: str,
    passed: bool,
    reason_code: str | None = None,
    evaluated_at: datetime = NOW,
) -> RiskRuleResult:
    return RiskRuleResult(
        rule_id=rule_id,
        rule_version="1.0",
        passed=passed,
        reason_code=reason_code or (f"{rule_id}_PASS" if passed else f"{rule_id}_FAIL"),
        reason_text=None,
        observed_value=Decimal("1") if passed else Decimal("125"),
        limit_value=Decimal("100"),
        unit="usd",
        evaluated_at=evaluated_at,
    )
