"""RISK-017 available-balance rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskAvailableBalanceState, RiskContext
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_AVAILABLE_BALANCE_RULE_ID = "RISK-017"
RISK_AVAILABLE_BALANCE_RULE_VERSION = "1.0"
RISK_AVAILABLE_BALANCE_VALID_REASON = "RISK_AVAILABLE_BALANCE_VALID"
RISK_AVAILABLE_BALANCE_PRICE_MISSING_REASON = "RISK_AVAILABLE_BALANCE_PRICE_MISSING"
RISK_AVAILABLE_BALANCE_STATE_MISSING_REASON = "RISK_AVAILABLE_BALANCE_STATE_MISSING"
RISK_AVAILABLE_BALANCE_STATE_STALE_REASON = "RISK_AVAILABLE_BALANCE_STATE_STALE"
RISK_AVAILABLE_BALANCE_STATE_FUTURE_REASON = "RISK_AVAILABLE_BALANCE_STATE_FUTURE"
RISK_AVAILABLE_BALANCE_INSUFFICIENT_REASON = "RISK_AVAILABLE_BALANCE_INSUFFICIENT"

_BALANCE_UNIT = "balance"
_MILLISECONDS_UNIT = "milliseconds"
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class AvailableBalanceRule:
    """Reject intents that require more cash than the effective available balance."""

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

        return RISK_AVAILABLE_BALANCE_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_AVAILABLE_BALANCE_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether an intent has enough effective available balance."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("available-balance rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("available-balance rule requires a RiskContext")

        if intent.limit_price is None:
            return self._result(
                passed=False,
                reason_code=RISK_AVAILABLE_BALANCE_PRICE_MISSING_REASON,
                observed_value=None,
                limit_value=None,
                unit=_BALANCE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        required_balance = intent.quantity * intent.limit_price
        state = context.available_balance_state()
        if state is None:
            return self._result(
                passed=False,
                reason_code=RISK_AVAILABLE_BALANCE_STATE_MISSING_REASON,
                observed_value=required_balance,
                limit_value=None,
                unit=_BALANCE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        state_age_result = self._state_age_result(state, context)
        if state_age_result is not None:
            return state_age_result

        effective_available_balance = state.effective_available_balance
        if required_balance > effective_available_balance:
            return self._result(
                passed=False,
                reason_code=RISK_AVAILABLE_BALANCE_INSUFFICIENT_REASON,
                observed_value=required_balance,
                limit_value=effective_available_balance,
                unit=_BALANCE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_AVAILABLE_BALANCE_VALID_REASON,
            observed_value=required_balance,
            limit_value=effective_available_balance,
            unit=_BALANCE_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _state_age_result(
        self,
        state: RiskAvailableBalanceState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if state.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_AVAILABLE_BALANCE_STATE_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(state.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - state.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_AVAILABLE_BALANCE_STATE_STALE_REASON,
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
