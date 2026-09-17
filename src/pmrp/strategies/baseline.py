"""Baseline transparent strategies used to validate the strategy runtime."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from pydantic import Field, field_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.events import MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE, OrderBookSnapshotEvent
from pmrp.schemas.identifiers import ContractId, MarketId, StrategyId
from pmrp.strategies.context import StrategyContext, StrategyMetrics
from pmrp.strategies.errors import StrategyContextError

MIDPOINT_OBSERVER_CONFIGURATION_SCHEMA_VERSION = 1
MIDPOINT_OBSERVER_STRATEGY_TYPE = "midpoint_observer"
MIDPOINT_OBSERVER_STRATEGY_VERSION = "1.0.0"


class MidpointObserverConfiguration(CanonicalModel):
    """Configuration for a transparent no-order midpoint observer."""

    market_id: MarketId | None = None
    metric_prefix: str = Field(default="strategy.midpoint_observer", min_length=1, max_length=128)

    @field_validator("metric_prefix")
    @classmethod
    def validate_metric_prefix(cls, value: str) -> str:
        if value == "" or value.strip() != value:
            msg = "metric_prefix must be nonempty without surrounding whitespace"
            raise ValueError(msg)
        return value


@dataclass(frozen=True, slots=True)
class MidpointObservation:
    """Recorded Decimal midpoint for one valid order-book snapshot."""

    market_id: MarketId
    contract_id: ContractId
    exchange: str
    best_bid: Decimal
    best_ask: Decimal
    midpoint: Decimal
    spread: Decimal


class MidpointObserverStrategy:
    """Observe order-book snapshots, calculate midpoint, and emit metrics only."""

    def __init__(
        self,
        *,
        strategy_id: StrategyId,
        configuration: MidpointObserverConfiguration,
    ) -> None:
        if not isinstance(strategy_id, StrategyId):
            msg = "strategy_id must be a StrategyId"
            raise TypeError(msg)
        if not isinstance(configuration, MidpointObserverConfiguration):
            msg = "configuration must be a MidpointObserverConfiguration"
            raise TypeError(msg)
        self._strategy_id = strategy_id
        self._configuration = configuration
        self._metrics: StrategyMetrics | None = None
        self._observations: list[MidpointObservation] = []
        self._shutdown_reason: str | None = None

    @property
    def strategy_id(self) -> StrategyId:
        """Return the configured strategy instance id."""

        return self._strategy_id

    @property
    def strategy_type(self) -> str:
        """Return the stable strategy type key."""

        return MIDPOINT_OBSERVER_STRATEGY_TYPE

    @property
    def strategy_version(self) -> str:
        """Return the strategy implementation version."""

        return MIDPOINT_OBSERVER_STRATEGY_VERSION

    @property
    def configuration_schema_version(self) -> int:
        """Return the strategy configuration schema version."""

        return MIDPOINT_OBSERVER_CONFIGURATION_SCHEMA_VERSION

    @property
    def subscribed_event_types(self) -> tuple[str, ...]:
        """Return the canonical market data event types consumed by this strategy."""

        return (MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,)

    @property
    def observations(self) -> tuple[MidpointObservation, ...]:
        """Return midpoint observations in event-processing order."""

        return tuple(self._observations)

    @property
    def shutdown_reason(self) -> str | None:
        """Return the most recent controlled shutdown reason."""

        return self._shutdown_reason

    async def initialize(self, context: StrategyContext) -> None:
        """Bind the approved metrics service exposed through the strategy context."""

        metrics = context.service("metrics")
        if metrics is None:
            raise StrategyContextError(
                "Midpoint observer requires a metrics service",
                reason_code="midpoint_observer_metrics_missing",
                context={"strategy_id": str(self.strategy_id)},
            )
        if not callable(getattr(metrics, "increment", None)) or not callable(
            getattr(metrics, "gauge", None)
        ):
            raise StrategyContextError(
                "Midpoint observer metrics service is invalid",
                reason_code="midpoint_observer_metrics_invalid",
                context={"strategy_id": str(self.strategy_id)},
            )
        self._metrics = cast(StrategyMetrics, metrics)

    async def on_event(self, event: object) -> None:
        """Process one typed order-book snapshot event."""

        if not isinstance(event, OrderBookSnapshotEvent):
            return
        if self._configuration.market_id is not None and (
            event.snapshot.market_id != self._configuration.market_id
        ):
            return
        metrics = self._require_metrics()
        snapshot = event.snapshot
        tags = {
            "strategy_id": str(self.strategy_id),
            "market_id": str(snapshot.market_id),
            "contract_id": str(snapshot.contract_id),
            "exchange": snapshot.exchange,
        }
        if not snapshot.is_valid or not snapshot.bids or not snapshot.asks:
            metrics.increment(
                f"{self._configuration.metric_prefix}.snapshot_skipped",
                tags=tags,
            )
            return

        best_bid = snapshot.bids[0].price
        best_ask = snapshot.asks[0].price
        midpoint = (best_bid + best_ask) / Decimal("2")
        spread = best_ask - best_bid
        observation = MidpointObservation(
            market_id=snapshot.market_id,
            contract_id=snapshot.contract_id,
            exchange=snapshot.exchange,
            best_bid=best_bid,
            best_ask=best_ask,
            midpoint=midpoint,
            spread=spread,
        )
        self._observations.append(observation)

        metrics.increment(f"{self._configuration.metric_prefix}.snapshot_observed", tags=tags)
        metrics.gauge(f"{self._configuration.metric_prefix}.best_bid", best_bid, tags=tags)
        metrics.gauge(f"{self._configuration.metric_prefix}.best_ask", best_ask, tags=tags)
        metrics.gauge(f"{self._configuration.metric_prefix}.midpoint", midpoint, tags=tags)
        metrics.gauge(f"{self._configuration.metric_prefix}.spread", spread, tags=tags)

    async def shutdown(self, reason: str) -> None:
        """Record controlled shutdown reason without external side effects."""

        self._shutdown_reason = reason

    def _require_metrics(self) -> StrategyMetrics:
        if self._metrics is None:
            raise StrategyContextError(
                "Midpoint observer has not been initialized",
                reason_code="midpoint_observer_not_initialized",
                context={"strategy_id": str(self.strategy_id)},
            )
        return self._metrics


class MidpointObserverFactory:
    """Create midpoint observer strategy instances from validated configuration."""

    def create(
        self,
        *,
        strategy_id: StrategyId,
        configuration: object,
    ) -> MidpointObserverStrategy:
        """Return a midpoint observer strategy instance."""

        if not isinstance(configuration, MidpointObserverConfiguration):
            msg = "configuration must be a MidpointObserverConfiguration"
            raise TypeError(msg)
        return MidpointObserverStrategy(strategy_id=strategy_id, configuration=configuration)
