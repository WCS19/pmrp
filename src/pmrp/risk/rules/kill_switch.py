"""RISK-019 kill-switch clear rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext, RiskKillSwitchClearState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_KILL_SWITCH_CLEAR_RULE_ID = "RISK-019"
RISK_KILL_SWITCH_CLEAR_RULE_VERSION = "1.0"
RISK_KILL_SWITCH_CLEAR_REASON = "RISK_KILL_SWITCH_CLEAR"
RISK_KILL_SWITCH_STATE_MISSING_REASON = "RISK_KILL_SWITCH_STATE_MISSING"
RISK_KILL_SWITCH_STATE_STALE_REASON = "RISK_KILL_SWITCH_STATE_STALE"
RISK_KILL_SWITCH_STATE_FUTURE_REASON = "RISK_KILL_SWITCH_STATE_FUTURE"
RISK_KILL_SWITCH_ACTIVE_REASON = "RISK_KILL_SWITCH_ACTIVE"
RISK_KILL_SWITCH_NOT_CLEAR_REASON = "RISK_KILL_SWITCH_NOT_CLEAR"

_CLEAR_FLAG_UNIT = "clear_flag"
_ACTIVE_SCOPE_UNIT = "active_scope_count"
_MILLISECONDS_UNIT = "milliseconds"
_ONE = Decimal("1")
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class KillSwitchClearRule:
    """Reject intents when an applicable kill switch blocks trading."""

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

        return RISK_KILL_SWITCH_CLEAR_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_KILL_SWITCH_CLEAR_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether applicable kill-switch state permits new trading activity."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("kill-switch clear rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("kill-switch clear rule requires a RiskContext")

        state = context.kill_switch_clear_state()
        if state is None:
            return self._result(
                passed=False,
                reason_code=RISK_KILL_SWITCH_STATE_MISSING_REASON,
                observed_value=None,
                limit_value=_ONE,
                unit=_CLEAR_FLAG_UNIT,
                evaluated_at=context.evaluated_at,
            )

        state_age_result = self._state_age_result(state, context)
        if state_age_result is not None:
            return state_age_result

        if state.active_scopes:
            return self._result(
                passed=False,
                reason_code=RISK_KILL_SWITCH_ACTIVE_REASON,
                observed_value=Decimal(len(state.active_scopes)),
                limit_value=_ZERO,
                unit=_ACTIVE_SCOPE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if not state.clear:
            return self._result(
                passed=False,
                reason_code=RISK_KILL_SWITCH_NOT_CLEAR_REASON,
                observed_value=_ZERO,
                limit_value=_ONE,
                unit=_CLEAR_FLAG_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_KILL_SWITCH_CLEAR_REASON,
            observed_value=_ONE,
            limit_value=_ONE,
            unit=_CLEAR_FLAG_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _state_age_result(
        self,
        state: RiskKillSwitchClearState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if state.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_KILL_SWITCH_STATE_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(state.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - state.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_KILL_SWITCH_STATE_STALE_REASON,
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
