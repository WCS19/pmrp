"""RISK-018 reconciliation-health rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext, RiskReconciliationHealthState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.portfolio import ReconciliationStatus
from pmrp.schemas.risk import RiskRuleResult

RISK_RECONCILIATION_HEALTH_RULE_ID = "RISK-018"
RISK_RECONCILIATION_HEALTH_RULE_VERSION = "1.0"
RISK_RECONCILIATION_HEALTHY_REASON = "RISK_RECONCILIATION_HEALTHY"
RISK_RECONCILIATION_HEALTH_STATE_MISSING_REASON = "RISK_RECONCILIATION_HEALTH_STATE_MISSING"
RISK_RECONCILIATION_HEALTH_STATE_STALE_REASON = "RISK_RECONCILIATION_HEALTH_STATE_STALE"
RISK_RECONCILIATION_HEALTH_STATE_FUTURE_REASON = "RISK_RECONCILIATION_HEALTH_STATE_FUTURE"
RISK_RECONCILIATION_UNHEALTHY_STATUS_REASON = "RISK_RECONCILIATION_UNHEALTHY_STATUS"
RISK_RECONCILIATION_GATE_HELD_REASON = "RISK_RECONCILIATION_GATE_HELD"
RISK_RECONCILIATION_MANUAL_REVIEW_REQUIRED_REASON = "RISK_RECONCILIATION_MANUAL_REVIEW_REQUIRED"
RISK_RECONCILIATION_MISMATCHES_PRESENT_REASON = "RISK_RECONCILIATION_MISMATCHES_PRESENT"

_HEALTHY_FLAG_UNIT = "healthy_flag"
_MILLISECONDS_UNIT = "milliseconds"
_MANUAL_REVIEW_UNIT = "manual_review_count"
_MISMATCH_UNIT = "mismatch_count"
_ONE = Decimal("1")
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class ReconciliationHealthRule:
    """Reject intents when reconciliation state does not release trading."""

    max_state_age: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.max_state_age, timedelta):
            msg = "max_state_age must be a timedelta"
            raise TypeError(msg)
        if self.max_state_age <= timedelta(0):
            raise RiskConfigurationError("max_state_age must be positive")

    @property
    def rule_id(self) -> str:
        """Return the stable risk rule identifier."""

        return RISK_RECONCILIATION_HEALTH_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_RECONCILIATION_HEALTH_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether reconciliation health permits new trading activity."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("reconciliation health rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("reconciliation health rule requires a RiskContext")

        state = context.reconciliation_health_state()
        if state is None:
            return self._result(
                passed=False,
                reason_code=RISK_RECONCILIATION_HEALTH_STATE_MISSING_REASON,
                observed_value=None,
                limit_value=_ONE,
                unit=_HEALTHY_FLAG_UNIT,
                evaluated_at=context.evaluated_at,
            )

        state_age_result = self._state_age_result(state, context)
        if state_age_result is not None:
            return state_age_result

        if state.status is not ReconciliationStatus.HEALTHY:
            return self._result(
                passed=False,
                reason_code=RISK_RECONCILIATION_UNHEALTHY_STATUS_REASON,
                observed_value=_ZERO,
                limit_value=_ONE,
                unit=_HEALTHY_FLAG_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if not state.trading_gate_released:
            return self._result(
                passed=False,
                reason_code=RISK_RECONCILIATION_GATE_HELD_REASON,
                observed_value=_ZERO,
                limit_value=_ONE,
                unit=_HEALTHY_FLAG_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if state.manual_review_count > 0:
            return self._result(
                passed=False,
                reason_code=RISK_RECONCILIATION_MANUAL_REVIEW_REQUIRED_REASON,
                observed_value=Decimal(state.manual_review_count),
                limit_value=_ZERO,
                unit=_MANUAL_REVIEW_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if state.unresolved_mismatch_count > 0:
            return self._result(
                passed=False,
                reason_code=RISK_RECONCILIATION_MISMATCHES_PRESENT_REASON,
                observed_value=Decimal(state.unresolved_mismatch_count),
                limit_value=_ZERO,
                unit=_MISMATCH_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_RECONCILIATION_HEALTHY_REASON,
            observed_value=_ONE,
            limit_value=_ONE,
            unit=_HEALTHY_FLAG_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _state_age_result(
        self,
        state: RiskReconciliationHealthState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if state.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_RECONCILIATION_HEALTH_STATE_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(state.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - state.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_RECONCILIATION_HEALTH_STATE_STALE_REASON,
                observed_value=_timedelta_milliseconds(age),
                limit_value=_timedelta_milliseconds(self.max_state_age),
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )
        return None

    def _result(
        self,
        *,
        passed: bool,
        reason_code: str,
        observed_value: Decimal | None,
        limit_value: Decimal | None,
        unit: str,
        evaluated_at: datetime,
    ) -> RiskRuleResult:
        return RiskRuleResult(
            rule_id=self.rule_id,
            rule_version=self.version,
            passed=passed,
            reason_code=reason_code,
            reason_text=None,
            observed_value=observed_value,
            limit_value=limit_value,
            unit=unit,
            evaluated_at=evaluated_at,
        )


def _timedelta_milliseconds(value: timedelta) -> Decimal:
    total_microseconds = (
        value.days * _SECONDS_PER_DAY + value.seconds
    ) * 1_000_000 + value.microseconds
    return Decimal(total_microseconds) / _MICROSECONDS_PER_MILLISECOND
