"""Helpers for deriving kill-switch risk context from canonical records."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Self

from pmrp.risk.context import RiskContext, RiskKillSwitchClearState
from pmrp.risk.errors import RiskConfigurationError, RiskInputError
from pmrp.schemas.identifiers import AccountId, ExchangeId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import KillSwitchScope, KillSwitchState
from pmrp.schemas.time import parse_utc_datetime

_SCOPE_ID_MAX_LENGTH = 256


@dataclass(frozen=True, slots=True)
class KillSwitchEvaluationSubject:
    """Identifiers used to decide which active kill switches apply to an intent."""

    strategy_id: StrategyId
    market_id: MarketId
    exchange_id: ExchangeId | None = None
    account_id: AccountId | None = None
    execution_gateway_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, StrategyId):
            raise RiskConfigurationError("strategy_id must be a canonical StrategyId")
        if not isinstance(self.market_id, MarketId):
            raise RiskConfigurationError("market_id must be a canonical MarketId")
        if self.exchange_id is not None and not isinstance(self.exchange_id, ExchangeId):
            raise RiskConfigurationError("exchange_id must be a canonical ExchangeId")
        if self.account_id is not None and not isinstance(self.account_id, AccountId):
            raise RiskConfigurationError("account_id must be a canonical AccountId")
        if self.execution_gateway_id is not None:
            _validate_scope_id(
                self.execution_gateway_id,
                field_name="execution_gateway_id",
            )

    @classmethod
    def from_intent(
        cls,
        intent: OrderIntent,
        context: RiskContext,
        *,
        account_id: AccountId | None = None,
        execution_gateway_id: str | None = None,
    ) -> Self:
        """Build a subject from an order intent and risk context exchange mapping."""

        if not isinstance(intent, OrderIntent):
            raise RiskInputError("kill-switch subject requires an OrderIntent")
        if not isinstance(context, RiskContext):
            raise RiskInputError("kill-switch subject requires a RiskContext")
        return cls(
            strategy_id=intent.strategy_id,
            market_id=intent.market_id,
            exchange_id=context.market_exchange_id(intent.market_id),
            account_id=account_id,
            execution_gateway_id=execution_gateway_id,
        )


@dataclass(frozen=True, slots=True)
class KillSwitchClearStateFactory:
    """Build deterministic RISK-019 state from active canonical kill switches."""

    def clear_state_for_subject(
        self,
        kill_switches: Sequence[KillSwitchState],
        subject: KillSwitchEvaluationSubject,
        *,
        observed_at: datetime,
    ) -> RiskKillSwitchClearState:
        """Return the kill-switch clear state applicable to one evaluation subject."""

        switches = _validate_kill_switches(kill_switches)
        if not isinstance(subject, KillSwitchEvaluationSubject):
            raise RiskInputError("kill-switch clear state requires a KillSwitchEvaluationSubject")
        observed_at = parse_utc_datetime(observed_at)

        active_scopes: set[KillSwitchScope] = set()
        for kill_switch in switches:
            if not kill_switch.active:
                continue
            if _matches_subject(kill_switch, subject):
                active_scopes.add(kill_switch.scope)

        if not active_scopes:
            return RiskKillSwitchClearState(clear=True, observed_at=observed_at)
        return RiskKillSwitchClearState(
            clear=False,
            observed_at=observed_at,
            active_scopes=frozenset(active_scopes),
        )


def build_kill_switch_clear_state(
    kill_switches: Sequence[KillSwitchState],
    subject: KillSwitchEvaluationSubject,
    *,
    observed_at: datetime,
) -> RiskKillSwitchClearState:
    """Build the kill-switch clear state using the default factory."""

    return KillSwitchClearStateFactory().clear_state_for_subject(
        kill_switches,
        subject,
        observed_at=observed_at,
    )


def _validate_kill_switches(
    kill_switches: Sequence[KillSwitchState],
) -> tuple[KillSwitchState, ...]:
    if isinstance(kill_switches, (str, bytes)) or not isinstance(kill_switches, Sequence):
        msg = "kill_switches must be a sequence"
        raise TypeError(msg)
    switches = tuple(kill_switches)
    for kill_switch in switches:
        if not isinstance(kill_switch, KillSwitchState):
            raise RiskInputError("kill_switches values must be canonical KillSwitchState records")
    return switches


def _matches_subject(
    kill_switch: KillSwitchState,
    subject: KillSwitchEvaluationSubject,
) -> bool:
    if kill_switch.scope is KillSwitchScope.GLOBAL:
        return True

    scope_id = kill_switch.scope_id
    if scope_id is None:
        raise RiskConfigurationError("active non-global kill switch requires scope_id")

    if kill_switch.scope is KillSwitchScope.STRATEGY:
        return scope_id == str(subject.strategy_id)
    if kill_switch.scope is KillSwitchScope.MARKET:
        return scope_id == str(subject.market_id)
    if kill_switch.scope is KillSwitchScope.EXCHANGE:
        return subject.exchange_id is not None and scope_id == str(subject.exchange_id)
    if kill_switch.scope is KillSwitchScope.ACCOUNT:
        return subject.account_id is not None and scope_id == str(subject.account_id)
    if kill_switch.scope is KillSwitchScope.EXECUTION_GATEWAY:
        return subject.execution_gateway_id is not None and scope_id == subject.execution_gateway_id

    return False


def _validate_scope_id(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "":
        raise RiskConfigurationError(f"{field_name} must not be empty")
    if len(value) > _SCOPE_ID_MAX_LENGTH:
        raise RiskConfigurationError(f"{field_name} must be at most 256 characters")
    return value
