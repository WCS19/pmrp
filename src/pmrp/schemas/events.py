"""Canonical event envelope schema."""

from __future__ import annotations

from pydantic import Field

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import DataQualityFlag
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
from pmrp.schemas.time import UTCDateTime
from pmrp.schemas.versions import SchemaVersion

_DOTTED_EVENT_TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


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
    attributes: dict[str, object] = Field(default_factory=dict)
