"""Shared adapter request contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import Environment, MarketStatus
from pmrp.schemas.identifiers import CorrelationId
from pmrp.schemas.time import UTCDateTime

_ADAPTER_LABEL_MAX_LENGTH = 128
_ADAPTER_OPAQUE_ID_MAX_LENGTH = 256


class MarketDataChannel(StrEnum):
    """Common market-data stream channels exposed through adapters."""

    ORDER_BOOK = "order_book"
    TRADES = "trades"


class MarketListRequest(CanonicalModel):
    """Exchange market-listing request before adapter-specific translation."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    environment: Environment

    requested_at: UTCDateTime
    correlation_id: CorrelationId

    limit: int | None = Field(default=None, gt=0)
    cursor: str | None = Field(default=None, min_length=1, max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH)
    status_filter: tuple[MarketStatus, ...] = ()
    include_closed: bool = False

    @field_validator("exchange", "cursor")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="market-list request text field")

    @model_validator(mode="after")
    def validate_unique_status_filter(self) -> Self:
        _validate_unique_values(self.status_filter, field_name="status_filter")
        return self


class MarketSubscription(CanonicalModel):
    """Market-data subscription request before adapter-specific translation."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    environment: Environment

    exchange_market_id: str = Field(min_length=1, max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH)
    exchange_contract_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )

    channels: tuple[MarketDataChannel, ...] = Field(min_length=1)
    depth: int | None = Field(default=None, gt=0)

    requested_at: UTCDateTime
    correlation_id: CorrelationId

    @field_validator("exchange", "exchange_market_id", "exchange_contract_id")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="market subscription text field")

    @model_validator(mode="after")
    def validate_unique_channels(self) -> Self:
        _validate_unique_values(self.channels, field_name="channels")
        return self


def _validate_unique_values(values: tuple[object, ...], *, field_name: str) -> None:
    if len(set(values)) != len(values):
        msg = f"{field_name} must not contain duplicate values"
        raise ValueError(msg)


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
