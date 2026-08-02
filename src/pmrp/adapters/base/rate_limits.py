"""Shared adapter rate-limit contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.adapters.base.errors import AdapterEndpointCategory
from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.time import UTCDateTime, parse_utc_datetime

_ADAPTER_LABEL_MAX_LENGTH = 128


class AdapterRateLimitRule(CanonicalModel):
    """Configured per-adapter rate-limit window."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    endpoint_category: AdapterEndpointCategory
    operation: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    window_name: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)

    limit: int = Field(gt=0)
    window_seconds: int = Field(gt=0)
    cost: int = Field(default=1, gt=0)

    @field_validator("exchange", "operation", "window_name")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        return _validate_required_text(value, field_name="adapter rate-limit rule text field")

    @model_validator(mode="after")
    def validate_cost_within_limit(self) -> Self:
        if self.cost > self.limit:
            msg = "rate-limit cost must not exceed limit"
            raise ValueError(msg)
        return self


class AdapterRateLimitDecision(CanonicalModel):
    """Deterministic rate-limit check result for one adapter operation."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    endpoint_category: AdapterEndpointCategory
    operation: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    window_name: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)

    allowed: bool
    cost: int = Field(gt=0)
    limit: int = Field(gt=0)
    remaining_before: int = Field(ge=0)
    remaining_after: int = Field(ge=0)

    decided_at: UTCDateTime
    resets_at: UTCDateTime | None = None
    retry_after_seconds: int | None = Field(default=None, ge=0)

    @field_validator("exchange", "operation", "window_name")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        return _validate_required_text(value, field_name="adapter rate-limit decision text field")

    @model_validator(mode="after")
    def validate_decision_identity(self) -> Self:
        if self.cost > self.limit:
            msg = "rate-limit cost must not exceed limit"
            raise ValueError(msg)
        if self.remaining_before > self.limit or self.remaining_after > self.limit:
            msg = "remaining rate-limit capacity must not exceed limit"
            raise ValueError(msg)
        if self.resets_at is not None and self.resets_at < self.decided_at:
            msg = "resets_at must not precede decided_at"
            raise ValueError(msg)
        if self.allowed:
            expected_remaining = self.remaining_before - self.cost
            if expected_remaining < 0 or self.remaining_after != expected_remaining:
                msg = "allowed rate-limit decision must consume cost from remaining capacity"
                raise ValueError(msg)
            if self.retry_after_seconds is not None:
                msg = "allowed rate-limit decision must not include retry_after_seconds"
                raise ValueError(msg)
        elif self.remaining_after != self.remaining_before:
            msg = "blocked rate-limit decision must preserve remaining capacity"
            raise ValueError(msg)
        return self


def evaluate_rate_limit(
    rule: AdapterRateLimitRule,
    *,
    remaining: int,
    decided_at: datetime,
    resets_at: datetime | None = None,
    cost: int | None = None,
) -> AdapterRateLimitDecision:
    """Evaluate one rate-limit check without reading wall-clock time."""

    actual_cost = rule.cost if cost is None else _validate_positive_int(cost, field_name="cost")
    decided_at_utc = parse_utc_datetime(decided_at)
    resets_at_utc = parse_utc_datetime(resets_at) if resets_at is not None else None
    allowed = remaining >= actual_cost

    return AdapterRateLimitDecision(
        exchange=rule.exchange,
        endpoint_category=rule.endpoint_category,
        operation=rule.operation,
        window_name=rule.window_name,
        allowed=allowed,
        cost=actual_cost,
        limit=rule.limit,
        remaining_before=remaining,
        remaining_after=remaining - actual_cost if allowed else remaining,
        decided_at=decided_at_utc,
        resets_at=resets_at_utc,
        retry_after_seconds=None
        if allowed
        else _retry_after_seconds(decided_at_utc, resets_at_utc),
    )


def _retry_after_seconds(decided_at: datetime, resets_at: datetime | None) -> int | None:
    if resets_at is None:
        return None
    delta = resets_at - decided_at
    total_microseconds = (
        delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds
    )
    return max(0, (total_microseconds + 999_999) // 1_000_000)


def _validate_positive_int(value: int, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field_name} must be an integer"
        raise TypeError(msg)
    if value <= 0:
        msg = f"{field_name} must be positive"
        raise ValueError(msg)
    return value


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
