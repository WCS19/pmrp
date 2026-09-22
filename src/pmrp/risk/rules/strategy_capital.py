"""RISK-012 strategy-capital limit rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext, RiskStrategyCapitalState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_STRATEGY_CAPITAL_LIMIT_RULE_ID = "RISK-012"
RISK_STRATEGY_CAPITAL_LIMIT_RULE_VERSION = "1.0"
RISK_STRATEGY_CAPITAL_VALID_REASON = "RISK_STRATEGY_CAPITAL_VALID"
RISK_STRATEGY_CAPITAL_PRICE_MISSING_REASON = "RISK_STRATEGY_CAPITAL_PRICE_MISSING"
RISK_STRATEGY_CAPITAL_STATE_MISSING_REASON = "RISK_STRATEGY_CAPITAL_STATE_MISSING"
RISK_STRATEGY_CAPITAL_STATE_STALE_REASON = "RISK_STRATEGY_CAPITAL_STATE_STALE"
RISK_STRATEGY_CAPITAL_STATE_FUTURE_REASON = "RISK_STRATEGY_CAPITAL_STATE_FUTURE"
RISK_STRATEGY_CAPITAL_ABOVE_MAX_REASON = "RISK_STRATEGY_CAPITAL_ABOVE_MAX"

_CAPITAL_UNIT = "capital"
_MILLISECONDS_UNIT = "milliseconds"
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class StrategyCapitalLimitRule:
    """Reject intents that would exceed a strategy's capital allocation."""

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

        return RISK_STRATEGY_CAPITAL_LIMIT_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_STRATEGY_CAPITAL_LIMIT_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether an intent keeps strategy capital within limits."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("strategy capital limit rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("strategy capital limit rule requires a RiskContext")

        if intent.limit_price is None:
            return self._result(
                passed=False,
                reason_code=RISK_STRATEGY_CAPITAL_PRICE_MISSING_REASON,
                observed_value=None,
                limit_value=None,
                unit=_CAPITAL_UNIT,
                evaluated_at=context.evaluated_at,
            )

        intent_capital = intent.quantity * intent.limit_price
        state = context.strategy_capital_state(intent.strategy_id)
        if state is None:
            return self._result(
                passed=False,
                reason_code=RISK_STRATEGY_CAPITAL_STATE_MISSING_REASON,
                observed_value=intent_capital,
                limit_value=None,
                unit=_CAPITAL_UNIT,
                evaluated_at=context.evaluated_at,
            )

        state_age_result = self._state_age_result(state, context)
        if state_age_result is not None:
            return state_age_result

        projected_capital = state.effective_capital_used + intent_capital
        if projected_capital > state.max_strategy_capital:
            return self._result(
                passed=False,
                reason_code=RISK_STRATEGY_CAPITAL_ABOVE_MAX_REASON,
                observed_value=projected_capital,
                limit_value=state.max_strategy_capital,
                unit=_CAPITAL_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_STRATEGY_CAPITAL_VALID_REASON,
            observed_value=projected_capital,
            limit_value=state.max_strategy_capital,
            unit=_CAPITAL_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _state_age_result(
        self,
        state: RiskStrategyCapitalState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if state.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_STRATEGY_CAPITAL_STATE_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(state.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - state.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_STRATEGY_CAPITAL_STATE_STALE_REASON,
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
