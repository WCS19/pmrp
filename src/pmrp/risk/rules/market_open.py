"""RISK-004 market-open rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.enums import MarketStatus
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_MARKET_OPEN_RULE_ID = "RISK-004"
RISK_MARKET_OPEN_RULE_VERSION = "1.0"
RISK_MARKET_OPEN_REASON = "RISK_MARKET_OPEN"
RISK_MARKET_NOT_OPEN_REASON = "RISK_MARKET_NOT_OPEN"
RISK_MARKET_STATUS_MISSING_REASON = "RISK_MARKET_STATUS_MISSING"
RISK_MARKET_STATUS_STALE_REASON = "RISK_MARKET_STATUS_STALE"
RISK_MARKET_STATUS_FUTURE_REASON = "RISK_MARKET_STATUS_FUTURE"

_OPEN_STATUS_UNIT = "open_status"
_MILLISECONDS_UNIT = "milliseconds"
_ONE = Decimal("1")
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class MarketOpenRule:
    """Reject intents when the target market is not fresh and open."""

    max_state_age: timedelta
    open_statuses: tuple[MarketStatus, ...] = (MarketStatus.OPEN,)

    def __post_init__(self) -> None:
        if not isinstance(self.max_state_age, timedelta):
            msg = "max_state_age must be a timedelta"
            raise TypeError(msg)
        if self.max_state_age <= timedelta(0):
            raise RiskConfigurationError("max_state_age must be positive")
        if not isinstance(self.open_statuses, tuple):
            msg = "open_statuses must be a tuple"
            raise TypeError(msg)
        if not self.open_statuses:
            raise RiskConfigurationError("open_statuses must not be empty")
        if any(not isinstance(status, MarketStatus) for status in self.open_statuses):
            msg = "open_statuses must contain only canonical MarketStatus values"
            raise TypeError(msg)

    @property
    def rule_id(self) -> str:
        """Return the stable risk rule identifier."""

        return RISK_MARKET_OPEN_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_MARKET_OPEN_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether an intent's market is open in the risk snapshot."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("market open rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("market open rule requires a RiskContext")

        state = context.market_status_state(intent.market_id)
        if state is None:
            return self._result(
                passed=False,
                reason_code=RISK_MARKET_STATUS_MISSING_REASON,
                observed_value=None,
                limit_value=_ONE,
                unit=_OPEN_STATUS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if state.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_MARKET_STATUS_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(state.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - state.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_MARKET_STATUS_STALE_REASON,
                observed_value=_timedelta_milliseconds(age),
                limit_value=_timedelta_milliseconds(self.max_state_age),
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        passed = state.status in self.open_statuses
        return self._result(
            passed=passed,
            reason_code=RISK_MARKET_OPEN_REASON if passed else RISK_MARKET_NOT_OPEN_REASON,
            observed_value=_ONE if passed else _ZERO,
            limit_value=_ONE,
            unit=_OPEN_STATUS_UNIT,
            evaluated_at=context.evaluated_at,
        )

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
