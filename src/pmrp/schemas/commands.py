"""Canonical command envelope schema."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import Field, field_serializer, field_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.identifiers import CausationRef, CommandId, CorrelationId
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
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

    attributes: Mapping[str, object] = Field(default_factory=dict)

    @field_validator("attributes")
    @classmethod
    def validate_attributes(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return freeze_canonical_mapping(value, field_name="command attributes")

    @field_serializer("attributes")
    def serialize_attributes(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)
