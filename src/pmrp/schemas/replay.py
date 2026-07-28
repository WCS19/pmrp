"""Canonical replay manifest, session, and result schemas."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Self

from pydantic import Field, field_serializer, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.identifiers import ReplaySessionId
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.portfolio import PortfolioSnapshot
from pmrp.schemas.time import UTCDateTime

_REPLAY_ID_MAX_LENGTH = 128
_REPLAY_HASH_MAX_LENGTH = 256
_REPLAY_TEXT_MAX_LENGTH = 1024


class ReplayManifest(CanonicalModel):
    replay_session_id: ReplaySessionId

    dataset_id: str = Field(min_length=1, max_length=_REPLAY_ID_MAX_LENGTH)
    dataset_checksum: str = Field(min_length=1, max_length=_REPLAY_HASH_MAX_LENGTH)

    starts_at: UTCDateTime
    ends_at: UTCDateTime

    speed: Decimal = Field(gt=Decimal("0"))
    deterministic: bool
    random_seed: int = Field(ge=0)

    event_ordering_policy_version: str = Field(min_length=1, max_length=64)

    strategy_versions: Mapping[str, str]
    model_versions: Mapping[str, str]

    configuration_hash: str = Field(min_length=1, max_length=_REPLAY_HASH_MAX_LENGTH)
    code_commit: str = Field(min_length=1, max_length=128)
    dependency_lock_hash: str = Field(min_length=1, max_length=_REPLAY_HASH_MAX_LENGTH)

    created_at: UTCDateTime
    created_by: str = Field(min_length=1, max_length=_REPLAY_ID_MAX_LENGTH)

    @field_validator("speed", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="replay manifest decimal field")

    @field_validator("strategy_versions", "model_versions")
    @classmethod
    def validate_version_mapping(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        _validate_string_mapping(value, field_name="version mapping")
        return MappingProxyType(dict(value))

    @field_serializer("strategy_versions", "model_versions")
    def serialize_version_mapping(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        if self.ends_at <= self.starts_at:
            msg = "ends_at must be after starts_at"
            raise ValueError(msg)
        return self


class ReplayState(StrEnum):
    CREATED = "created"
    LOADING = "loading"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplaySession(CanonicalModel):
    replay_session_id: ReplaySessionId
    manifest: ReplayManifest

    state: ReplayState

    current_time: UTCDateTime | None = None
    processed_events: int = Field(default=0, ge=0)
    rejected_events: int = Field(default=0, ge=0)

    started_at: UTCDateTime | None = None
    completed_at: UTCDateTime | None = None

    result_checksum: str | None = Field(
        default=None,
        min_length=1,
        max_length=_REPLAY_HASH_MAX_LENGTH,
    )
    failure_message: str | None = Field(
        default=None,
        min_length=1,
        max_length=_REPLAY_TEXT_MAX_LENGTH,
    )

    @model_validator(mode="after")
    def validate_session_lifecycle(self) -> Self:
        if self.replay_session_id != self.manifest.replay_session_id:
            msg = "replay_session_id must match manifest replay_session_id"
            raise ValueError(msg)
        if self.current_time is not None and (
            self.current_time < self.manifest.starts_at or self.current_time > self.manifest.ends_at
        ):
            msg = "current_time must be within the manifest replay window"
            raise ValueError(msg)
        if self.started_at is not None and self.started_at < self.manifest.created_at:
            msg = "started_at must not be before manifest created_at"
            raise ValueError(msg)
        if self.completed_at is not None and self.completed_at < self.manifest.created_at:
            msg = "completed_at must not be before manifest created_at"
            raise ValueError(msg)
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            msg = "completed_at must not be before started_at"
            raise ValueError(msg)

        if self.state in {ReplayState.RUNNING, ReplayState.PAUSED}:
            if self.started_at is None:
                msg = "active replay session requires started_at"
                raise ValueError(msg)
            if self.current_time is None:
                msg = "active replay session requires current_time"
                raise ValueError(msg)
            if self.completed_at is not None or self.result_checksum is not None:
                msg = "active replay session cannot contain terminal result fields"
                raise ValueError(msg)

        terminal_states = {
            ReplayState.COMPLETED,
            ReplayState.FAILED,
            ReplayState.CANCELLED,
        }
        if self.state in terminal_states and self.completed_at is None:
            msg = "terminal replay session requires completed_at"
            raise ValueError(msg)
        if self.state is ReplayState.COMPLETED:
            if self.started_at is None:
                msg = "completed replay session requires started_at"
                raise ValueError(msg)
            if self.result_checksum is None:
                msg = "completed replay session requires result_checksum"
                raise ValueError(msg)
            if self.failure_message is not None:
                msg = "completed replay session cannot contain failure_message"
                raise ValueError(msg)
        elif self.state is ReplayState.FAILED:
            if self.failure_message is None:
                msg = "failed replay session requires failure_message"
                raise ValueError(msg)
            if self.result_checksum is not None:
                msg = "failed replay session cannot contain result_checksum"
                raise ValueError(msg)
        elif self.result_checksum is not None:
            msg = "non-completed replay session cannot contain result_checksum"
            raise ValueError(msg)

        if self.state is not ReplayState.FAILED and self.failure_message is not None:
            msg = "non-failed replay session cannot contain failure_message"
            raise ValueError(msg)
        return self


class ReplayResult(CanonicalModel):
    replay_session_id: ReplaySessionId

    processed_events: int = Field(ge=0)
    generated_signals: int = Field(ge=0)
    generated_intents: int = Field(ge=0)
    simulated_orders: int = Field(ge=0)
    simulated_fills: int = Field(ge=0)

    final_portfolio: PortfolioSnapshot
    metrics: Mapping[str, str]

    result_checksum: str = Field(min_length=1, max_length=_REPLAY_HASH_MAX_LENGTH)
    completed_at: UTCDateTime

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        _validate_string_mapping(value, field_name="metrics")
        return MappingProxyType(dict(value))

    @field_serializer("metrics")
    def serialize_metrics(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)


def _validate_string_mapping(value: Mapping[str, str], *, field_name: str) -> None:
    for key, item in value.items():
        if key == "" or key.strip() != key:
            msg = f"{field_name} keys must be nonempty strings without surrounding whitespace"
            raise ValueError(msg)
        if item == "" or item.strip() != item:
            msg = f"{field_name} values must be nonempty strings without surrounding whitespace"
            raise ValueError(msg)
