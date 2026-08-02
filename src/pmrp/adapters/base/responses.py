"""Shared adapter response and raw payload contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Self

from pydantic import Field, field_serializer, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import Environment, MarketStatus
from pmrp.schemas.immutability import freeze_string_mapping, thaw_string_mapping
from pmrp.schemas.time import UTCDateTime

_ADAPTER_LABEL_MAX_LENGTH = 128
_ADAPTER_OPAQUE_ID_MAX_LENGTH = 256
_ADAPTER_TEXT_MAX_LENGTH = 4096
_CONTENT_TYPE_MAX_LENGTH = 128
_PAYLOAD_HASH_MAX_LENGTH = 128


class RawExchangeEvent(CanonicalModel):
    """Raw exchange payload emitted by an adapter before normalization."""

    raw_record_id: str = Field(min_length=1, max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH)
    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    environment: Environment

    connection_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )
    endpoint: str | None = Field(default=None, min_length=1, max_length=_ADAPTER_TEXT_MAX_LENGTH)
    channel: str | None = Field(default=None, min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    message_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_LABEL_MAX_LENGTH,
    )

    received_at: UTCDateTime
    exchange_occurred_at: UTCDateTime | None = None
    sequence: int | None = Field(default=None, ge=0)

    content_type: str = Field(default="application/json", min_length=1, max_length=128)
    compression: str | None = Field(default=None, min_length=1, max_length=_CONTENT_TYPE_MAX_LENGTH)

    payload_text: str | None = Field(default=None, min_length=1)
    payload_bytes_b64: str | None = Field(default=None, min_length=1)
    payload_hash: str = Field(min_length=1, max_length=_PAYLOAD_HASH_MAX_LENGTH)

    parser_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_LABEL_MAX_LENGTH,
    )
    transport_metadata: Mapping[str, str] = Field(default_factory=dict)

    @field_validator(
        "raw_record_id",
        "exchange",
        "connection_id",
        "endpoint",
        "channel",
        "message_type",
        "content_type",
        "compression",
        "payload_text",
        "payload_bytes_b64",
        "payload_hash",
        "parser_version",
    )
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="raw exchange event text field")

    @field_validator("transport_metadata")
    @classmethod
    def validate_transport_metadata(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        return freeze_string_mapping(value, field_name="transport_metadata")

    @field_serializer("transport_metadata")
    def serialize_transport_metadata(self, value: Mapping[str, str]) -> dict[str, str]:
        return thaw_string_mapping(value)

    @model_validator(mode="after")
    def validate_payload_storage(self) -> Self:
        if (self.payload_text is None) == (self.payload_bytes_b64 is None):
            msg = "exactly one of payload_text or payload_bytes_b64 must be populated"
            raise ValueError(msg)
        return self


class RawMarket(CanonicalModel):
    """Raw market-listing item returned by an adapter."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    environment: Environment
    exchange_market_id: str = Field(min_length=1, max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH)
    exchange_event_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )
    status: MarketStatus | None = None
    title: str | None = Field(default=None, min_length=1, max_length=512)
    raw_event: RawExchangeEvent

    @field_validator("exchange", "exchange_market_id", "exchange_event_id", "title")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="raw market text field")

    @model_validator(mode="after")
    def validate_raw_event_scope(self) -> Self:
        _validate_raw_event_scope(
            self.raw_event, exchange=self.exchange, environment=self.environment
        )
        return self


class RawOpenOrder(CanonicalModel):
    """Raw open-order item returned by an adapter."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    environment: Environment
    exchange_order_id: str = Field(min_length=1, max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH)
    client_order_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )
    exchange_market_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )
    raw_event: RawExchangeEvent

    @field_validator("exchange", "exchange_order_id", "client_order_id", "exchange_market_id")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="raw open order text field")

    @model_validator(mode="after")
    def validate_raw_event_scope(self) -> Self:
        _validate_raw_event_scope(
            self.raw_event, exchange=self.exchange, environment=self.environment
        )
        return self


class RawPosition(CanonicalModel):
    """Raw account position item returned by an adapter."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    environment: Environment
    exchange_position_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )
    exchange_market_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )
    exchange_contract_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )
    raw_event: RawExchangeEvent

    @field_validator(
        "exchange", "exchange_position_id", "exchange_market_id", "exchange_contract_id"
    )
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="raw position text field")

    @model_validator(mode="after")
    def validate_raw_event_scope(self) -> Self:
        _validate_raw_event_scope(
            self.raw_event, exchange=self.exchange, environment=self.environment
        )
        return self


class RawBalance(CanonicalModel):
    """Raw account balance item returned by an adapter."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    environment: Environment
    exchange_account_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )
    currency: str | None = Field(default=None, min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    raw_event: RawExchangeEvent

    @field_validator("exchange", "exchange_account_id", "currency")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="raw balance text field")

    @model_validator(mode="after")
    def validate_raw_event_scope(self) -> Self:
        _validate_raw_event_scope(
            self.raw_event, exchange=self.exchange, environment=self.environment
        )
        return self


class RawFill(CanonicalModel):
    """Raw fill item returned by an adapter."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)
    environment: Environment
    exchange_fill_id: str = Field(min_length=1, max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH)
    exchange_order_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_ADAPTER_OPAQUE_ID_MAX_LENGTH,
    )
    raw_event: RawExchangeEvent

    @field_validator("exchange", "exchange_fill_id", "exchange_order_id")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="raw fill text field")

    @model_validator(mode="after")
    def validate_raw_event_scope(self) -> Self:
        _validate_raw_event_scope(
            self.raw_event, exchange=self.exchange, environment=self.environment
        )
        return self


def _validate_raw_event_scope(
    raw_event: RawExchangeEvent,
    *,
    exchange: str,
    environment: Environment,
) -> None:
    if raw_event.exchange != exchange:
        msg = "raw_event exchange must match wrapper exchange"
        raise ValueError(msg)
    if raw_event.environment is not environment:
        msg = "raw_event environment must match wrapper environment"
        raise ValueError(msg)


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
