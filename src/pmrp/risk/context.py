"""Immutable risk input context snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType

from pmrp.risk.errors import RiskConfigurationError
from pmrp.schemas.identifiers import MarketId, StrategyId
from pmrp.schemas.time import parse_utc_datetime


@dataclass(frozen=True, slots=True)
class RiskBooleanState:
    """One timestamped boolean input used by deterministic risk rules."""

    value: bool
    observed_at: datetime

    def __post_init__(self) -> None:
        if type(self.value) is not bool:
            msg = "risk boolean state value must be a bool"
            raise TypeError(msg)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))


@dataclass(frozen=True, slots=True)
class RiskContext:
    """Immutable state snapshot supplied to risk rule evaluation."""

    evaluated_at: datetime
    strategy_enabled: Mapping[StrategyId, RiskBooleanState] = field(default_factory=dict)
    market_enabled: Mapping[MarketId, RiskBooleanState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluated_at", parse_utc_datetime(self.evaluated_at))
        object.__setattr__(
            self,
            "strategy_enabled",
            _freeze_strategy_enabled(self.strategy_enabled),
        )
        object.__setattr__(
            self,
            "market_enabled",
            _freeze_market_enabled(self.market_enabled),
        )

    def strategy_enabled_state(self, strategy_id: StrategyId) -> RiskBooleanState | None:
        """Return the enabled state for a strategy, if present in this snapshot."""

        return self.strategy_enabled.get(strategy_id)

    def market_enabled_state(self, market_id: MarketId) -> RiskBooleanState | None:
        """Return the enabled state for a market, if present in this snapshot."""

        return self.market_enabled.get(market_id)


def _freeze_strategy_enabled(
    states: Mapping[StrategyId, RiskBooleanState],
) -> Mapping[StrategyId, RiskBooleanState]:
    if not isinstance(states, Mapping):
        msg = "strategy_enabled must be a mapping"
        raise TypeError(msg)
    frozen: dict[StrategyId, RiskBooleanState] = {}
    for strategy_id, state in states.items():
        if not isinstance(strategy_id, StrategyId):
            raise RiskConfigurationError(
                "strategy_enabled keys must be canonical StrategyId values"
            )
        if not isinstance(state, RiskBooleanState):
            raise RiskConfigurationError(
                "strategy_enabled values must be RiskBooleanState instances"
            )
        frozen[strategy_id] = state
    return MappingProxyType(frozen)


def _freeze_market_enabled(
    states: Mapping[MarketId, RiskBooleanState],
) -> Mapping[MarketId, RiskBooleanState]:
    if not isinstance(states, Mapping):
        msg = "market_enabled must be a mapping"
        raise TypeError(msg)
    frozen: dict[MarketId, RiskBooleanState] = {}
    for market_id, state in states.items():
        if not isinstance(market_id, MarketId):
            raise RiskConfigurationError("market_enabled keys must be canonical MarketId values")
        if not isinstance(state, RiskBooleanState):
            raise RiskConfigurationError("market_enabled values must be RiskBooleanState instances")
        frozen[market_id] = state
    return MappingProxyType(frozen)
