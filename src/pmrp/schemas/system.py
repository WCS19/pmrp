"""Canonical system health schemas."""

from __future__ import annotations

from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import Environment, HealthStatus
from pmrp.schemas.time import UTCDateTime

_SYSTEM_LABEL_MAX_LENGTH = 128
_SYSTEM_MESSAGE_MAX_LENGTH = 1024
_TRADING_IMPACT_PATTERN = r"^(none|strategy_only|exchange_only|account_only|global)$"


class DependencyHealth(CanonicalModel):
    dependency: str = Field(min_length=1, max_length=_SYSTEM_LABEL_MAX_LENGTH)
    status: HealthStatus
    message: str | None = Field(default=None, min_length=1, max_length=_SYSTEM_MESSAGE_MAX_LENGTH)
    checked_at: UTCDateTime

    @field_validator("dependency", "message")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_nonblank_text(value, field_name="dependency health text field")


class ServiceHealth(CanonicalModel):
    service: str = Field(min_length=1, max_length=_SYSTEM_LABEL_MAX_LENGTH)
    component: str = Field(min_length=1, max_length=_SYSTEM_LABEL_MAX_LENGTH)
    environment: Environment

    status: HealthStatus
    since: UTCDateTime

    summary: str = Field(min_length=1, max_length=_SYSTEM_MESSAGE_MAX_LENGTH)
    last_success_at: UTCDateTime | None = None
    last_error_at: UTCDateTime | None = None

    dependencies: tuple[DependencyHealth, ...]

    trading_impact: str = Field(pattern=_TRADING_IMPACT_PATTERN)
    ready: bool
    alive: bool

    @field_validator("service", "component", "summary", "trading_impact")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        return _validate_required_text(value, field_name="service health text field")

    @model_validator(mode="after")
    def validate_unique_dependencies(self) -> Self:
        dependency_names = [dependency.dependency for dependency in self.dependencies]
        if len(set(dependency_names)) != len(dependency_names):
            msg = "dependencies must have unique dependency names"
            raise ValueError(msg)
        return self


class AdapterHealth(CanonicalModel):
    exchange: str = Field(min_length=1, max_length=_SYSTEM_LABEL_MAX_LENGTH)
    environment: Environment

    status: HealthStatus
    connected: bool
    authenticated: bool
    subscriptions_active: bool

    last_message_at: UTCDateTime | None = None
    last_heartbeat_at: UTCDateTime | None = None
    last_reconciliation_at: UTCDateTime | None = None

    market_data_fresh: bool
    trading_gate_open: bool

    reconnect_attempts: int = Field(ge=0)
    message: str | None = Field(default=None, min_length=1, max_length=_SYSTEM_MESSAGE_MAX_LENGTH)

    @field_validator("exchange", "message")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_nonblank_text(value, field_name="adapter health text field")


class RateLimitWindow(CanonicalModel):
    name: str = Field(min_length=1, max_length=_SYSTEM_LABEL_MAX_LENGTH)
    limit: int = Field(gt=0)
    remaining: int | None = Field(default=None, ge=0)
    resets_at: UTCDateTime | None = None
    window_seconds: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_required_text(value, field_name="rate-limit window name")

    @model_validator(mode="after")
    def validate_remaining_within_limit(self) -> Self:
        if self.remaining is not None and self.remaining > self.limit:
            msg = "remaining rate-limit capacity must not exceed limit"
            raise ValueError(msg)
        return self


class RateLimitStatus(CanonicalModel):
    exchange: str = Field(min_length=1, max_length=_SYSTEM_LABEL_MAX_LENGTH)
    measured_at: UTCDateTime
    windows: tuple[RateLimitWindow, ...]

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, value: str) -> str:
        return _validate_required_text(value, field_name="rate-limit exchange")


def _validate_nonblank_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_required_text(value, field_name=field_name)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
