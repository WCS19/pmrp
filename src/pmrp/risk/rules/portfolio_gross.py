"""RISK-010 portfolio gross-exposure limit rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext, RiskPortfolioGrossExposureState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_PORTFOLIO_GROSS_LIMIT_RULE_ID = "RISK-010"
RISK_PORTFOLIO_GROSS_LIMIT_RULE_VERSION = "1.0"
RISK_PORTFOLIO_GROSS_VALID_REASON = "RISK_PORTFOLIO_GROSS_VALID"
RISK_PORTFOLIO_GROSS_PRICE_MISSING_REASON = "RISK_PORTFOLIO_GROSS_PRICE_MISSING"
RISK_PORTFOLIO_GROSS_STATE_MISSING_REASON = "RISK_PORTFOLIO_GROSS_STATE_MISSING"
RISK_PORTFOLIO_GROSS_STATE_STALE_REASON = "RISK_PORTFOLIO_GROSS_STATE_STALE"
RISK_PORTFOLIO_GROSS_STATE_FUTURE_REASON = "RISK_PORTFOLIO_GROSS_STATE_FUTURE"
RISK_PORTFOLIO_GROSS_ABOVE_MAX_REASON = "RISK_PORTFOLIO_GROSS_ABOVE_MAX"

_GROSS_EXPOSURE_UNIT = "gross_exposure"
_MILLISECONDS_UNIT = "milliseconds"
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class PortfolioGrossLimitRule:
    """Reject intents that would exceed the portfolio gross-exposure cap."""

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

        return RISK_PORTFOLIO_GROSS_LIMIT_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_PORTFOLIO_GROSS_LIMIT_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether an intent keeps portfolio gross exposure within limits."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("portfolio gross limit rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("portfolio gross limit rule requires a RiskContext")

        if intent.limit_price is None:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_GROSS_PRICE_MISSING_REASON,
                observed_value=None,
                limit_value=None,
                unit=_GROSS_EXPOSURE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        intent_exposure = intent.quantity * intent.limit_price
        state = context.portfolio_gross_exposure_state()
        if state is None:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_GROSS_STATE_MISSING_REASON,
                observed_value=intent_exposure,
                limit_value=None,
                unit=_GROSS_EXPOSURE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        state_age_result = self._state_age_result(state, context)
        if state_age_result is not None:
            return state_age_result

        projected_exposure = state.effective_gross_exposure + intent_exposure
        if projected_exposure > state.max_gross_exposure:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_GROSS_ABOVE_MAX_REASON,
                observed_value=projected_exposure,
                limit_value=state.max_gross_exposure,
                unit=_GROSS_EXPOSURE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_PORTFOLIO_GROSS_VALID_REASON,
            observed_value=projected_exposure,
            limit_value=state.max_gross_exposure,
            unit=_GROSS_EXPOSURE_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _state_age_result(
        self,
        state: RiskPortfolioGrossExposureState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if state.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_GROSS_STATE_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(state.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - state.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_GROSS_STATE_STALE_REASON,
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
