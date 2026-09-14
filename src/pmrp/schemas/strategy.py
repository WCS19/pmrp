"""Canonical strategy and signal schemas."""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import Field, field_serializer, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import Environment, HealthStatus, StrategyState
from pmrp.schemas.identifiers import (
    ContractId,
    CorrelationId,
    FeatureSnapshotId,
    MarketId,
    ModelId,
    OutcomeId,
    SignalId,
    StrategyId,
)
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
from pmrp.schemas.numeric import Money, parse_decimal
from pmrp.schemas.time import UTCDateTime
from pmrp.schemas.versions import SchemaVersion

_STRATEGY_TEXT_MAX_LENGTH = 1024
_STRATEGY_LABEL_MAX_LENGTH = 128
_STRATEGY_HASH_MAX_LENGTH = 256
_DOTTED_EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
_IMPLEMENTATION_PATH_PATTERN = (
    r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+"
    r":[A-Za-z_][A-Za-z0-9_]*$"
)


class StrategyDefinition(CanonicalModel):
    strategy_type: str = Field(min_length=1, max_length=_STRATEGY_LABEL_MAX_LENGTH)
    version: str = Field(min_length=1, max_length=_STRATEGY_LABEL_MAX_LENGTH)

    implementation_path: str = Field(
        min_length=1,
        max_length=_STRATEGY_TEXT_MAX_LENGTH,
        pattern=_IMPLEMENTATION_PATH_PATTERN,
    )
    description: str | None = Field(
        default=None,
        min_length=1,
        max_length=_STRATEGY_TEXT_MAX_LENGTH,
    )

    configuration_schema_version: SchemaVersion
    subscribed_event_types: tuple[str, ...]

    supports_replay: bool
    supports_simulation: bool
    supports_paper: bool
    supports_shadow: bool
    supports_live: bool

    @field_validator("strategy_type", "version", "description")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_nonblank_text(value, field_name="strategy definition text field")

    @field_validator("subscribed_event_types")
    @classmethod
    def validate_subscribed_event_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_event_type_tuple(value)


class StrategyInstance(CanonicalModel):
    strategy_id: StrategyId
    strategy_type: str = Field(min_length=1, max_length=_STRATEGY_LABEL_MAX_LENGTH)
    strategy_version: str = Field(min_length=1, max_length=_STRATEGY_LABEL_MAX_LENGTH)

    name: str = Field(min_length=1, max_length=_STRATEGY_LABEL_MAX_LENGTH)
    environment: Environment
    state: StrategyState

    configuration_version: SchemaVersion
    configuration_hash: str = Field(min_length=1, max_length=_STRATEGY_HASH_MAX_LENGTH)
    capital_allocation: Money | None = None

    created_at: UTCDateTime
    started_at: UTCDateTime | None = None
    stopped_at: UTCDateTime | None = None

    health_status: HealthStatus
    health_message: str | None = Field(
        default=None,
        min_length=1,
        max_length=_STRATEGY_TEXT_MAX_LENGTH,
    )

    @field_validator(
        "strategy_type",
        "strategy_version",
        "name",
        "configuration_hash",
        "health_message",
    )
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_nonblank_text(value, field_name="strategy instance text field")

    @model_validator(mode="after")
    def validate_lifecycle_timestamps(self) -> Self:
        if self.started_at is not None and self.started_at < self.created_at:
            msg = "started_at must not be before created_at"
            raise ValueError(msg)
        if self.stopped_at is not None and self.stopped_at < self.created_at:
            msg = "stopped_at must not be before created_at"
            raise ValueError(msg)
        if (
            self.started_at is not None
            and self.stopped_at is not None
            and self.stopped_at < self.started_at
        ):
            msg = "stopped_at must not be before started_at"
            raise ValueError(msg)
        if self.state is StrategyState.CREATED and (
            self.started_at is not None or self.stopped_at is not None
        ):
            msg = "created strategy instance cannot contain lifecycle terminal timestamps"
            raise ValueError(msg)
        if self.state in {StrategyState.RUNNING, StrategyState.DEGRADED, StrategyState.DRAINING}:
            if self.started_at is None:
                msg = "active strategy instance requires started_at"
                raise ValueError(msg)
            if self.stopped_at is not None:
                msg = "active strategy instance cannot contain stopped_at"
                raise ValueError(msg)
        if self.state in {StrategyState.STOPPED, StrategyState.FAILED} and self.stopped_at is None:
            msg = "terminal strategy instance requires stopped_at"
            raise ValueError(msg)
        return self


class StrategyConfigurationRecord(CanonicalModel):
    strategy_id: StrategyId
    configuration_version: SchemaVersion
    effective_at: UTCDateTime

    configuration: Mapping[str, object]
    configuration_hash: str = Field(min_length=1, max_length=_STRATEGY_HASH_MAX_LENGTH)

    created_by: str = Field(min_length=1, max_length=_STRATEGY_LABEL_MAX_LENGTH)
    approved_by: str | None = Field(
        default=None,
        min_length=1,
        max_length=_STRATEGY_LABEL_MAX_LENGTH,
    )
    approval_required: bool = False

    @field_validator("configuration")
    @classmethod
    def validate_configuration(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return freeze_canonical_mapping(value, field_name="strategy configuration")

    @field_serializer("configuration")
    def serialize_configuration(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @field_validator("configuration_hash", "created_by", "approved_by")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_nonblank_text(value, field_name="strategy configuration text field")


class SignalDirection(StrEnum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    BUY = "buy"
    SELL = "sell"


class Signal(CanonicalModel):
    signal_id: SignalId
    strategy_id: StrategyId

    market_id: MarketId
    contract_id: ContractId | None = None
    outcome_id: OutcomeId | None = None

    signal_type: str = Field(min_length=1, max_length=128)
    direction: SignalDirection

    strength: Decimal | None = None
    fair_probability: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    confidence: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))

    valid_from: UTCDateTime
    valid_until: UTCDateTime | None = None

    model_id: ModelId | None = None
    model_version: str | None = Field(default=None, min_length=1, max_length=128)
    feature_snapshot_id: FeatureSnapshotId | None = None

    reason_code: str = Field(min_length=1, max_length=128)
    reason_text: str | None = Field(default=None, min_length=1, max_length=1024)

    correlation_id: CorrelationId

    @field_validator("strength", "fair_probability", "confidence", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="signal decimal field")

    @model_validator(mode="after")
    def validate_validity_window(self) -> Self:
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            msg = "valid_until must be after valid_from"
            raise ValueError(msg)
        return self


def _validate_event_type_tuple(value: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        msg = "subscribed_event_types must not be empty"
        raise ValueError(msg)
    if len(set(value)) != len(value):
        msg = "subscribed_event_types must contain unique event types"
        raise ValueError(msg)
    for event_type in value:
        if _DOTTED_EVENT_TYPE_PATTERN.fullmatch(event_type) is None:
            msg = "subscribed_event_types must use dotted lowercase event types"
            raise ValueError(msg)
    return tuple(value)


def _validate_nonblank_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
