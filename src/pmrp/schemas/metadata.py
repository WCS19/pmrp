"""Common canonical metadata schemas."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import Field, field_serializer, field_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
from pmrp.schemas.time import UTCDateTime
from pmrp.schemas.versions import SchemaVersion


class SourceMetadata(CanonicalModel):
    producer: str = Field(min_length=1, max_length=128)
    source_type: str = Field(min_length=1, max_length=64)
    exchange: str | None = Field(default=None, min_length=1, max_length=64)
    connection_id: str | None = Field(default=None, min_length=1, max_length=128)
    endpoint: str | None = Field(default=None, min_length=1, max_length=256)
    channel: str | None = Field(default=None, min_length=1, max_length=128)
    parser_version: str | None = Field(default=None, min_length=1, max_length=64)
    mapper_version: str | None = Field(default=None, min_length=1, max_length=64)


class VersionMetadata(CanonicalModel):
    schema_version: SchemaVersion
    code_version: str | None = Field(default=None, min_length=1, max_length=128)
    model_version: str | None = Field(default=None, min_length=1, max_length=128)
    strategy_version: str | None = Field(default=None, min_length=1, max_length=128)
    configuration_hash: str | None = Field(default=None, min_length=1, max_length=256)


class AuditMetadata(CanonicalModel):
    created_at: UTCDateTime
    created_by: str = Field(min_length=1, max_length=128)
    updated_at: UTCDateTime | None = None
    updated_by: str | None = Field(default=None, min_length=1, max_length=128)


class FlexibleMetadata(CanonicalModel):
    values: Mapping[str, object] = Field(default_factory=dict)

    @field_validator("values")
    @classmethod
    def validate_values(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return freeze_canonical_mapping(value, field_name="flexible metadata")

    @field_serializer("values")
    def serialize_values(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)
