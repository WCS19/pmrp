"""Factories for canonical event envelopes."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from pmrp.clock import Clock
from pmrp.schemas.enums import DataQualityFlag
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.identifiers import (
    AccountId,
    CausationRef,
    CorrelationId,
    EventId,
    MarketId,
    OrderId,
    ReplaySessionId,
    SimulationSessionId,
    StrategyId,
)

from .registry import EventTypeRegistry

_CROCKFORD_BASE32 = "0123456789abcdefghjkmnpqrstvwxyz"
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class EventIdentifierGenerator(Protocol):
    """Generator for event factory identifiers."""

    def event_id(self, timestamp: datetime) -> EventId: ...

    def correlation_id(self, timestamp: datetime) -> CorrelationId: ...


class PrefixedUlidIdentifierGenerator:
    """Generate prefixed ULID-shaped identifiers using caller-provided time."""

    def event_id(self, timestamp: datetime) -> EventId:
        return EventId(f"{EventId.prefix}{_ulid_suffix(timestamp)}")

    def correlation_id(self, timestamp: datetime) -> CorrelationId:
        return CorrelationId(f"{CorrelationId.prefix}{_ulid_suffix(timestamp)}")


class DeterministicEventIdentifierGenerator:
    """Predictable identifier generator for deterministic tests and replays."""

    def __init__(self, *, event_counter: int = 0, correlation_counter: int = 0) -> None:
        self._event_counter = event_counter
        self._correlation_counter = correlation_counter

    def event_id(self, timestamp: datetime) -> EventId:
        del timestamp
        self._event_counter += 1
        return EventId(f"{EventId.prefix}test_{self._event_counter:024d}")

    def correlation_id(self, timestamp: datetime) -> CorrelationId:
        del timestamp
        self._correlation_counter += 1
        return CorrelationId(f"{CorrelationId.prefix}test_{self._correlation_counter:024d}")


class EventFactory:
    """Create canonical event envelopes using injected clock and registry state."""

    def __init__(
        self,
        *,
        clock: Clock,
        registry: EventTypeRegistry,
        identifier_generator: EventIdentifierGenerator | None = None,
    ) -> None:
        self._clock = clock
        self._registry = registry
        self._identifier_generator = identifier_generator or PrefixedUlidIdentifierGenerator()

    def create_envelope(
        self,
        *,
        event_type: str,
        producer: str,
        occurred_at: datetime | None = None,
        received_at: datetime | None = None,
        exchange: str | None = None,
        market_id: MarketId | None = None,
        account_id: AccountId | None = None,
        strategy_id: StrategyId | None = None,
        order_id: OrderId | None = None,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationRef | None = None,
        trace_id: str | None = None,
        replay_session_id: ReplaySessionId | None = None,
        simulation_session_id: SimulationSessionId | None = None,
        quality_flags: tuple[DataQualityFlag, ...] = (),
        attributes: Mapping[str, object] | None = None,
    ) -> EventEnvelope:
        published_at = self._clock.now()
        event_id = self._identifier_generator.event_id(published_at)
        effective_correlation_id = correlation_id or self._identifier_generator.correlation_id(
            published_at
        )
        effective_received_at = received_at or published_at
        effective_occurred_at = occurred_at or effective_received_at

        return EventEnvelope(
            event_id=event_id,
            event_type=event_type,
            schema_version=self._registry.schema_version_for(event_type),
            occurred_at=effective_occurred_at,
            received_at=effective_received_at,
            published_at=published_at,
            producer=producer,
            exchange=exchange,
            market_id=market_id,
            account_id=account_id,
            strategy_id=strategy_id,
            order_id=order_id,
            correlation_id=effective_correlation_id,
            causation_id=causation_id,
            trace_id=trace_id,
            replay_session_id=replay_session_id,
            simulation_session_id=simulation_session_id,
            quality_flags=quality_flags,
            attributes=attributes or {},
        )


def _ulid_suffix(timestamp: datetime) -> str:
    timestamp_ms = _timestamp_milliseconds(timestamp)
    random_part = int.from_bytes(secrets.token_bytes(10), byteorder="big")
    return _encode_crockford_base32((timestamp_ms << 80) | random_part, length=26)


def _timestamp_milliseconds(timestamp: datetime) -> int:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        msg = "identifier timestamp must be timezone-aware"
        raise ValueError(msg)
    delta = timestamp.astimezone(UTC) - _UNIX_EPOCH
    timestamp_ms = (
        (delta.days * 24 * 60 * 60 * 1000) + (delta.seconds * 1000) + (delta.microseconds // 1000)
    )
    if timestamp_ms < 0 or timestamp_ms >= 2**48:
        msg = "identifier timestamp is outside ULID timestamp range"
        raise ValueError(msg)
    return timestamp_ms


def _encode_crockford_base32(value: int, *, length: int) -> str:
    return "".join(
        _CROCKFORD_BASE32[(value >> shift) & 0b11111] for shift in range((length - 1) * 5, -1, -5)
    )
