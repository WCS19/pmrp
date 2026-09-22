"""Central deterministic risk decision engine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from pmrp.risk.context import RiskContext
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.risk.rules import RiskRule
from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.identifiers import RiskDecisionId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskDecision, RiskRuleResult
from pmrp.schemas.serialization import canonical_sha256

RISK_ENGINE_RULE_ERROR_REASON = "RISK_ENGINE_RULE_ERROR"
RISK_ENGINE_RULE_RESULT_INVALID_REASON = "RISK_ENGINE_RULE_RESULT_INVALID"
RISK_ENGINE_APPROVAL_LIMIT_PRICE_MISSING_REASON = "RISK_ENGINE_APPROVAL_LIMIT_PRICE_MISSING"
RISK_ENGINE_RULE_ID = "RISK-ENGINE"
RISK_ENGINE_RULE_VERSION = "1.0"
_MAX_SNAPSHOT_ID_LENGTH = 128
_HASH_PREFIX_LENGTH = 32


class RiskDecisionIdGenerator(Protocol):
    """Generate risk decision identifiers from evaluated decision content."""

    def risk_decision_id(
        self,
        *,
        intent: OrderIntent,
        evaluated_at: datetime,
        input_snapshot_id: str,
        configuration_hash: str,
        rule_results: tuple[RiskRuleResult, ...],
    ) -> RiskDecisionId:
        """Return a canonical risk decision identifier."""
        ...


@dataclass(frozen=True, slots=True)
class HashingRiskDecisionIdGenerator:
    """Generate deterministic risk decision identifiers from canonical content."""

    def risk_decision_id(
        self,
        *,
        intent: OrderIntent,
        evaluated_at: datetime,
        input_snapshot_id: str,
        configuration_hash: str,
        rule_results: tuple[RiskRuleResult, ...],
    ) -> RiskDecisionId:
        payload = {
            "configuration_hash": configuration_hash,
            "evaluated_at": evaluated_at,
            "input_snapshot_id": input_snapshot_id,
            "intent_id": intent.intent_id,
            "rule_results": rule_results,
        }
        digest = canonical_sha256(payload).removeprefix("sha256:")
        return RiskDecisionId(f"{RiskDecisionId.prefix}{digest[:_HASH_PREFIX_LENGTH]}")


@dataclass(frozen=True, slots=True)
class RiskEngine:
    """Evaluate a configured set of risk rules into one canonical decision."""

    rules: Sequence[RiskRule]
    configuration_hash: str | None = None
    approval_ttl: timedelta | None = None
    decision_id_generator: RiskDecisionIdGenerator = field(
        default_factory=HashingRiskDecisionIdGenerator
    )

    def __post_init__(self) -> None:
        frozen_rules = _freeze_rules(self.rules)
        object.__setattr__(self, "rules", frozen_rules)
        if self.configuration_hash is None:
            object.__setattr__(self, "configuration_hash", _configuration_hash(frozen_rules))
        elif type(self.configuration_hash) is not str:
            msg = "configuration_hash must be a string"
            raise TypeError(msg)
        elif self.configuration_hash == "":
            raise RiskConfigurationError("configuration_hash must not be empty")

        if self.approval_ttl is not None and not isinstance(self.approval_ttl, timedelta):
            msg = "approval_ttl must be a timedelta"
            raise TypeError(msg)
        if self.approval_ttl is not None and self.approval_ttl <= timedelta(0):
            raise RiskConfigurationError("approval_ttl must be positive")
        if not hasattr(self.decision_id_generator, "risk_decision_id"):
            raise RiskConfigurationError("decision_id_generator must implement risk_decision_id")

    async def evaluate(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        input_snapshot_id: str,
    ) -> RiskDecision:
        """Evaluate all configured rules and return a canonical risk decision."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("risk engine requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("risk engine requires a RiskContext")
        _validate_input_snapshot_id(input_snapshot_id)

        rule_results = await self._evaluate_rules(intent, context)
        status = _decision_status(rule_results)
        if status is RiskDecisionStatus.APPROVED and intent.limit_price is None:
            rule_results = (
                *rule_results,
                _engine_result(
                    context=context,
                    reason_code=RISK_ENGINE_APPROVAL_LIMIT_PRICE_MISSING_REASON,
                    reason_text="approved decision requires intent limit_price",
                ),
            )
            status = RiskDecisionStatus.REJECTED

        configuration_hash = self.configuration_hash
        if configuration_hash is None:
            raise RiskConfigurationError("configuration_hash must be configured")

        approval_expires_at = (
            context.evaluated_at + self.approval_ttl
            if status is RiskDecisionStatus.APPROVED and self.approval_ttl is not None
            else None
        )
        risk_decision_id = self.decision_id_generator.risk_decision_id(
            intent=intent,
            evaluated_at=context.evaluated_at,
            input_snapshot_id=input_snapshot_id,
            configuration_hash=configuration_hash,
            rule_results=rule_results,
        )

        return RiskDecision(
            risk_decision_id=risk_decision_id,
            intent_id=intent.intent_id,
            status=status,
            evaluated_at=context.evaluated_at,
            input_snapshot_id=input_snapshot_id,
            rule_results=rule_results,
            approved_quantity=intent.quantity if status is RiskDecisionStatus.APPROVED else None,
            approved_limit_price=(
                intent.limit_price if status is RiskDecisionStatus.APPROVED else None
            ),
            approval_expires_at=approval_expires_at,
            configuration_hash=configuration_hash,
            correlation_id=intent.correlation_id,
        )

    async def _evaluate_rules(
        self,
        intent: OrderIntent,
        context: RiskContext,
    ) -> tuple[RiskRuleResult, ...]:
        results: list[RiskRuleResult] = []
        for rule in self.rules:
            rule_id, rule_version = _rule_identity(rule)
            try:
                result = await rule.evaluate(intent, context)
            except Exception as exc:
                results.append(
                    _rule_error_result(
                        rule_id=rule_id,
                        rule_version=rule_version,
                        context=context,
                        reason_code=RISK_ENGINE_RULE_ERROR_REASON,
                        reason_text=f"rule evaluation raised {type(exc).__name__}",
                    )
                )
                break
            if not isinstance(result, RiskRuleResult):
                results.append(
                    _rule_error_result(
                        rule_id=rule_id,
                        rule_version=rule_version,
                        context=context,
                        reason_code=RISK_ENGINE_RULE_RESULT_INVALID_REASON,
                        reason_text="rule returned non-RiskRuleResult",
                    )
                )
                break
            results.append(result)
        return tuple(results)


def _freeze_rules(rules: Sequence[RiskRule]) -> tuple[RiskRule, ...]:
    if isinstance(rules, (str, bytes)) or not isinstance(rules, Sequence):
        msg = "rules must be a sequence"
        raise TypeError(msg)
    frozen = tuple(rules)
    if not frozen:
        raise RiskConfigurationError("risk engine requires at least one rule")
    seen: set[tuple[str, str]] = set()
    for rule in frozen:
        rule_id, rule_version = _rule_identity(rule)
        if not callable(getattr(rule, "evaluate", None)):
            raise RiskConfigurationError("risk rules must implement evaluate")
        key = (rule_id, rule_version)
        if key in seen:
            raise RiskConfigurationError("risk rule identifiers must be unique by version")
        seen.add(key)
    return frozen


def _rule_identity(rule: RiskRule) -> tuple[str, str]:
    rule_id = getattr(rule, "rule_id", None)
    rule_version = getattr(rule, "version", None)
    if type(rule_id) is not str or rule_id == "":
        raise RiskConfigurationError("risk rules must expose a nonempty rule_id")
    if type(rule_version) is not str or rule_version == "":
        raise RiskConfigurationError("risk rules must expose a nonempty version")
    return rule_id, rule_version


def _configuration_hash(rules: tuple[RiskRule, ...]) -> str:
    return canonical_sha256(
        tuple(
            {
                "rule_id": rule_id,
                "rule_version": rule_version,
            }
            for rule_id, rule_version in (_rule_identity(rule) for rule in rules)
        )
    )


def _validate_input_snapshot_id(input_snapshot_id: str) -> None:
    if type(input_snapshot_id) is not str:
        msg = "input_snapshot_id must be a string"
        raise TypeError(msg)
    if input_snapshot_id == "":
        raise RiskInputError("input_snapshot_id must not be empty")
    if len(input_snapshot_id) > _MAX_SNAPSHOT_ID_LENGTH:
        raise RiskInputError("input_snapshot_id must be at most 128 characters")


def _decision_status(rule_results: tuple[RiskRuleResult, ...]) -> RiskDecisionStatus:
    for result in rule_results:
        if not result.passed and result.reason_code in {
            RISK_ENGINE_RULE_ERROR_REASON,
            RISK_ENGINE_RULE_RESULT_INVALID_REASON,
        }:
            return RiskDecisionStatus.ERROR
    if all(result.passed for result in rule_results):
        return RiskDecisionStatus.APPROVED
    return RiskDecisionStatus.REJECTED


def _rule_error_result(
    *,
    rule_id: str,
    rule_version: str,
    context: RiskContext,
    reason_code: str,
    reason_text: str,
) -> RiskRuleResult:
    return RiskRuleResult(
        rule_id=rule_id,
        rule_version=rule_version,
        passed=False,
        reason_code=reason_code,
        reason_text=reason_text,
        observed_value=None,
        limit_value=None,
        unit=None,
        evaluated_at=context.evaluated_at,
    )


def _engine_result(
    *,
    context: RiskContext,
    reason_code: str,
    reason_text: str,
) -> RiskRuleResult:
    return _rule_error_result(
        rule_id=RISK_ENGINE_RULE_ID,
        rule_version=RISK_ENGINE_RULE_VERSION,
        context=context,
        reason_code=reason_code,
        reason_text=reason_text,
    )
