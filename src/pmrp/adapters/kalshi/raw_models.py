"""Kalshi raw payload models."""

from __future__ import annotations

import json
from collections.abc import Mapping
from json import JSONDecodeError
from typing import Self

from pydantic import Field, field_serializer, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
from pmrp.schemas.time import UTCDateTime

_KALSHI_TEXT_MAX_LENGTH = 4096
_KALSHI_TICKER_MAX_LENGTH = 256


class KalshiRawMarket(CanonicalModel):
    """Raw Kalshi market-listing item before canonical mapping."""

    ticker: str = Field(min_length=1, max_length=_KALSHI_TICKER_MAX_LENGTH)
    event_ticker: str | None = Field(
        default=None,
        min_length=1,
        max_length=_KALSHI_TICKER_MAX_LENGTH,
    )
    market_type: str | None = Field(default=None, min_length=1, max_length=128)

    title: str = Field(min_length=1, max_length=512)
    subtitle: str | None = Field(default=None, min_length=1, max_length=512)
    category: str | None = Field(default=None, min_length=1, max_length=128)

    status: str = Field(min_length=1, max_length=128)

    open_time: UTCDateTime | None = None
    close_time: UTCDateTime | None = None
    expiration_time: UTCDateTime | None = None
    expected_expiration_time: UTCDateTime | None = None

    yes_bid: int | None = Field(default=None, ge=0, le=100)
    yes_ask: int | None = Field(default=None, ge=0, le=100)
    no_bid: int | None = Field(default=None, ge=0, le=100)
    no_ask: int | None = Field(default=None, ge=0, le=100)
    last_price: int | None = Field(default=None, ge=0, le=100)

    volume: int | None = Field(default=None, ge=0)
    open_interest: int | None = Field(default=None, ge=0)

    tick_size: int | None = Field(default=None, gt=0, le=100)
    minimum_order_size: int | None = Field(default=None, gt=0)

    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build a raw model from one decoded Kalshi market payload."""

        model_payload = {
            field_name: payload[field_name]
            for field_name in cls.model_fields
            if field_name != "raw_payload" and field_name in payload
        }
        return cls.model_validate({**model_payload, "raw_payload": payload})

    @field_validator(
        "ticker",
        "event_ticker",
        "market_type",
        "title",
        "subtitle",
        "category",
        "status",
    )
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Kalshi raw market text field")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        try:
            return freeze_canonical_mapping(value, field_name="kalshi raw market payload")
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_market_time_ordering(self) -> Self:
        if (
            self.open_time is not None
            and self.close_time is not None
            and self.close_time < self.open_time
        ):
            msg = "close_time must not precede open_time"
            raise ValueError(msg)
        return self


class KalshiMarketListResponse(CanonicalModel):
    """Raw Kalshi market-list response before canonical mapping."""

    markets: tuple[KalshiRawMarket, ...]
    cursor: str | None = Field(default=None, min_length=1, max_length=_KALSHI_TICKER_MAX_LENGTH)
    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build a market-list response from a decoded Kalshi payload."""

        markets_payload = payload.get("markets")
        if not isinstance(markets_payload, list | tuple):
            msg = "Kalshi market list payload must contain a markets array"
            raise ValueError(msg)
        markets = tuple(_market_from_payload(item) for item in markets_payload)
        return cls.model_validate(
            {
                "markets": markets,
                "cursor": payload.get("cursor"),
                "raw_payload": payload,
            }
        )

    @field_validator("cursor")
    @classmethod
    def validate_cursor(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Kalshi market-list cursor")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        try:
            return freeze_canonical_mapping(value, field_name="kalshi market-list payload")
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_unique_market_tickers(self) -> Self:
        tickers = [market.ticker for market in self.markets]
        if len(set(tickers)) != len(tickers):
            msg = "Kalshi market-list response must not contain duplicate tickers"
            raise ValueError(msg)
        return self


def parse_kalshi_market_list_json(payload_text: str) -> KalshiMarketListResponse:
    """Parse a Kalshi market-list JSON payload into immutable raw models."""

    try:
        payload = json.loads(payload_text)
    except JSONDecodeError as exc:
        msg = "Kalshi market-list payload must be valid JSON"
        raise ValueError(msg) from exc
    if not isinstance(payload, Mapping):
        msg = "Kalshi market-list payload must be a JSON object"
        raise ValueError(msg)
    return KalshiMarketListResponse.from_exchange_payload(payload)


def _market_from_payload(value: object) -> KalshiRawMarket:
    if not isinstance(value, Mapping):
        msg = "Kalshi market-list markets must contain JSON objects"
        raise ValueError(msg)
    return KalshiRawMarket.from_exchange_payload(value)


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    if len(value) > _KALSHI_TEXT_MAX_LENGTH:
        msg = f"{field_name} must be at most {_KALSHI_TEXT_MAX_LENGTH} characters"
        raise ValueError(msg)
    return value
