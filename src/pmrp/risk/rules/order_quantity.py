"""RISK-007 order-quantity limit rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext, RiskQuantityLimitsState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_ORDER_QUANTITY_LIMIT_RULE_ID = "RISK-007"
RISK_ORDER_QUANTITY_LIMIT_RULE_VERSION = "1.0"
RISK_ORDER_QUANTITY_VALID_REASON = "RISK_ORDER_QUANTITY_VALID"
RISK_ORDER_QUANTITY_LIMITS_MISSING_REASON = "RISK_ORDER_QUANTITY_LIMITS_MISSING"
RISK_ORDER_QUANTITY_LIMITS_STALE_REASON = "RISK_ORDER_QUANTITY_LIMITS_STALE"
RISK_ORDER_QUANTITY_LIMITS_FUTURE_REASON = "RISK_ORDER_QUANTITY_LIMITS_FUTURE"
RISK_ORDER_QUANTITY_BELOW_MIN_REASON = "RISK_ORDER_QUANTITY_BELOW_MIN"
RISK_ORDER_QUANTITY_ABOVE_MAX_REASON = "RISK_ORDER_QUANTITY_ABOVE_MAX"
RISK_ORDER_QUANTITY_OFF_INCREMENT_REASON = "RISK_ORDER_QUANTITY_OFF_INCREMENT"

_QUANTITY_UNIT = "quantity"
_MIN_QUANTITY_UNIT = "min_quantity"
_MAX_QUANTITY_UNIT = "max_quantity"
_QUANTITY_INCREMENT_UNIT = "quantity_increment"
_MILLISECONDS_UNIT = "milliseconds"
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class OrderQuantityLimitRule:
    """Reject intents with missing, stale, out-of-bounds, or off-increment quantities."""

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

        return RISK_ORDER_QUANTITY_LIMIT_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_ORDER_QUANTITY_LIMIT_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether an intent's quantity is valid for the target contract."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("order quantity limit rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("order quantity limit rule requires a RiskContext")

        limits = context.quantity_limits_state(intent.contract_id)
        if limits is None:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_QUANTITY_LIMITS_MISSING_REASON,
                observed_value=intent.quantity,
                limit_value=None,
                unit=_QUANTITY_UNIT,
                evaluated_at=context.evaluated_at,
            )

        limits_age_result = self._limits_age_result(limits, context)
        if limits_age_result is not None:
            return limits_age_result

        if intent.quantity < limits.min_quantity:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_QUANTITY_BELOW_MIN_REASON,
                observed_value=intent.quantity,
                limit_value=limits.min_quantity,
                unit=_MIN_QUANTITY_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if intent.quantity > limits.max_quantity:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_QUANTITY_ABOVE_MAX_REASON,
                observed_value=intent.quantity,
                limit_value=limits.max_quantity,
                unit=_MAX_QUANTITY_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if (intent.quantity - limits.min_quantity) % limits.quantity_increment != _ZERO:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_QUANTITY_OFF_INCREMENT_REASON,
                observed_value=intent.quantity,
                limit_value=limits.quantity_increment,
                unit=_QUANTITY_INCREMENT_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_ORDER_QUANTITY_VALID_REASON,
            observed_value=intent.quantity,
            limit_value=limits.max_quantity,
            unit=_QUANTITY_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _limits_age_result(
        self,
        limits: RiskQuantityLimitsState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if limits.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_QUANTITY_LIMITS_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(limits.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - limits.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_QUANTITY_LIMITS_STALE_REASON,
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
