"""RISK-014 daily-loss limit rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext, RiskDailyLossState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_DAILY_LOSS_LIMIT_RULE_ID = "RISK-014"
RISK_DAILY_LOSS_LIMIT_RULE_VERSION = "1.0"
RISK_DAILY_LOSS_VALID_REASON = "RISK_DAILY_LOSS_VALID"
RISK_DAILY_LOSS_STATE_MISSING_REASON = "RISK_DAILY_LOSS_STATE_MISSING"
RISK_DAILY_LOSS_STATE_STALE_REASON = "RISK_DAILY_LOSS_STATE_STALE"
RISK_DAILY_LOSS_STATE_FUTURE_REASON = "RISK_DAILY_LOSS_STATE_FUTURE"
RISK_DAILY_LOSS_ABOVE_MAX_REASON = "RISK_DAILY_LOSS_ABOVE_MAX"

_LOSS_UNIT = "loss"
_MILLISECONDS_UNIT = "milliseconds"
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class DailyLossLimitRule:
    """Reject intents when the current daily loss exceeds the configured cap."""

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

        return RISK_DAILY_LOSS_LIMIT_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_DAILY_LOSS_LIMIT_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether current daily PnL is within the allowed loss limit."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("daily loss limit rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("daily loss limit rule requires a RiskContext")

        state = context.daily_loss_state()
        if state is None:
            return self._result(
                passed=False,
                reason_code=RISK_DAILY_LOSS_STATE_MISSING_REASON,
                observed_value=None,
                limit_value=None,
                unit=_LOSS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        state_age_result = self._state_age_result(state, context)
        if state_age_result is not None:
            return state_age_result

        current_daily_loss = state.current_daily_loss
        if current_daily_loss > state.max_daily_loss:
            return self._result(
                passed=False,
                reason_code=RISK_DAILY_LOSS_ABOVE_MAX_REASON,
                observed_value=current_daily_loss,
                limit_value=state.max_daily_loss,
                unit=_LOSS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_DAILY_LOSS_VALID_REASON,
            observed_value=current_daily_loss,
            limit_value=state.max_daily_loss,
            unit=_LOSS_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _state_age_result(
        self,
        state: RiskDailyLossState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if state.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_DAILY_LOSS_STATE_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(state.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - state.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_DAILY_LOSS_STATE_STALE_REASON,
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
