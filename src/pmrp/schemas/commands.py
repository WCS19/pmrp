"""Canonical command envelope schema."""

from __future__ import annotations

from pydantic import Field

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.identifiers import CausationRef, CommandId, CorrelationId
from pmrp.schemas.time import UTCDateTime
from pmrp.schemas.versions import SchemaVersion

_DOTTED_COMMAND_TYPE_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


class CommandEnvelope(CanonicalModel):
    command_id: CommandId
    command_type: str = Field(
        min_length=1,
        max_length=128,
        pattern=_DOTTED_COMMAND_TYPE_PATTERN,
    )
    schema_version: SchemaVersion

    issued_at: UTCDateTime
    issuer: str = Field(min_length=1, max_length=128)

    correlation_id: CorrelationId
    causation_id: CausationRef | None = None
    trace_id: str | None = Field(default=None, min_length=1, max_length=128)

    idempotency_key: str = Field(min_length=1, max_length=256)
    deadline_at: UTCDateTime | None = None
    priority: int = 0

    attributes: dict[str, object] = Field(default_factory=dict)
