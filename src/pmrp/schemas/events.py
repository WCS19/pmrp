"""Canonical event envelope schema."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Self

from pydantic import Field, field_serializer, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import DataQualityFlag, HealthStatus
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
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
from pmrp.schemas.strategy import Signal, StrategyInstance
from pmrp.schemas.time import UTCDateTime
from pmrp.schemas.versions import SchemaVersion

_DOTTED_EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
STRATEGY_STARTED_EVENT_TYPE = "strategy.started"
STRATEGY_STOPPED_EVENT_TYPE = "strategy.stopped"
STRATEGY_HEALTH_CHANGED_EVENT_TYPE = "strategy.health_changed"
STRATEGY_SIGNAL_GENERATED_EVENT_TYPE = "strategy.signal_generated"


class EventEnvelope(CanonicalModel):
    event_id: EventId
    event_type: str = Field(
        min_length=1,
        max_length=128,
        pattern=_DOTTED_EVENT_TYPE_PATTERN,
    )
    schema_version: SchemaVersion

    occurred_at: UTCDateTime
    received_at: UTCDateTime
    published_at: UTCDateTime

    producer: str = Field(min_length=1, max_length=128)
    exchange: str | None = Field(default=None, min_length=1, max_length=64)
    market_id: MarketId | None = None
    account_id: AccountId | None = None
    strategy_id: StrategyId | None = None
    order_id: OrderId | None = None

    correlation_id: CorrelationId
    causation_id: CausationRef | None = None
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)

    replay_session_id: ReplaySessionId | None = None
    simulation_session_id: SimulationSessionId | None = None

    quality_flags: tuple[DataQualityFlag, ...] = ()
    attributes: Mapping[str, object] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return freeze_canonical_mapping(value, field_name="event attributes")

    @field_serializer("attributes")
    def serialize_attributes(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)


class StrategyStartedEvent(CanonicalModel):
    envelope: EventEnvelope
    strategy: StrategyInstance

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, STRATEGY_STARTED_EVENT_TYPE)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.strategy.strategy_id,
            field_name="strategy.strategy_id",
        )
        return self


class StrategyStoppedEvent(CanonicalModel):
    envelope: EventEnvelope
    strategy_id: StrategyId
    reason: str = Field(min_length=1, max_length=1024)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return _validate_required_text(value, field_name="strategy stop reason")

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, STRATEGY_STOPPED_EVENT_TYPE)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.strategy_id,
            field_name="strategy_id",
        )
        return self


class StrategyHealthChangedEvent(CanonicalModel):
    envelope: EventEnvelope
    strategy_id: StrategyId
    previous_status: HealthStatus
    current_status: HealthStatus
    message: str | None = Field(default=None, min_length=1, max_length=1024)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="strategy health message")

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, STRATEGY_HEALTH_CHANGED_EVENT_TYPE)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.strategy_id,
            field_name="strategy_id",
        )
        if self.previous_status is self.current_status:
            msg = "strategy health change requires distinct statuses"
            raise ValueError(msg)
        return self


class SignalGeneratedEvent(CanonicalModel):
    envelope: EventEnvelope
    signal: Signal

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        _validate_event_type(self.envelope, STRATEGY_SIGNAL_GENERATED_EVENT_TYPE)
        _validate_strategy_lineage(
            self.envelope.strategy_id,
            self.signal.strategy_id,
            field_name="signal.strategy_id",
        )
        if self.envelope.market_id is not None and self.envelope.market_id != self.signal.market_id:
            msg = "event envelope market_id must match signal market_id when provided"
            raise ValueError(msg)
        return self


def _validate_event_type(envelope: EventEnvelope, expected_event_type: str) -> None:
    if envelope.event_type != expected_event_type:
        msg = f"event envelope event_type must be {expected_event_type!r}"
        raise ValueError(msg)


def _validate_strategy_lineage(
    envelope_strategy_id: StrategyId | None,
    payload_strategy_id: StrategyId,
    *,
    field_name: str,
) -> None:
    if envelope_strategy_id is None:
        msg = "event envelope strategy_id is required for strategy events"
        raise ValueError(msg)
    if envelope_strategy_id != payload_strategy_id:
        msg = f"event envelope strategy_id must match {field_name}"
        raise ValueError(msg)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_required_text(value, field_name=field_name)
