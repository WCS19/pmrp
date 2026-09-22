"""RISK-005 market-data freshness rule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from pmrp.risk.context import RiskContext
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult

RISK_MARKET_DATA_FRESH_RULE_ID = "RISK-005"
RISK_MARKET_DATA_FRESH_RULE_VERSION = "1.0"
RISK_MARKET_DATA_FRESH_REASON = "RISK_MARKET_DATA_FRESH"
RISK_MARKET_DATA_NOT_FRESH_REASON = "RISK_MARKET_DATA_NOT_FRESH"
RISK_MARKET_DATA_MISSING_REASON = "RISK_MARKET_DATA_MISSING"
RISK_MARKET_DATA_STALE_REASON = "RISK_MARKET_DATA_STALE"
RISK_MARKET_DATA_FUTURE_REASON = "RISK_MARKET_DATA_FUTURE"

_FRESH_UNIT = "fresh_flag"
_MILLISECONDS_UNIT = "milliseconds"
_ONE = Decimal("1")
_ZERO = Decimal("0")
_MICROSECONDS_PER_MILLISECOND = Decimal("1000")
_SECONDS_PER_DAY = 86_400


@dataclass(frozen=True, slots=True)
class MarketDataFreshnessRule:
    """Reject intents without a fresh market-data snapshot."""

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

        return RISK_MARKET_DATA_FRESH_RULE_ID

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""

        return RISK_MARKET_DATA_FRESH_RULE_VERSION

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate whether an intent has fresh market data in the risk snapshot."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("market data freshness rule requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("market data freshness rule requires a RiskContext")

        state = context.market_data_fresh_state(intent.market_id)
        if state is None:
            return self._result(
                passed=False,
                reason_code=RISK_MARKET_DATA_MISSING_REASON,
                observed_value=None,
                limit_value=_ONE,
                unit=_FRESH_UNIT,
                evaluated_at=context.evaluated_at,
            )

        if state.observed_at > context.evaluated_at:
            return self._result(
                passed=False,
                reason_code=RISK_MARKET_DATA_FUTURE_REASON,
                observed_value=_timedelta_milliseconds(state.observed_at - context.evaluated_at),
                limit_value=_ZERO,
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        age = context.evaluated_at - state.observed_at
        if age > self.max_state_age:
            return self._result(
                passed=False,
                reason_code=RISK_MARKET_DATA_STALE_REASON,
                observed_value=_timedelta_milliseconds(age),
                limit_value=_timedelta_milliseconds(self.max_state_age),
                unit=_MILLISECONDS_UNIT,
                evaluated_at=context.evaluated_at,
            )

        return self._result(
            passed=state.value,
            reason_code=(
                RISK_MARKET_DATA_FRESH_REASON if state.value else RISK_MARKET_DATA_NOT_FRESH_REASON
            ),
            observed_value=_ONE if state.value else _ZERO,
            limit_value=_ONE,
            unit=_FRESH_UNIT,
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
