"""RISK-008 order-notional limit rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext, RiskNotionalLimitState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_ORDER_NOTIONAL_LIMIT_RULE_ID = "RISK-008"
RISK_ORDER_NOTIONAL_LIMIT_RULE_VERSION = "1.0"
RISK_ORDER_NOTIONAL_VALID_REASON = "RISK_ORDER_NOTIONAL_VALID"
RISK_ORDER_NOTIONAL_PRICE_MISSING_REASON = "RISK_ORDER_NOTIONAL_PRICE_MISSING"
RISK_ORDER_NOTIONAL_LIMIT_MISSING_REASON = "RISK_ORDER_NOTIONAL_LIMIT_MISSING"
RISK_ORDER_NOTIONAL_LIMIT_STALE_REASON = "RISK_ORDER_NOTIONAL_LIMIT_STALE"
RISK_ORDER_NOTIONAL_LIMIT_FUTURE_REASON = "RISK_ORDER_NOTIONAL_LIMIT_FUTURE"
RISK_ORDER_NOTIONAL_ABOVE_MAX_REASON = "RISK_ORDER_NOTIONAL_ABOVE_MAX"

_NOTIONAL_UNIT = "notional"
_MILLISECONDS_UNIT = "milliseconds"
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class OrderNotionalLimitRule:
    """Reject intents with missing, stale, or exceeded notional limits."""

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

        return RISK_ORDER_NOTIONAL_LIMIT_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_ORDER_NOTIONAL_LIMIT_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether an intent's notional is within the configured cap."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("order notional limit rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("order notional limit rule requires a RiskContext")

        if intent.limit_price is None:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_NOTIONAL_PRICE_MISSING_REASON,
                observed_value=None,
                limit_value=None,
                unit=_NOTIONAL_UNIT,
                evaluated_at=context.evaluated_at,
            )

        notional = intent.quantity * intent.limit_price
        limit = context.notional_limits_state(intent.contract_id)
        if limit is None:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_NOTIONAL_LIMIT_MISSING_REASON,
                observed_value=notional,
                limit_value=None,
                unit=_NOTIONAL_UNIT,
                evaluated_at=context.evaluated_at,
            )

        limit_age_result = self._limit_age_result(limit, context)
        if limit_age_result is not None:
            return limit_age_result

        if notional > limit.max_notional:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_NOTIONAL_ABOVE_MAX_REASON,
                observed_value=notional,
                limit_value=limit.max_notional,
                unit=_NOTIONAL_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_ORDER_NOTIONAL_VALID_REASON,
            observed_value=notional,
            limit_value=limit.max_notional,
            unit=_NOTIONAL_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _limit_age_result(
        self,
        limit: RiskNotionalLimitState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if limit.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_NOTIONAL_LIMIT_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(limit.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - limit.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_NOTIONAL_LIMIT_STALE_REASON,
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
