"""RISK-011 portfolio net-exposure limit rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext, RiskPortfolioNetExposureState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.enums import Side
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_PORTFOLIO_NET_LIMIT_RULE_ID = "RISK-011"
RISK_PORTFOLIO_NET_LIMIT_RULE_VERSION = "1.0"
RISK_PORTFOLIO_NET_VALID_REASON = "RISK_PORTFOLIO_NET_VALID"
RISK_PORTFOLIO_NET_PRICE_MISSING_REASON = "RISK_PORTFOLIO_NET_PRICE_MISSING"
RISK_PORTFOLIO_NET_STATE_MISSING_REASON = "RISK_PORTFOLIO_NET_STATE_MISSING"
RISK_PORTFOLIO_NET_STATE_STALE_REASON = "RISK_PORTFOLIO_NET_STATE_STALE"
RISK_PORTFOLIO_NET_STATE_FUTURE_REASON = "RISK_PORTFOLIO_NET_STATE_FUTURE"
RISK_PORTFOLIO_NET_ABOVE_MAX_REASON = "RISK_PORTFOLIO_NET_ABOVE_MAX"

_NET_EXPOSURE_UNIT = "net_exposure"
_MILLISECONDS_UNIT = "milliseconds"
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class PortfolioNetLimitRule:
    """Reject intents that would exceed the portfolio absolute net-exposure cap."""

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

        return RISK_PORTFOLIO_NET_LIMIT_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_PORTFOLIO_NET_LIMIT_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether an intent keeps portfolio net exposure within limits."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("portfolio net limit rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("portfolio net limit rule requires a RiskContext")

        if intent.limit_price is None:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_NET_PRICE_MISSING_REASON,
                observed_value=None,
                limit_value=None,
                unit=_NET_EXPOSURE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        intent_net_exposure = _signed_notional(intent.quantity, intent.limit_price, intent.side)
        state = context.portfolio_net_exposure_state()
        if state is None:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_NET_STATE_MISSING_REASON,
                observed_value=abs(intent_net_exposure),
                limit_value=None,
                unit=_NET_EXPOSURE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        state_age_result = self._state_age_result(state, context)
        if state_age_result is not None:
            return state_age_result

        projected_net_exposure = state.effective_net_exposure + intent_net_exposure
        observed_net_exposure = abs(projected_net_exposure)
        if observed_net_exposure > state.max_net_exposure:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_NET_ABOVE_MAX_REASON,
                observed_value=observed_net_exposure,
                limit_value=state.max_net_exposure,
                unit=_NET_EXPOSURE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_PORTFOLIO_NET_VALID_REASON,
            observed_value=observed_net_exposure,
            limit_value=state.max_net_exposure,
            unit=_NET_EXPOSURE_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _state_age_result(
        self,
        state: RiskPortfolioNetExposureState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if state.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_NET_STATE_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(state.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - state.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_PORTFOLIO_NET_STATE_STALE_REASON,
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


def _signed_notional(quantity: Decimal, limit_price: Decimal, side: Side) -> Decimal:
    notional = quantity * limit_price
    if side is Side.BUY:
        return notional
    return -notional


def _timedelta_milliseconds(value: timedelta) -> Decimal:
    total_microseconds = (
        value.days * _SECONDS_PER_DAY + value.seconds
    ) * 1_000_000 + value.microseconds
    return Decimal(total_microseconds) / _MICROSECONDS_PER_MILLISECOND
