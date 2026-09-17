"""Baseline transparent strategies used to validate the strategy runtime."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import cast

from pydantic import Field, field_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.events import MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE, OrderBookSnapshotEvent
from pmrp.schemas.identifiers import ContractId, MarketId, SignalId, StrategyId
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.strategy import Signal, SignalDirection
from pmrp.strategies.context import StrategyContext, StrategyMetrics
from pmrp.strategies.errors import StrategyContextError

MIDPOINT_OBSERVER_CONFIGURATION_SCHEMA_VERSION = 1
MIDPOINT_OBSERVER_STRATEGY_TYPE = "midpoint_observer"
MIDPOINT_OBSERVER_STRATEGY_VERSION = "1.0.0"
THRESHOLD_SIGNAL_CONFIGURATION_SCHEMA_VERSION = 1
THRESHOLD_SIGNAL_STRATEGY_TYPE = "threshold_signal"
THRESHOLD_SIGNAL_STRATEGY_VERSION = "1.0.0"


class MidpointObserverConfiguration(CanonicalModel):
    """Configuration for a transparent no-order midpoint observer."""

    market_id: MarketId | None = None
    metric_prefix: str = Field(default="strategy.midpoint_observer", min_length=1, max_length=128)

    @field_validator("metric_prefix")
    @classmethod
    def validate_metric_prefix(cls, value: str) -> str:
        return _validate_required_text(value, field_name="metric_prefix")


class ThresholdSignalConfiguration(CanonicalModel):
    """Configuration for a transparent threshold-based buy signal strategy."""

    threshold_probability: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    market_id: MarketId | None = None
    confidence: Decimal = Field(default=Decimal("1"), ge=Decimal("0"), le=Decimal("1"))
    signal_type: str = Field(default="threshold_probability", min_length=1, max_length=128)
    reason_code: str = Field(default="BEST_ASK_BELOW_THRESHOLD", min_length=1, max_length=128)
    reason_text: str | None = Field(default=None, min_length=1, max_length=1024)

    @field_validator("threshold_probability", "confidence", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="threshold signal decimal field")

    @field_validator("signal_type", "reason_code")
    @classmethod
    def validate_required_text_fields(cls, value: str) -> str:
        return _validate_required_text(value, field_name="threshold signal text field")

    @field_validator("reason_text")
    @classmethod
    def validate_reason_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_required_text(value, field_name="threshold signal reason_text")


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


@dataclass(frozen=True, slots=True)
class ThresholdSignalDecision:
    """Recorded threshold signal decision for one generated signal."""

    market_id: MarketId
    contract_id: ContractId
    exchange: str
    best_ask: Decimal
    threshold_probability: Decimal
    signal: Signal


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


class ThresholdSignalStrategy:
    """Emit a canonical buy signal when best ask is below a configured threshold."""

    def __init__(
        self,
        *,
        strategy_id: StrategyId,
        configuration: ThresholdSignalConfiguration,
    ) -> None:
        if not isinstance(strategy_id, StrategyId):
            msg = "strategy_id must be a StrategyId"
            raise TypeError(msg)
        if not isinstance(configuration, ThresholdSignalConfiguration):
            msg = "configuration must be a ThresholdSignalConfiguration"
            raise TypeError(msg)
        self._strategy_id = strategy_id
        self._configuration = configuration
        self._context: StrategyContext | None = None
        self._decisions: list[ThresholdSignalDecision] = []
        self._shutdown_reason: str | None = None

    @property
    def strategy_id(self) -> StrategyId:
        """Return the configured strategy instance id."""

        return self._strategy_id

    @property
    def strategy_type(self) -> str:
        """Return the stable strategy type key."""

        return THRESHOLD_SIGNAL_STRATEGY_TYPE

    @property
    def strategy_version(self) -> str:
        """Return the strategy implementation version."""

        return THRESHOLD_SIGNAL_STRATEGY_VERSION

    @property
    def configuration_schema_version(self) -> int:
        """Return the strategy configuration schema version."""

        return THRESHOLD_SIGNAL_CONFIGURATION_SCHEMA_VERSION

    @property
    def subscribed_event_types(self) -> tuple[str, ...]:
        """Return the canonical market data event types consumed by this strategy."""

        return (MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,)

    @property
    def decisions(self) -> tuple[ThresholdSignalDecision, ...]:
        """Return generated signal decisions in event-processing order."""

        return tuple(self._decisions)

    @property
    def generated_signals(self) -> tuple[Signal, ...]:
        """Return canonical signals emitted by this strategy."""

        return tuple(decision.signal for decision in self._decisions)

    @property
    def shutdown_reason(self) -> str | None:
        """Return the most recent controlled shutdown reason."""

        return self._shutdown_reason

    async def initialize(self, context: StrategyContext) -> None:
        """Bind the approved strategy context for signal publication."""

        self._context = context

    async def on_event(self, event: object) -> None:
        """Process one typed order-book snapshot event."""

        if not isinstance(event, OrderBookSnapshotEvent):
            return
        if self._configuration.market_id is not None and (
            event.snapshot.market_id != self._configuration.market_id
        ):
            return
        snapshot = event.snapshot
        if not snapshot.is_valid or not snapshot.asks:
            return

        best_ask = snapshot.asks[0].price
        if best_ask >= self._configuration.threshold_probability:
            return

        context = self._require_context()
        signal = self._build_signal(event=event, best_ask=best_ask, context=context)
        await context.publish_signal(signal)
        self._decisions.append(
            ThresholdSignalDecision(
                market_id=snapshot.market_id,
                contract_id=snapshot.contract_id,
                exchange=snapshot.exchange,
                best_ask=best_ask,
                threshold_probability=self._configuration.threshold_probability,
                signal=signal,
            )
        )

    async def shutdown(self, reason: str) -> None:
        """Record controlled shutdown reason without order side effects."""

        self._shutdown_reason = reason

    def _build_signal(
        self,
        *,
        event: OrderBookSnapshotEvent,
        best_ask: Decimal,
        context: StrategyContext,
    ) -> Signal:
        snapshot = event.snapshot
        strength = self._configuration.threshold_probability - best_ask
        return Signal(
            signal_id=self._signal_id(event=event, best_ask=best_ask),
            strategy_id=self.strategy_id,
            market_id=snapshot.market_id,
            contract_id=snapshot.contract_id,
            outcome_id=None,
            signal_type=self._configuration.signal_type,
            direction=SignalDirection.BUY,
            strength=strength,
            fair_probability=self._configuration.threshold_probability,
            confidence=self._configuration.confidence,
            valid_from=context.now(),
            valid_until=None,
            model_id=None,
            model_version=None,
            feature_snapshot_id=None,
            reason_code=self._configuration.reason_code,
            reason_text=self._configuration.reason_text
            or (
                f"Best ask {best_ask} is below threshold "
                f"{self._configuration.threshold_probability}."
            ),
            correlation_id=event.envelope.correlation_id,
        )

    def _signal_id(self, *, event: OrderBookSnapshotEvent, best_ask: Decimal) -> SignalId:
        snapshot = event.snapshot
        key = "|".join(
            (
                str(self.strategy_id),
                str(event.envelope.event_id),
                str(event.envelope.correlation_id),
                str(snapshot.market_id),
                str(snapshot.contract_id),
                str(best_ask),
                str(self._configuration.threshold_probability),
                self._configuration.signal_type,
            )
        )
        digest = sha256(key.encode("ascii")).hexdigest()[:32]
        return SignalId(f"{SignalId.prefix}threshold_{digest}")

    def _require_context(self) -> StrategyContext:
        if self._context is None:
            raise StrategyContextError(
                "Threshold signal strategy has not been initialized",
                reason_code="threshold_signal_not_initialized",
                context={"strategy_id": str(self.strategy_id)},
            )
        return self._context


class ThresholdSignalFactory:
    """Create threshold signal strategy instances from validated configuration."""

    def create(
        self,
        *,
        strategy_id: StrategyId,
        configuration: object,
    ) -> ThresholdSignalStrategy:
        """Return a threshold signal strategy instance."""

        if not isinstance(configuration, ThresholdSignalConfiguration):
            msg = "configuration must be a ThresholdSignalConfiguration"
            raise TypeError(msg)
        return ThresholdSignalStrategy(strategy_id=strategy_id, configuration=configuration)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
