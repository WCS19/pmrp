"""Immutable risk input context snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType

from pmrp.risk.errors import RiskConfigurationError
from pmrp.schemas.enums import MarketStatus
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.schemas.numeric import parse_decimal
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
class RiskMarketStatusState:
    """One timestamped market status input used by deterministic risk rules."""

    status: MarketStatus
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.status, MarketStatus):
            msg = "risk market status state requires a canonical MarketStatus"
            raise TypeError(msg)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))


@dataclass(frozen=True, slots=True)
class RiskPriceBoundsState:
    """One timestamped price-bounds input used by deterministic risk rules."""

    min_price: Decimal
    max_price: Decimal
    observed_at: datetime
    tick_size: Decimal | None = None

    def __post_init__(self) -> None:
        min_price = parse_decimal(self.min_price, field_name="risk price min_price")
        max_price = parse_decimal(self.max_price, field_name="risk price max_price")
        tick_size = (
            None
            if self.tick_size is None
            else parse_decimal(self.tick_size, field_name="risk price tick_size")
        )
        if min_price < Decimal("0"):
            raise RiskConfigurationError("min_price must be nonnegative")
        if max_price < min_price:
            raise RiskConfigurationError("max_price must be greater than or equal to min_price")
        if tick_size is not None and tick_size <= Decimal("0"):
            raise RiskConfigurationError("tick_size must be positive")
        object.__setattr__(self, "min_price", min_price)
        object.__setattr__(self, "max_price", max_price)
        object.__setattr__(self, "tick_size", tick_size)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))


@dataclass(frozen=True, slots=True)
class RiskQuantityLimitsState:
    """One timestamped quantity-limit input used by deterministic risk rules."""

    min_quantity: Decimal
    max_quantity: Decimal
    quantity_increment: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        min_quantity = parse_decimal(
            self.min_quantity,
            field_name="risk quantity min_quantity",
        )
        max_quantity = parse_decimal(
            self.max_quantity,
            field_name="risk quantity max_quantity",
        )
        quantity_increment = parse_decimal(
            self.quantity_increment,
            field_name="risk quantity quantity_increment",
        )
        if min_quantity < Decimal("0"):
            raise RiskConfigurationError("min_quantity must be nonnegative")
        if max_quantity < min_quantity:
            raise RiskConfigurationError(
                "max_quantity must be greater than or equal to min_quantity"
            )
        if quantity_increment <= Decimal("0"):
            raise RiskConfigurationError("quantity_increment must be positive")
        object.__setattr__(self, "min_quantity", min_quantity)
        object.__setattr__(self, "max_quantity", max_quantity)
        object.__setattr__(self, "quantity_increment", quantity_increment)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))


@dataclass(frozen=True, slots=True)
class RiskContext:
    """Immutable state snapshot supplied to risk rule evaluation."""

    evaluated_at: datetime
    strategy_enabled: Mapping[StrategyId, RiskBooleanState] = field(default_factory=dict)
    market_enabled: Mapping[MarketId, RiskBooleanState] = field(default_factory=dict)
    market_status: Mapping[MarketId, RiskMarketStatusState] = field(default_factory=dict)
    market_data_fresh: Mapping[MarketId, RiskBooleanState] = field(default_factory=dict)
    price_bounds: Mapping[MarketId, RiskPriceBoundsState] = field(default_factory=dict)
    quantity_limits: Mapping[ContractId, RiskQuantityLimitsState] = field(default_factory=dict)

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
        object.__setattr__(
            self,
            "market_data_fresh",
            _freeze_market_data_fresh(self.market_data_fresh),
        )
        object.__setattr__(
            self,
            "market_status",
            _freeze_market_status(self.market_status),
        )
        object.__setattr__(
            self,
            "price_bounds",
            _freeze_price_bounds(self.price_bounds),
        )
        object.__setattr__(
            self,
            "quantity_limits",
            _freeze_quantity_limits(self.quantity_limits),
        )

    def strategy_enabled_state(self, strategy_id: StrategyId) -> RiskBooleanState | None:
        """Return the enabled state for a strategy, if present in this snapshot."""

        return self.strategy_enabled.get(strategy_id)

    def market_enabled_state(self, market_id: MarketId) -> RiskBooleanState | None:
        """Return the enabled state for a market, if present in this snapshot."""

        return self.market_enabled.get(market_id)

    def market_data_fresh_state(self, market_id: MarketId) -> RiskBooleanState | None:
        """Return the market-data freshness state for a market, if present."""

        return self.market_data_fresh.get(market_id)

    def market_status_state(self, market_id: MarketId) -> RiskMarketStatusState | None:
        """Return the market status state for a market, if present in this snapshot."""

        return self.market_status.get(market_id)

    def price_bounds_state(self, market_id: MarketId) -> RiskPriceBoundsState | None:
        """Return the price-bounds state for a market, if present in this snapshot."""

        return self.price_bounds.get(market_id)

    def quantity_limits_state(self, contract_id: ContractId) -> RiskQuantityLimitsState | None:
        """Return the quantity-limit state for a contract, if present in this snapshot."""

        return self.quantity_limits.get(contract_id)


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


def _freeze_market_data_fresh(
    states: Mapping[MarketId, RiskBooleanState],
) -> Mapping[MarketId, RiskBooleanState]:
    if not isinstance(states, Mapping):
        msg = "market_data_fresh must be a mapping"
        raise TypeError(msg)
    frozen: dict[MarketId, RiskBooleanState] = {}
    for market_id, state in states.items():
        if not isinstance(market_id, MarketId):
            raise RiskConfigurationError("market_data_fresh keys must be canonical MarketId values")
        if not isinstance(state, RiskBooleanState):
            raise RiskConfigurationError(
                "market_data_fresh values must be RiskBooleanState instances"
            )
        frozen[market_id] = state
    return MappingProxyType(frozen)


def _freeze_market_status(
    states: Mapping[MarketId, RiskMarketStatusState],
) -> Mapping[MarketId, RiskMarketStatusState]:
    if not isinstance(states, Mapping):
        msg = "market_status must be a mapping"
        raise TypeError(msg)
    frozen: dict[MarketId, RiskMarketStatusState] = {}
    for market_id, state in states.items():
        if not isinstance(market_id, MarketId):
            raise RiskConfigurationError("market_status keys must be canonical MarketId values")
        if not isinstance(state, RiskMarketStatusState):
            raise RiskConfigurationError(
                "market_status values must be RiskMarketStatusState instances"
            )
        frozen[market_id] = state
    return MappingProxyType(frozen)


def _freeze_price_bounds(
    states: Mapping[MarketId, RiskPriceBoundsState],
) -> Mapping[MarketId, RiskPriceBoundsState]:
    if not isinstance(states, Mapping):
        msg = "price_bounds must be a mapping"
        raise TypeError(msg)
    frozen: dict[MarketId, RiskPriceBoundsState] = {}
    for market_id, state in states.items():
        if not isinstance(market_id, MarketId):
            raise RiskConfigurationError("price_bounds keys must be canonical MarketId values")
        if not isinstance(state, RiskPriceBoundsState):
            raise RiskConfigurationError(
                "price_bounds values must be RiskPriceBoundsState instances"
            )
        frozen[market_id] = state
    return MappingProxyType(frozen)


def _freeze_quantity_limits(
    states: Mapping[ContractId, RiskQuantityLimitsState],
) -> Mapping[ContractId, RiskQuantityLimitsState]:
    if not isinstance(states, Mapping):
        msg = "quantity_limits must be a mapping"
        raise TypeError(msg)
    frozen: dict[ContractId, RiskQuantityLimitsState] = {}
    for contract_id, state in states.items():
        if not isinstance(contract_id, ContractId):
            raise RiskConfigurationError("quantity_limits keys must be canonical ContractId values")
        if not isinstance(state, RiskQuantityLimitsState):
            raise RiskConfigurationError(
                "quantity_limits values must be RiskQuantityLimitsState instances"
            )
        frozen[contract_id] = state
    return MappingProxyType(frozen)
