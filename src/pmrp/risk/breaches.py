"""Deterministic derivation of canonical risk breach records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.risk import RiskBreach, RiskDecision, RiskLimitScope, RiskRuleResult
from pmrp.schemas.serialization import canonical_sha256

_RISK_ID_MAX_LENGTH = 128
_SCOPE_ID_MAX_LENGTH = 256
_SEVERITY_MAX_LENGTH = 64
_HASH_PREFIX_LENGTH = 32


class RiskBreachIdGenerator(Protocol):
    """Generate durable breach IDs from deterministic breach inputs."""

    def breach_id(
        self,
        *,
        decision: RiskDecision,
        result: RiskRuleResult,
        result_index: int,
        policy: RiskBreachPolicy,
    ) -> str:
        """Return a canonical risk breach identifier."""
        ...


@dataclass(frozen=True, slots=True)
class HashingRiskBreachIdGenerator:
    """Generate stable breach IDs from decision, rule result, and policy content."""

    def breach_id(
        self,
        *,
        decision: RiskDecision,
        result: RiskRuleResult,
        result_index: int,
        policy: RiskBreachPolicy,
    ) -> str:
        payload = {
            "action_taken": policy.action_taken,
            "intent_id": str(decision.intent_id),
            "reason_code": result.reason_code,
            "result_index": result_index,
            "risk_decision_id": str(decision.risk_decision_id),
            "rule_id": result.rule_id,
            "rule_version": result.rule_version,
            "scope": policy.scope.value,
            "scope_id": policy.scope_id,
            "severity": policy.severity,
        }
        digest = canonical_sha256(payload).removeprefix("sha256:")
        return f"breach_{digest[:_HASH_PREFIX_LENGTH]}"


@dataclass(frozen=True, slots=True)
class RiskBreachPolicy:
    """Configuration mapping a failed risk result to breach metadata."""

    rule_id: str
    scope: RiskLimitScope
    severity: str
    action_taken: str
    scope_id: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        _validate_text(self.rule_id, field_name="rule_id", max_length=_RISK_ID_MAX_LENGTH)
        if not isinstance(self.scope, RiskLimitScope):
            msg = "risk breach policy scope must be a RiskLimitScope"
            raise TypeError(msg)
        _validate_text(self.severity, field_name="severity", max_length=_SEVERITY_MAX_LENGTH)
        _validate_text(
            self.action_taken,
            field_name="action_taken",
            max_length=_RISK_ID_MAX_LENGTH,
        )
        if self.scope_id is not None:
            _validate_text(self.scope_id, field_name="scope_id", max_length=_SCOPE_ID_MAX_LENGTH)
        if self.reason_code is not None:
            _validate_text(
                self.reason_code,
                field_name="reason_code",
                max_length=_RISK_ID_MAX_LENGTH,
            )

    @property
    def key(self) -> tuple[str, str | None]:
        """Return the unique rule/reason matching key."""

        return (self.rule_id, self.reason_code)


@dataclass(frozen=True, slots=True)
class RiskBreachFactory:
    """Derive canonical breaches from failed risk rule results."""

    policies: Sequence[RiskBreachPolicy]
    id_generator: RiskBreachIdGenerator = field(default_factory=HashingRiskBreachIdGenerator)

    def __post_init__(self) -> None:
        policies = _freeze_policies(self.policies)
        object.__setattr__(self, "policies", policies)
        if not hasattr(self.id_generator, "breach_id"):
            raise RiskConfigurationError("id_generator must implement breach_id")

    def breaches_for_decision(self, decision: RiskDecision) -> tuple[RiskBreach, ...]:
        """Return deterministic breaches for configured failed rule results."""

        if not isinstance(decision, RiskDecision):
            raise RiskInputError("risk breach factory requires a RiskDecision")

        breaches: list[RiskBreach] = []
        for result_index, result in enumerate(decision.rule_results):
            if result.passed:
                continue
            policy = _policy_for_result(self.policies, result)
            if policy is None:
                continue
            breach_id = self.id_generator.breach_id(
                decision=decision,
                result=result,
                result_index=result_index,
                policy=policy,
            )
            breaches.append(
                RiskBreach(
                    breach_id=breach_id,
                    rule_id=result.rule_id,
                    rule_version=result.rule_version,
                    scope=policy.scope,
                    scope_id=policy.scope_id,
                    severity=policy.severity,
                    detected_at=result.evaluated_at,
                    observed_value=result.observed_value,
                    limit_value=result.limit_value,
                    unit=result.unit,
                    action_taken=policy.action_taken,
                    correlation_id=decision.correlation_id,
                )
            )
        return tuple(breaches)


def _freeze_policies(policies: Sequence[RiskBreachPolicy]) -> tuple[RiskBreachPolicy, ...]:
    if isinstance(policies, (str, bytes)) or not isinstance(policies, Sequence):
        msg = "risk breach policies must be a sequence"
        raise TypeError(msg)
    frozen = tuple(policies)
    if not frozen:
        raise RiskConfigurationError("risk breach factory requires at least one policy")

    seen: set[tuple[str, str | None]] = set()
    for policy in frozen:
        if not isinstance(policy, RiskBreachPolicy):
            msg = "risk breach policies must be RiskBreachPolicy instances"
            raise TypeError(msg)
        if policy.key in seen:
            raise RiskConfigurationError("risk breach policy keys must be unique")
        seen.add(policy.key)
    return frozen


def _policy_for_result(
    policies: Sequence[RiskBreachPolicy],
    result: RiskRuleResult,
) -> RiskBreachPolicy | None:
    reason_match: RiskBreachPolicy | None = None
    rule_match: RiskBreachPolicy | None = None
    for policy in policies:
        if policy.rule_id != result.rule_id:
            continue
        if policy.reason_code == result.reason_code:
            reason_match = policy
        elif policy.reason_code is None:
            rule_match = policy
    return reason_match or rule_match


def _validate_text(value: str, *, field_name: str, max_length: int) -> None:
    if type(value) is not str:
        msg = f"risk breach policy {field_name} must be a string"
        raise TypeError(msg)
    if value == "":
        raise RiskConfigurationError(f"risk breach policy {field_name} must not be empty")
    if len(value) > max_length:
        raise RiskConfigurationError(
            f"risk breach policy {field_name} must be at most {max_length} characters"
        )
