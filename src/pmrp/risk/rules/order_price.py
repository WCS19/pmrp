"""RISK-006 order-price validation rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext, RiskPriceBoundsState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_ORDER_PRICE_VALID_RULE_ID = "RISK-006"
RISK_ORDER_PRICE_VALID_RULE_VERSION = "1.0"
RISK_ORDER_PRICE_VALID_REASON = "RISK_ORDER_PRICE_VALID"
RISK_ORDER_PRICE_NOT_REQUIRED_REASON = "RISK_ORDER_PRICE_NOT_REQUIRED"
RISK_ORDER_PRICE_BOUNDS_MISSING_REASON = "RISK_ORDER_PRICE_BOUNDS_MISSING"
RISK_ORDER_PRICE_BOUNDS_STALE_REASON = "RISK_ORDER_PRICE_BOUNDS_STALE"
RISK_ORDER_PRICE_BOUNDS_FUTURE_REASON = "RISK_ORDER_PRICE_BOUNDS_FUTURE"
RISK_ORDER_PRICE_BELOW_MIN_REASON = "RISK_ORDER_PRICE_BELOW_MIN"
RISK_ORDER_PRICE_ABOVE_MAX_REASON = "RISK_ORDER_PRICE_ABOVE_MAX"
RISK_ORDER_PRICE_OFF_TICK_REASON = "RISK_ORDER_PRICE_OFF_TICK"

_PRICE_UNIT = "price"
_MIN_PRICE_UNIT = "min_price"
_MAX_PRICE_UNIT = "max_price"
_TICK_SIZE_UNIT = "tick_size"
_MILLISECONDS_UNIT = "milliseconds"
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class OrderPriceValidRule:
    """Reject intents with missing, stale, out-of-bounds, or off-tick prices."""

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

        return RISK_ORDER_PRICE_VALID_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_ORDER_PRICE_VALID_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether an intent's price is valid for the target market."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("order price valid rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("order price valid rule requires a RiskContext")

        price = intent.limit_price
        if price is None:
            return self._result(
                passed=True,
                reason_code=RISK_ORDER_PRICE_NOT_REQUIRED_REASON,
                observed_value=None,
                limit_value=None,
                unit=_PRICE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        bounds = context.price_bounds_state(intent.market_id)
        if bounds is None:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_PRICE_BOUNDS_MISSING_REASON,
                observed_value=price,
                limit_value=None,
                unit=_PRICE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        bounds_age_result = self._bounds_age_result(bounds, context)
        if bounds_age_result is not None:
            return bounds_age_result

        if price < bounds.min_price:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_PRICE_BELOW_MIN_REASON,
                observed_value=price,
                limit_value=bounds.min_price,
                unit=_MIN_PRICE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if price > bounds.max_price:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_PRICE_ABOVE_MAX_REASON,
                observed_value=price,
                limit_value=bounds.max_price,
                unit=_MAX_PRICE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if bounds.tick_size is not None and (price - bounds.min_price) % bounds.tick_size != _ZERO:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_PRICE_OFF_TICK_REASON,
                observed_value=price,
                limit_value=bounds.tick_size,
                unit=_TICK_SIZE_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=True,
            reason_code=RISK_ORDER_PRICE_VALID_REASON,
            observed_value=price,
            limit_value=bounds.max_price,
            unit=_PRICE_UNIT,
            evaluated_at=context.evaluated_at,
        )

    def _bounds_age_result(
        self,
        bounds: RiskPriceBoundsState,
        context: RiskContext,
    ) -> RiskRuleResult | None:
        if bounds.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_PRICE_BOUNDS_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(bounds.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - bounds.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_ORDER_PRICE_BOUNDS_STALE_REASON,
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
