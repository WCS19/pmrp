"""Approved dependency context exposed to strategy implementations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Protocol

from pmrp.bus.protocol import EventBus, EventSubscription
from pmrp.clock import Clock
from pmrp.clock.protocol import normalize_clock_datetime
from pmrp.schemas.identifiers import ReplaySessionId, SimulationSessionId, StrategyId
from pmrp.schemas.immutability import freeze_canonical_mapping
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.strategy import Signal
from pmrp.strategies.errors import StrategyContextError, StrategyEmissionError

APPROVED_STRATEGY_CONTEXT_SERVICES = frozenset(
    {
        "feature_store",
        "logger",
        "market_data",
        "metrics",
        "portfolio",
        "risk",
    }
)
FORBIDDEN_STRATEGY_CONTEXT_SERVICES = frozenset(
    {
        "database_session",
        "env",
        "environment",
        "exchange_client",
        "http_client",
        "raw_http_client",
        "secret_manager",
        "secrets",
    }
)
_SENSITIVE_METADATA_KEY_PARTS = ("api_key", "password", "private_key", "secret", "token")


class StrategySignalPublisher(Protocol):
    """Approved sink for canonical strategy signals."""

    async def publish_signal(self, signal: Signal) -> None:
        """Publish a canonical signal emitted by the active strategy."""
        ...


class StrategyOrderIntentPublisher(Protocol):
    """Approved sink for pre-risk order intents."""

    async def publish_order_intent(self, intent: OrderIntent) -> None:
        """Publish a canonical order intent for centralized risk evaluation."""
        ...


class StrategyMetrics(Protocol):
    """Minimal metrics interface exposed through approved context services."""

    def increment(self, name: str, *, tags: Mapping[str, str] | None = None) -> None:
        """Increment a named strategy metric."""
        ...

    def gauge(
        self,
        name: str,
        value: int | Decimal,
        *,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Record a named strategy gauge value without float inputs."""
        ...


class StrategyLogger(Protocol):
    """Structured logger interface exposed through approved context services."""

    def info(self, message: str, *, context: Mapping[str, object] | None = None) -> None:
        """Write an informational strategy log entry."""
        ...

    def warning(self, message: str, *, context: Mapping[str, object] | None = None) -> None:
        """Write a warning strategy log entry."""
        ...

    def error(self, message: str, *, context: Mapping[str, object] | None = None) -> None:
        """Write an error strategy log entry."""
        ...


@dataclass(frozen=True, slots=True, init=False)
class StrategyContext:
    """Immutable runtime context containing only approved strategy services."""

    _clock: Clock = field(repr=False, compare=False)
    _event_bus: EventBus = field(repr=False, compare=False)
    _signal_publisher: StrategySignalPublisher = field(repr=False, compare=False)
    _order_intent_publisher: StrategyOrderIntentPublisher = field(
        repr=False,
        compare=False,
    )
    strategy_id: StrategyId
    order_intents_enabled: bool = True
    replay_session_id: ReplaySessionId | None = None
    simulation_session_id: SimulationSessionId | None = None
    services: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __init__(
        self,
        *,
        strategy_id: StrategyId,
        clock: Clock,
        event_bus: EventBus,
        signal_publisher: StrategySignalPublisher,
        order_intent_publisher: StrategyOrderIntentPublisher,
        order_intents_enabled: bool = True,
        replay_session_id: ReplaySessionId | None = None,
        simulation_session_id: SimulationSessionId | None = None,
        services: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        _require_identifier(strategy_id, StrategyId, field_name="strategy_id")
        _require_clock(clock)
        _require_event_bus(event_bus)
        _require_callable_dependency(
            signal_publisher,
            method_name="publish_signal",
            field_name="signal_publisher",
        )
        _require_callable_dependency(
            order_intent_publisher,
            method_name="publish_order_intent",
            field_name="order_intent_publisher",
        )
        if type(order_intents_enabled) is not bool:
            msg = "order_intents_enabled must be a bool"
            raise TypeError(msg)
        if replay_session_id is not None:
            _require_identifier(
                replay_session_id,
                ReplaySessionId,
                field_name="replay_session_id",
            )
        if simulation_session_id is not None:
            _require_identifier(
                simulation_session_id,
                SimulationSessionId,
                field_name="simulation_session_id",
            )
        context_metadata = metadata or {}
        _reject_sensitive_metadata_keys(context_metadata)
        object.__setattr__(self, "_clock", clock)
        object.__setattr__(self, "_event_bus", event_bus)
        object.__setattr__(self, "_signal_publisher", signal_publisher)
        object.__setattr__(self, "_order_intent_publisher", order_intent_publisher)
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "order_intents_enabled", order_intents_enabled)
        object.__setattr__(self, "replay_session_id", replay_session_id)
        object.__setattr__(self, "simulation_session_id", simulation_session_id)
        object.__setattr__(self, "services", _freeze_services(services or {}))
        object.__setattr__(
            self,
            "metadata",
            freeze_canonical_mapping(context_metadata, field_name="strategy context metadata"),
        )

    def now(self) -> datetime:
        """Return the current injected clock time as timezone-aware UTC."""

        return normalize_clock_datetime(self._clock.now())

    def service(self, name: str) -> object | None:
        """Return an approved optional service by name."""

        _validate_service_name(name)
        return self.services.get(name)

    def subscribe[T](
        self,
        event_type: type[T],
        *,
        consumer_name: str,
        partition_key: str | None = None,
        queue_size: int | None = None,
    ) -> EventSubscription[T]:
        """Subscribe to canonical events through the injected event bus."""

        subscription = _try_subscribe(
            self._event_bus,
            event_type,
            consumer_name=consumer_name,
            partition_key=partition_key,
            queue_size=queue_size,
        )
        if subscription is None:
            raise StrategyContextError(
                "Strategy event subscription failed",
                reason_code="strategy_context_subscription_failed",
                context={
                    "strategy_id": str(self.strategy_id),
                    "consumer_name": consumer_name,
                },
            )
        return subscription

    async def publish_signal(self, signal: Signal) -> None:
        """Publish a signal after validating strategy lineage."""

        if signal.strategy_id != self.strategy_id:
            raise StrategyEmissionError(
                "Signal strategy_id must match the active strategy context",
                reason_code="strategy_signal_strategy_id_mismatch",
                context={
                    "context_strategy_id": str(self.strategy_id),
                    "signal_strategy_id": str(signal.strategy_id),
                    "signal_id": str(signal.signal_id),
                },
            )
        published = await _try_publish_signal(self._signal_publisher, signal)
        if not published:
            raise StrategyEmissionError(
                "Strategy signal emission failed",
                reason_code="strategy_signal_emission_failed",
                context={
                    "strategy_id": str(self.strategy_id),
                    "signal_id": str(signal.signal_id),
                },
            )

    async def publish_order_intent(self, intent: OrderIntent) -> None:
        """Publish an order intent only through the approved pre-risk sink."""

        if not self.order_intents_enabled:
            raise StrategyEmissionError(
                "Order intent emission is disabled for the active strategy context",
                reason_code="strategy_order_intent_emission_disabled",
                context={
                    "strategy_id": str(self.strategy_id),
                    "intent_id": str(intent.intent_id),
                },
            )
        if intent.strategy_id != self.strategy_id:
            raise StrategyEmissionError(
                "OrderIntent strategy_id must match the active strategy context",
                reason_code="strategy_order_intent_strategy_id_mismatch",
                context={
                    "context_strategy_id": str(self.strategy_id),
                    "intent_strategy_id": str(intent.strategy_id),
                    "intent_id": str(intent.intent_id),
                },
            )
        _validate_order_intent_lineage(intent)
        published = await _try_publish_order_intent(self._order_intent_publisher, intent)
        if not published:
            raise StrategyEmissionError(
                "Strategy order intent emission failed",
                reason_code="strategy_order_intent_emission_failed",
                context={
                    "strategy_id": str(self.strategy_id),
                    "intent_id": str(intent.intent_id),
                },
            )


def _require_identifier(value: object, expected_type: type[str], *, field_name: str) -> None:
    if not isinstance(value, expected_type):
        msg = f"{field_name} must be a {expected_type.__name__}"
        raise TypeError(msg)


def _require_clock(value: object) -> None:
    if not isinstance(value, Clock):
        msg = "clock must implement the Clock protocol"
        raise TypeError(msg)


def _require_event_bus(value: object) -> None:
    _require_callable_dependency(value, method_name="subscribe", field_name="event_bus")
    _require_callable_dependency(value, method_name="publish", field_name="event_bus")


def _require_callable_dependency(value: object, *, method_name: str, field_name: str) -> None:
    if not callable(getattr(value, method_name, None)):
        msg = f"{field_name} must provide {method_name}()"
        raise TypeError(msg)


def _try_subscribe[T](
    event_bus: EventBus,
    event_type: type[T],
    *,
    consumer_name: str,
    partition_key: str | None,
    queue_size: int | None,
) -> EventSubscription[T] | None:
    try:
        return event_bus.subscribe(
            event_type,
            consumer_name=consumer_name,
            partition_key=partition_key,
            queue_size=queue_size,
        )
    except Exception:
        return None


async def _try_publish_signal(
    signal_publisher: StrategySignalPublisher,
    signal: Signal,
) -> bool:
    try:
        await signal_publisher.publish_signal(signal)
    except Exception:
        return False
    return True


async def _try_publish_order_intent(
    order_intent_publisher: StrategyOrderIntentPublisher,
    intent: OrderIntent,
) -> bool:
    try:
        await order_intent_publisher.publish_order_intent(intent)
    except Exception:
        return False
    return True


def _validate_order_intent_lineage(intent: OrderIntent) -> None:
    if not intent.signal_ids:
        raise StrategyEmissionError(
            "OrderIntent must include at least one signal_id before strategy emission",
            reason_code="strategy_order_intent_signal_lineage_missing",
            context={
                "strategy_id": str(intent.strategy_id),
                "intent_id": str(intent.intent_id),
            },
        )
    if len(set(intent.signal_ids)) != len(intent.signal_ids):
        raise StrategyEmissionError(
            "OrderIntent signal lineage must not contain duplicate signal_id values",
            reason_code="strategy_order_intent_signal_lineage_duplicate",
            context={
                "strategy_id": str(intent.strategy_id),
                "intent_id": str(intent.intent_id),
            },
        )


def _freeze_services(value: Mapping[str, object]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = "strategy context services must be a mapping"
        raise TypeError(msg)
    validated: dict[str, object] = {}
    for name, service in value.items():
        _validate_service_name(name)
        if service is None:
            msg = "strategy context service values must not be None"
            raise TypeError(msg)
        validated[name] = service
    return MappingProxyType(validated)


def _validate_service_name(name: str) -> None:
    if type(name) is not str:
        msg = "strategy context service names must be strings"
        raise TypeError(msg)
    if name == "" or name.strip() != name:
        msg = "strategy context service names must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    if (
        name in FORBIDDEN_STRATEGY_CONTEXT_SERVICES
        or name not in APPROVED_STRATEGY_CONTEXT_SERVICES
    ):
        raise StrategyContextError(
            "Strategy context service is not approved for strategy access",
            reason_code="strategy_context_service_not_approved",
            context={"service_name": name},
        )


def _reject_sensitive_metadata_keys(value: Mapping[str, object]) -> None:
    for key in value:
        if type(key) is not str:
            msg = "strategy context metadata keys must be strings"
            raise TypeError(msg)
        normalized = key.lower().replace("-", "_")
        if any(part in normalized for part in _SENSITIVE_METADATA_KEY_PARTS):
            raise StrategyContextError(
                "Strategy context metadata must not include sensitive key names",
                reason_code="strategy_context_sensitive_metadata_key",
                context={"metadata_key": key},
            )
