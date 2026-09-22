"""Immutable risk input context snapshots."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType

from pmrp.risk.errors import RiskConfigurationError
from pmrp.schemas.enums import MarketStatus
from pmrp.schemas.identifiers import ContractId, ExchangeId, IntentId, MarketId, StrategyId
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
class RiskNotionalLimitState:
    """One timestamped notional-limit input used by deterministic risk rules."""

    max_notional: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        max_notional = parse_decimal(
            self.max_notional,
            field_name="risk notional max_notional",
        )
        if max_notional <= Decimal("0"):
            raise RiskConfigurationError("max_notional must be positive")
        object.__setattr__(self, "max_notional", max_notional)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))


@dataclass(frozen=True, slots=True)
class RiskMarketPositionState:
    """One timestamped market-position input used by deterministic risk rules."""

    current_position: Decimal
    max_position: Decimal
    observed_at: datetime
    open_order_position_delta: Decimal = Decimal("0")
    reserved_position_delta: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        current_position = parse_decimal(
            self.current_position,
            field_name="risk market position current_position",
        )
        max_position = parse_decimal(
            self.max_position,
            field_name="risk market position max_position",
        )
        open_order_position_delta = parse_decimal(
            self.open_order_position_delta,
            field_name="risk market position open_order_position_delta",
        )
        reserved_position_delta = parse_decimal(
            self.reserved_position_delta,
            field_name="risk market position reserved_position_delta",
        )
        if max_position <= Decimal("0"):
            raise RiskConfigurationError("max_position must be positive")
        object.__setattr__(self, "current_position", current_position)
        object.__setattr__(self, "max_position", max_position)
        object.__setattr__(self, "open_order_position_delta", open_order_position_delta)
        object.__setattr__(self, "reserved_position_delta", reserved_position_delta)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))

    @property
    def effective_position(self) -> Decimal:
        """Return position after known open-order and reservation deltas."""

        return self.current_position + self.open_order_position_delta + self.reserved_position_delta


@dataclass(frozen=True, slots=True)
class RiskPortfolioGrossExposureState:
    """One timestamped portfolio gross-exposure input for deterministic risk rules."""

    current_gross_exposure: Decimal
    max_gross_exposure: Decimal
    observed_at: datetime
    open_order_gross_exposure: Decimal = Decimal("0")
    reserved_gross_exposure: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        current_gross_exposure = parse_decimal(
            self.current_gross_exposure,
            field_name="risk portfolio gross current_gross_exposure",
        )
        max_gross_exposure = parse_decimal(
            self.max_gross_exposure,
            field_name="risk portfolio gross max_gross_exposure",
        )
        open_order_gross_exposure = parse_decimal(
            self.open_order_gross_exposure,
            field_name="risk portfolio gross open_order_gross_exposure",
        )
        reserved_gross_exposure = parse_decimal(
            self.reserved_gross_exposure,
            field_name="risk portfolio gross reserved_gross_exposure",
        )
        if current_gross_exposure < Decimal("0"):
            raise RiskConfigurationError("current_gross_exposure must be nonnegative")
        if open_order_gross_exposure < Decimal("0"):
            raise RiskConfigurationError("open_order_gross_exposure must be nonnegative")
        if reserved_gross_exposure < Decimal("0"):
            raise RiskConfigurationError("reserved_gross_exposure must be nonnegative")
        if max_gross_exposure <= Decimal("0"):
            raise RiskConfigurationError("max_gross_exposure must be positive")
        object.__setattr__(self, "current_gross_exposure", current_gross_exposure)
        object.__setattr__(self, "max_gross_exposure", max_gross_exposure)
        object.__setattr__(self, "open_order_gross_exposure", open_order_gross_exposure)
        object.__setattr__(self, "reserved_gross_exposure", reserved_gross_exposure)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))

    @property
    def effective_gross_exposure(self) -> Decimal:
        """Return current gross exposure plus known pending exposure."""

        return (
            self.current_gross_exposure
            + self.open_order_gross_exposure
            + self.reserved_gross_exposure
        )


@dataclass(frozen=True, slots=True)
class RiskPortfolioNetExposureState:
    """One timestamped portfolio net-exposure input for deterministic risk rules."""

    current_net_exposure: Decimal
    max_net_exposure: Decimal
    observed_at: datetime
    open_order_net_exposure_delta: Decimal = Decimal("0")
    reserved_net_exposure_delta: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        current_net_exposure = parse_decimal(
            self.current_net_exposure,
            field_name="risk portfolio net current_net_exposure",
        )
        max_net_exposure = parse_decimal(
            self.max_net_exposure,
            field_name="risk portfolio net max_net_exposure",
        )
        open_order_net_exposure_delta = parse_decimal(
            self.open_order_net_exposure_delta,
            field_name="risk portfolio net open_order_net_exposure_delta",
        )
        reserved_net_exposure_delta = parse_decimal(
            self.reserved_net_exposure_delta,
            field_name="risk portfolio net reserved_net_exposure_delta",
        )
        if max_net_exposure <= Decimal("0"):
            raise RiskConfigurationError("max_net_exposure must be positive")
        object.__setattr__(self, "current_net_exposure", current_net_exposure)
        object.__setattr__(self, "max_net_exposure", max_net_exposure)
        object.__setattr__(self, "open_order_net_exposure_delta", open_order_net_exposure_delta)
        object.__setattr__(self, "reserved_net_exposure_delta", reserved_net_exposure_delta)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))

    @property
    def effective_net_exposure(self) -> Decimal:
        """Return current signed net exposure plus known pending net exposure."""

        return (
            self.current_net_exposure
            + self.open_order_net_exposure_delta
            + self.reserved_net_exposure_delta
        )


@dataclass(frozen=True, slots=True)
class RiskStrategyCapitalState:
    """One timestamped strategy-capital input used by deterministic risk rules."""

    current_capital_used: Decimal
    max_strategy_capital: Decimal
    observed_at: datetime
    open_order_capital: Decimal = Decimal("0")
    reserved_capital: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        current_capital_used = parse_decimal(
            self.current_capital_used,
            field_name="risk strategy capital current_capital_used",
        )
        max_strategy_capital = parse_decimal(
            self.max_strategy_capital,
            field_name="risk strategy capital max_strategy_capital",
        )
        open_order_capital = parse_decimal(
            self.open_order_capital,
            field_name="risk strategy capital open_order_capital",
        )
        reserved_capital = parse_decimal(
            self.reserved_capital,
            field_name="risk strategy capital reserved_capital",
        )
        if current_capital_used < Decimal("0"):
            raise RiskConfigurationError("current_capital_used must be nonnegative")
        if open_order_capital < Decimal("0"):
            raise RiskConfigurationError("open_order_capital must be nonnegative")
        if reserved_capital < Decimal("0"):
            raise RiskConfigurationError("reserved_capital must be nonnegative")
        if max_strategy_capital <= Decimal("0"):
            raise RiskConfigurationError("max_strategy_capital must be positive")
        object.__setattr__(self, "current_capital_used", current_capital_used)
        object.__setattr__(self, "max_strategy_capital", max_strategy_capital)
        object.__setattr__(self, "open_order_capital", open_order_capital)
        object.__setattr__(self, "reserved_capital", reserved_capital)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))

    @property
    def effective_capital_used(self) -> Decimal:
        """Return current strategy capital plus known pending capital."""

        return self.current_capital_used + self.open_order_capital + self.reserved_capital


@dataclass(frozen=True, slots=True)
class RiskExchangeCapitalState:
    """One timestamped exchange-capital input used by deterministic risk rules."""

    current_capital_used: Decimal
    max_exchange_capital: Decimal
    observed_at: datetime
    open_order_capital: Decimal = Decimal("0")
    reserved_capital: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        current_capital_used = parse_decimal(
            self.current_capital_used,
            field_name="risk exchange capital current_capital_used",
        )
        max_exchange_capital = parse_decimal(
            self.max_exchange_capital,
            field_name="risk exchange capital max_exchange_capital",
        )
        open_order_capital = parse_decimal(
            self.open_order_capital,
            field_name="risk exchange capital open_order_capital",
        )
        reserved_capital = parse_decimal(
            self.reserved_capital,
            field_name="risk exchange capital reserved_capital",
        )
        if current_capital_used < Decimal("0"):
            raise RiskConfigurationError("current_capital_used must be nonnegative")
        if open_order_capital < Decimal("0"):
            raise RiskConfigurationError("open_order_capital must be nonnegative")
        if reserved_capital < Decimal("0"):
            raise RiskConfigurationError("reserved_capital must be nonnegative")
        if max_exchange_capital <= Decimal("0"):
            raise RiskConfigurationError("max_exchange_capital must be positive")
        object.__setattr__(self, "current_capital_used", current_capital_used)
        object.__setattr__(self, "max_exchange_capital", max_exchange_capital)
        object.__setattr__(self, "open_order_capital", open_order_capital)
        object.__setattr__(self, "reserved_capital", reserved_capital)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))

    @property
    def effective_capital_used(self) -> Decimal:
        """Return current exchange capital plus known pending capital."""

        return self.current_capital_used + self.open_order_capital + self.reserved_capital


@dataclass(frozen=True, slots=True)
class RiskDailyLossState:
    """One timestamped daily-PnL input used by deterministic risk rules."""

    daily_realized_pnl: Decimal
    daily_unrealized_pnl: Decimal
    max_daily_loss: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        daily_realized_pnl = parse_decimal(
            self.daily_realized_pnl,
            field_name="risk daily loss daily_realized_pnl",
        )
        daily_unrealized_pnl = parse_decimal(
            self.daily_unrealized_pnl,
            field_name="risk daily loss daily_unrealized_pnl",
        )
        max_daily_loss = parse_decimal(
            self.max_daily_loss,
            field_name="risk daily loss max_daily_loss",
        )
        if max_daily_loss <= Decimal("0"):
            raise RiskConfigurationError("max_daily_loss must be positive")
        object.__setattr__(self, "daily_realized_pnl", daily_realized_pnl)
        object.__setattr__(self, "daily_unrealized_pnl", daily_unrealized_pnl)
        object.__setattr__(self, "max_daily_loss", max_daily_loss)
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))

    @property
    def total_daily_pnl(self) -> Decimal:
        """Return realized plus unrealized daily PnL."""

        return self.daily_realized_pnl + self.daily_unrealized_pnl

    @property
    def current_daily_loss(self) -> Decimal:
        """Return nonnegative daily loss implied by signed daily PnL."""

        total = self.total_daily_pnl
        if total >= Decimal("0"):
            return Decimal("0")
        return -total


@dataclass(frozen=True, slots=True)
class RiskOpenOrderLimitState:
    """One timestamped open-order count input used by deterministic risk rules."""

    current_open_orders: int
    max_open_orders: int
    observed_at: datetime
    pending_cancel_orders: int = 0
    reserved_open_orders: int = 0

    def __post_init__(self) -> None:
        _validate_nonnegative_int(self.current_open_orders, field_name="current_open_orders")
        _validate_positive_int(self.max_open_orders, field_name="max_open_orders")
        _validate_nonnegative_int(self.pending_cancel_orders, field_name="pending_cancel_orders")
        _validate_nonnegative_int(self.reserved_open_orders, field_name="reserved_open_orders")
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))

    @property
    def effective_open_order_count(self) -> int:
        """Return current open orders plus known pending and reserved orders."""

        return self.current_open_orders + self.pending_cancel_orders + self.reserved_open_orders


@dataclass(frozen=True, slots=True)
class RiskDuplicateOrderGuardState:
    """One timestamped duplicate-order snapshot used by deterministic risk rules."""

    observed_at: datetime
    known_intent_ids: Collection[IntentId] = field(default_factory=frozenset)
    known_idempotency_keys: Collection[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", parse_utc_datetime(self.observed_at))
        object.__setattr__(
            self,
            "known_intent_ids",
            _freeze_known_intent_ids(self.known_intent_ids),
        )
        object.__setattr__(
            self,
            "known_idempotency_keys",
            _freeze_known_idempotency_keys(self.known_idempotency_keys),
        )


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
    notional_limits: Mapping[ContractId, RiskNotionalLimitState] = field(default_factory=dict)
    market_positions: Mapping[MarketId, RiskMarketPositionState] = field(default_factory=dict)
    portfolio_gross_exposure: RiskPortfolioGrossExposureState | None = None
    portfolio_net_exposure: RiskPortfolioNetExposureState | None = None
    strategy_capital: Mapping[StrategyId, RiskStrategyCapitalState] = field(default_factory=dict)
    market_exchanges: Mapping[MarketId, ExchangeId] = field(default_factory=dict)
    exchange_capital: Mapping[ExchangeId, RiskExchangeCapitalState] = field(default_factory=dict)
    daily_loss: RiskDailyLossState | None = None
    open_order_limit: RiskOpenOrderLimitState | None = None
    duplicate_order_guard: RiskDuplicateOrderGuardState | None = None

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
        object.__setattr__(
            self,
            "notional_limits",
            _freeze_notional_limits(self.notional_limits),
        )
        object.__setattr__(
            self,
            "market_positions",
            _freeze_market_positions(self.market_positions),
        )
        if self.portfolio_gross_exposure is not None and not isinstance(
            self.portfolio_gross_exposure,
            RiskPortfolioGrossExposureState,
        ):
            raise RiskConfigurationError(
                "portfolio_gross_exposure must be a RiskPortfolioGrossExposureState instance"
            )
        if self.portfolio_net_exposure is not None and not isinstance(
            self.portfolio_net_exposure,
            RiskPortfolioNetExposureState,
        ):
            raise RiskConfigurationError(
                "portfolio_net_exposure must be a RiskPortfolioNetExposureState instance"
            )
        object.__setattr__(
            self,
            "strategy_capital",
            _freeze_strategy_capital(self.strategy_capital),
        )
        object.__setattr__(
            self,
            "market_exchanges",
            _freeze_market_exchanges(self.market_exchanges),
        )
        object.__setattr__(
            self,
            "exchange_capital",
            _freeze_exchange_capital(self.exchange_capital),
        )
        if self.daily_loss is not None and not isinstance(
            self.daily_loss,
            RiskDailyLossState,
        ):
            raise RiskConfigurationError("daily_loss must be a RiskDailyLossState instance")
        if self.open_order_limit is not None and not isinstance(
            self.open_order_limit,
            RiskOpenOrderLimitState,
        ):
            raise RiskConfigurationError(
                "open_order_limit must be a RiskOpenOrderLimitState instance"
            )
        if self.duplicate_order_guard is not None and not isinstance(
            self.duplicate_order_guard,
            RiskDuplicateOrderGuardState,
        ):
            raise RiskConfigurationError(
                "duplicate_order_guard must be a RiskDuplicateOrderGuardState instance"
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

    def notional_limits_state(self, contract_id: ContractId) -> RiskNotionalLimitState | None:
        """Return the notional-limit state for a contract, if present in this snapshot."""

        return self.notional_limits.get(contract_id)

    def market_position_state(self, market_id: MarketId) -> RiskMarketPositionState | None:
        """Return the market-position state for a market, if present in this snapshot."""

        return self.market_positions.get(market_id)

    def portfolio_gross_exposure_state(self) -> RiskPortfolioGrossExposureState | None:
        """Return the portfolio gross-exposure state, if present in this snapshot."""

        return self.portfolio_gross_exposure

    def portfolio_net_exposure_state(self) -> RiskPortfolioNetExposureState | None:
        """Return the portfolio net-exposure state, if present in this snapshot."""

        return self.portfolio_net_exposure

    def strategy_capital_state(self, strategy_id: StrategyId) -> RiskStrategyCapitalState | None:
        """Return the strategy-capital state for a strategy, if present."""

        return self.strategy_capital.get(strategy_id)

    def market_exchange_id(self, market_id: MarketId) -> ExchangeId | None:
        """Return the exchange identifier for a market, if present."""

        return self.market_exchanges.get(market_id)

    def exchange_capital_state(self, exchange_id: ExchangeId) -> RiskExchangeCapitalState | None:
        """Return the exchange-capital state for an exchange, if present."""

        return self.exchange_capital.get(exchange_id)

    def daily_loss_state(self) -> RiskDailyLossState | None:
        """Return the daily-loss state, if present in this snapshot."""

        return self.daily_loss

    def open_order_limit_state(self) -> RiskOpenOrderLimitState | None:
        """Return the open-order limit state, if present in this snapshot."""

        return self.open_order_limit

    def duplicate_order_guard_state(self) -> RiskDuplicateOrderGuardState | None:
        """Return the duplicate-order guard state, if present in this snapshot."""

        return self.duplicate_order_guard


def _validate_nonnegative_int(value: int, *, field_name: str) -> None:
    if type(value) is not int:
        msg = f"{field_name} must be an int"
        raise TypeError(msg)
    if value < 0:
        raise RiskConfigurationError(f"{field_name} must be nonnegative")


def _validate_positive_int(value: int, *, field_name: str) -> None:
    if type(value) is not int:
        msg = f"{field_name} must be an int"
        raise TypeError(msg)
    if value <= 0:
        raise RiskConfigurationError(f"{field_name} must be positive")


def _freeze_known_intent_ids(intent_ids: Collection[IntentId]) -> frozenset[IntentId]:
    if isinstance(intent_ids, (str, bytes)) or not isinstance(intent_ids, Collection):
        msg = "known_intent_ids must be a collection"
        raise TypeError(msg)
    frozen = frozenset(intent_ids)
    for intent_id in frozen:
        if not isinstance(intent_id, IntentId):
            raise RiskConfigurationError(
                "known_intent_ids values must be canonical IntentId values"
            )
    return frozen


_MAX_IDEMPOTENCY_KEY_LENGTH = 256


def _freeze_known_idempotency_keys(keys: Collection[str]) -> frozenset[str]:
    if isinstance(keys, (str, bytes)) or not isinstance(keys, Collection):
        msg = "known_idempotency_keys must be a collection"
        raise TypeError(msg)
    frozen = frozenset(keys)
    for key in frozen:
        if type(key) is not str:
            msg = "known_idempotency_keys values must be strings"
            raise TypeError(msg)
        if key == "":
            raise RiskConfigurationError("known_idempotency_keys values must not be empty")
        if len(key) > _MAX_IDEMPOTENCY_KEY_LENGTH:
            raise RiskConfigurationError(
                "known_idempotency_keys values must be at most 256 characters"
            )
    return frozen


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


def _freeze_strategy_capital(
    states: Mapping[StrategyId, RiskStrategyCapitalState],
) -> Mapping[StrategyId, RiskStrategyCapitalState]:
    if not isinstance(states, Mapping):
        msg = "strategy_capital must be a mapping"
        raise TypeError(msg)
    frozen: dict[StrategyId, RiskStrategyCapitalState] = {}
    for strategy_id, state in states.items():
        if not isinstance(strategy_id, StrategyId):
            raise RiskConfigurationError(
                "strategy_capital keys must be canonical StrategyId values"
            )
        if not isinstance(state, RiskStrategyCapitalState):
            raise RiskConfigurationError(
                "strategy_capital values must be RiskStrategyCapitalState instances"
            )
        frozen[strategy_id] = state
    return MappingProxyType(frozen)


def _freeze_market_exchanges(
    exchanges: Mapping[MarketId, ExchangeId],
) -> Mapping[MarketId, ExchangeId]:
    if not isinstance(exchanges, Mapping):
        msg = "market_exchanges must be a mapping"
        raise TypeError(msg)
    frozen: dict[MarketId, ExchangeId] = {}
    for market_id, exchange_id in exchanges.items():
        if not isinstance(market_id, MarketId):
            raise RiskConfigurationError("market_exchanges keys must be canonical MarketId values")
        if not isinstance(exchange_id, ExchangeId):
            raise RiskConfigurationError(
                "market_exchanges values must be canonical ExchangeId values"
            )
        frozen[market_id] = exchange_id
    return MappingProxyType(frozen)


def _freeze_exchange_capital(
    states: Mapping[ExchangeId, RiskExchangeCapitalState],
) -> Mapping[ExchangeId, RiskExchangeCapitalState]:
    if not isinstance(states, Mapping):
        msg = "exchange_capital must be a mapping"
        raise TypeError(msg)
    frozen: dict[ExchangeId, RiskExchangeCapitalState] = {}
    for exchange_id, state in states.items():
        if not isinstance(exchange_id, ExchangeId):
            raise RiskConfigurationError(
                "exchange_capital keys must be canonical ExchangeId values"
            )
        if not isinstance(state, RiskExchangeCapitalState):
            raise RiskConfigurationError(
                "exchange_capital values must be RiskExchangeCapitalState instances"
            )
        frozen[exchange_id] = state
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


def _freeze_notional_limits(
    states: Mapping[ContractId, RiskNotionalLimitState],
) -> Mapping[ContractId, RiskNotionalLimitState]:
    if not isinstance(states, Mapping):
        msg = "notional_limits must be a mapping"
        raise TypeError(msg)
    frozen: dict[ContractId, RiskNotionalLimitState] = {}
    for contract_id, state in states.items():
        if not isinstance(contract_id, ContractId):
            raise RiskConfigurationError("notional_limits keys must be canonical ContractId values")
        if not isinstance(state, RiskNotionalLimitState):
            raise RiskConfigurationError(
                "notional_limits values must be RiskNotionalLimitState instances"
            )
        frozen[contract_id] = state
    return MappingProxyType(frozen)


def _freeze_market_positions(
    states: Mapping[MarketId, RiskMarketPositionState],
) -> Mapping[MarketId, RiskMarketPositionState]:
    if not isinstance(states, Mapping):
        msg = "market_positions must be a mapping"
        raise TypeError(msg)
    frozen: dict[MarketId, RiskMarketPositionState] = {}
    for market_id, state in states.items():
        if not isinstance(market_id, MarketId):
            raise RiskConfigurationError("market_positions keys must be canonical MarketId values")
        if not isinstance(state, RiskMarketPositionState):
            raise RiskConfigurationError(
                "market_positions values must be RiskMarketPositionState instances"
            )
        frozen[market_id] = state
    return MappingProxyType(frozen)
