"""Polymarket raw payload models."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from json import JSONDecodeError
from typing import Literal, Self

from pydantic import Field, field_serializer, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.time import UTCDateTime

_POLYMARKET_TEXT_MAX_LENGTH = 4096
_POLYMARKET_IDENTIFIER_MAX_LENGTH = 256

type PolymarketOrderSide = Literal["BUY", "SELL"]
type PolymarketMarketListRawPayload = Mapping[str, object] | tuple[Mapping[str, object], ...]


class PolymarketRawMarket(CanonicalModel):
    """Raw Polymarket Gamma market payload before canonical mapping."""

    market_id: str = Field(min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH)
    condition_id: str = Field(min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH)
    question_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH,
    )

    question: str = Field(min_length=1, max_length=512)
    slug: str | None = Field(default=None, min_length=1, max_length=512)
    category: str | None = Field(default=None, min_length=1, max_length=128)

    active: bool | None = None
    closed: bool | None = None
    archived: bool | None = None
    enable_order_book: bool | None = None
    neg_risk: bool | None = None

    outcomes: tuple[str, ...]
    clob_token_ids: tuple[str, ...]
    outcome_prices: tuple[Decimal, ...] = ()

    start_date: UTCDateTime | None = None
    end_date: UTCDateTime | None = None
    created_at: UTCDateTime | None = None
    updated_at: UTCDateTime | None = None

    volume: Decimal | None = Field(default=None, ge=Decimal("0"))
    liquidity: Decimal | None = Field(default=None, ge=Decimal("0"))
    order_price_min_tick_size: Decimal | None = Field(default=None, gt=Decimal("0"))
    order_min_size: Decimal | None = Field(default=None, gt=Decimal("0"))

    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build a raw market model from one decoded Gamma market payload."""

        return cls.model_validate(
            {
                "market_id": _required_payload_item(
                    payload,
                    "id",
                    field_name="Polymarket market id",
                ),
                "condition_id": _required_payload_item(
                    payload,
                    "conditionId",
                    field_name="Polymarket conditionId",
                ),
                "question_id": payload.get("questionID"),
                "question": _required_payload_item(
                    payload,
                    "question",
                    field_name="Polymarket question",
                ),
                "slug": payload.get("slug"),
                "category": payload.get("category"),
                "active": payload.get("active"),
                "closed": payload.get("closed"),
                "archived": payload.get("archived"),
                "enable_order_book": payload.get("enableOrderBook"),
                "neg_risk": _first_present_payload_item(
                    payload,
                    "negRisk",
                    fallback_key="neg_risk",
                ),
                "outcomes": _required_payload_item(
                    payload,
                    "outcomes",
                    field_name="Polymarket outcomes",
                ),
                "clob_token_ids": _required_payload_item(
                    payload,
                    "clobTokenIds",
                    field_name="Polymarket clobTokenIds",
                ),
                "outcome_prices": payload.get("outcomePrices", ()),
                "start_date": _first_present_payload_item(
                    payload,
                    "startDate",
                    fallback_key="startDateIso",
                ),
                "end_date": _first_present_payload_item(
                    payload,
                    "endDate",
                    fallback_key="endDateIso",
                ),
                "created_at": payload.get("createdAt"),
                "updated_at": payload.get("updatedAt"),
                "volume": payload.get("volume"),
                "liquidity": payload.get("liquidity"),
                "order_price_min_tick_size": payload.get("orderPriceMinTickSize"),
                "order_min_size": payload.get("orderMinSize"),
                "raw_payload": payload,
            }
        )

    @field_validator("outcomes", "clob_token_ids", mode="before")
    @classmethod
    def parse_text_arrays(cls, value: object) -> tuple[str, ...]:
        return _text_tuple_from_jsonish_array(value, field_name="Polymarket text array")

    @field_validator("outcome_prices", mode="before")
    @classmethod
    def parse_outcome_prices(cls, value: object) -> tuple[Decimal, ...]:
        return _decimal_tuple_from_jsonish_array(
            value,
            field_name="Polymarket outcomePrices",
            min_value=Decimal("0"),
            max_value=Decimal("1"),
        )

    @field_validator(
        "volume",
        "liquidity",
        "order_price_min_tick_size",
        "order_min_size",
        mode="before",
    )
    @classmethod
    def parse_optional_decimal_fields(cls, value: object) -> Decimal | None:
        return _parse_optional_decimal(value, field_name="Polymarket market decimal field")

    @field_validator(
        "market_id",
        "condition_id",
        "question_id",
        "question",
        "slug",
        "category",
    )
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Polymarket market text field")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_mapping(value, field_name="polymarket market payload")

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_outcome_token_mapping(self) -> Self:
        if len(self.outcomes) != len(self.clob_token_ids):
            msg = "Polymarket outcomes and clobTokenIds must map one-to-one"
            raise ValueError(msg)
        if self.outcome_prices and len(self.outcome_prices) != len(self.outcomes):
            msg = "Polymarket outcomePrices must map one-to-one with outcomes"
            raise ValueError(msg)
        return self


class PolymarketMarketListResponse(CanonicalModel):
    """Raw Polymarket market-list response before canonical mapping."""

    markets: tuple[PolymarketRawMarket, ...]
    next_cursor: str | None = Field(
        default=None,
        min_length=1,
        max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH,
    )
    raw_payload: PolymarketMarketListRawPayload

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object] | list[object]) -> Self:
        """Build a market-list response from decoded Gamma list payload."""

        markets_payload: object
        next_cursor: object | None = None
        if isinstance(payload, Mapping):
            markets_payload = payload.get("markets", payload.get("data"))
            next_cursor = payload.get("next_cursor")
        else:
            markets_payload = payload
        if not isinstance(markets_payload, list | tuple):
            msg = "Polymarket market-list payload must contain market objects"
            raise ValueError(msg)
        return cls.model_validate(
            {
                "markets": tuple(_market_from_payload(item) for item in markets_payload),
                "next_cursor": next_cursor,
                "raw_payload": payload,
            }
        )

    @field_validator("next_cursor")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Polymarket market-list text field")

    @field_validator("raw_payload", mode="before")
    @classmethod
    def validate_raw_payload(cls, value: object) -> PolymarketMarketListRawPayload:
        if isinstance(value, Mapping):
            return _freeze_mapping(value, field_name="polymarket market-list payload")
        if isinstance(value, list | tuple):
            return tuple(
                _freeze_mapping(item, field_name="polymarket market-list payload")
                for item in _mapping_items(value, field_name="Polymarket market-list payload")
            )
        msg = "Polymarket market-list raw_payload must be a JSON object or array"
        raise TypeError(msg)

    @field_serializer("raw_payload")
    def serialize_raw_payload(
        self,
        value: PolymarketMarketListRawPayload,
    ) -> dict[str, object] | list[dict[str, object]]:
        if isinstance(value, Mapping):
            return thaw_canonical_mapping(value)
        return [thaw_canonical_mapping(item) for item in value]

    @model_validator(mode="after")
    def validate_unique_market_ids(self) -> Self:
        market_ids = [market.market_id for market in self.markets]
        condition_ids = [market.condition_id for market in self.markets]
        if len(set(market_ids)) != len(market_ids):
            msg = "Polymarket market-list response must not contain duplicate market ids"
            raise ValueError(msg)
        if len(set(condition_ids)) != len(condition_ids):
            msg = "Polymarket market-list response must not contain duplicate condition ids"
            raise ValueError(msg)
        return self


class PolymarketRawOrderBookLevel(CanonicalModel):
    """One raw Polymarket order-book price level before canonical mapping."""

    price: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    size: Decimal = Field(ge=Decimal("0"))

    @field_validator("price", "size", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal:
        return parse_decimal(value, field_name="Polymarket order-book level decimal field")


class PolymarketRawOrderBookSnapshot(CanonicalModel):
    """Raw Polymarket CLOB order-book snapshot before canonical mapping."""

    topic: Literal["market"] | None = None
    event_type: Literal["book"] | None = None
    market: str = Field(min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH)
    asset_id: str = Field(min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH)
    timestamp: str | None = Field(
        default=None,
        min_length=1,
        max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH,
    )
    hash: str | None = Field(
        default=None, min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH
    )

    bids: tuple[PolymarketRawOrderBookLevel, ...]
    asks: tuple[PolymarketRawOrderBookLevel, ...]

    min_order_size: Decimal | None = Field(default=None, gt=Decimal("0"))
    tick_size: Decimal | None = Field(default=None, gt=Decimal("0"), le=Decimal("1"))
    neg_risk: bool | None = None
    last_trade_price: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))

    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build an order-book snapshot from decoded CLOB payload."""

        message_payload = _market_stream_payload(
            payload,
            expected_type="book",
            field_name="Polymarket order-book payload",
        )
        return cls.model_validate(
            {
                "topic": payload.get("topic"),
                "event_type": _message_type(payload),
                "market": _required_payload_item(
                    message_payload,
                    "market",
                    field_name="Polymarket order-book market",
                ),
                "asset_id": _required_any_payload_item(
                    message_payload,
                    ("asset_id", "token_id", "tokenId"),
                    field_name="Polymarket order-book asset_id",
                ),
                "timestamp": message_payload.get("timestamp"),
                "hash": message_payload.get("hash"),
                "bids": _order_book_levels(message_payload.get("bids", ())),
                "asks": _order_book_levels(message_payload.get("asks", ())),
                "min_order_size": _first_present_any_payload_item(
                    message_payload,
                    ("min_order_size", "minOrderSize"),
                ),
                "tick_size": _first_present_any_payload_item(
                    message_payload,
                    ("tick_size", "tickSize"),
                ),
                "neg_risk": _first_present_any_payload_item(
                    message_payload,
                    ("neg_risk", "negRisk"),
                ),
                "last_trade_price": _first_present_any_payload_item(
                    message_payload,
                    ("last_trade_price", "lastTradePrice"),
                ),
                "raw_payload": payload,
            }
        )

    @field_validator("min_order_size", "tick_size", "last_trade_price", mode="before")
    @classmethod
    def parse_optional_decimal_fields(cls, value: object) -> Decimal | None:
        return _parse_optional_decimal(value, field_name="Polymarket order-book decimal field")

    @field_validator("market", "asset_id", "timestamp", "hash")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Polymarket order-book text field")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_mapping(value, field_name="polymarket order-book payload")

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)


class PolymarketRawPriceChange(CanonicalModel):
    """One raw Polymarket price-change entry before canonical mapping."""

    asset_id: str = Field(min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH)
    price: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    size: Decimal = Field(ge=Decimal("0"))
    side: PolymarketOrderSide
    hash: str | None = Field(
        default=None, min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH
    )
    best_bid: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    best_ask: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build one price-change entry from decoded market-channel payload."""

        return cls.model_validate(
            {
                "asset_id": _required_any_payload_item(
                    payload,
                    ("asset_id", "token_id", "tokenId"),
                    field_name="Polymarket price-change asset_id",
                ),
                "price": _required_payload_item(
                    payload,
                    "price",
                    field_name="Polymarket price-change price",
                ),
                "size": _required_payload_item(
                    payload,
                    "size",
                    field_name="Polymarket price-change size",
                ),
                "side": _required_payload_item(
                    payload,
                    "side",
                    field_name="Polymarket price-change side",
                ),
                "hash": payload.get("hash"),
                "best_bid": _first_present_any_payload_item(payload, ("best_bid", "bestBid")),
                "best_ask": _first_present_any_payload_item(payload, ("best_ask", "bestAsk")),
            }
        )

    @field_validator("price", "size", "best_bid", "best_ask", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        return _parse_optional_decimal(value, field_name="Polymarket price-change decimal field")

    @field_validator("asset_id", "hash")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Polymarket price-change text field")


class PolymarketRawPriceChangeMessage(CanonicalModel):
    """Raw Polymarket market-channel price-change message before canonical mapping."""

    topic: Literal["market"] | None = None
    event_type: Literal["price_change"]
    market: str = Field(min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH)
    timestamp: str | None = Field(
        default=None,
        min_length=1,
        max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH,
    )
    price_changes: tuple[PolymarketRawPriceChange, ...]
    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build a price-change message from decoded market-channel payload."""

        message_payload = _market_stream_payload(
            payload,
            expected_type="price_change",
            field_name="Polymarket price-change payload",
        )
        price_changes_payload = _first_present_any_payload_item(
            message_payload,
            ("price_changes", "priceChanges"),
        )
        if not isinstance(price_changes_payload, list | tuple):
            msg = "Polymarket price-change payload must contain price_changes array"
            raise ValueError(msg)
        return cls.model_validate(
            {
                "topic": payload.get("topic"),
                "event_type": _required_message_type(payload, field_name="Polymarket price-change"),
                "market": _required_payload_item(
                    message_payload,
                    "market",
                    field_name="Polymarket price-change market",
                ),
                "timestamp": message_payload.get("timestamp"),
                "price_changes": tuple(
                    _price_change_from_payload(item) for item in price_changes_payload
                ),
                "raw_payload": payload,
            }
        )

    @field_validator("market", "timestamp")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Polymarket price-change text field")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_mapping(value, field_name="polymarket price-change payload")

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_price_changes(self) -> Self:
        if not self.price_changes:
            msg = "Polymarket price-change messages must contain at least one change"
            raise ValueError(msg)
        return self


class PolymarketRawTrade(CanonicalModel):
    """Raw Polymarket trade observation before canonical mapping."""

    topic: Literal["market"] | None = None
    event_type: Literal["last_trade_price", "trade"] | None = None
    trade_id: str | None = Field(
        default=None, min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH
    )
    market: str = Field(min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH)
    asset_id: str = Field(min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH)
    side: PolymarketOrderSide
    price: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    size: Decimal | None = Field(default=None, gt=Decimal("0"))
    fee_rate_bps: int | None = Field(default=None, ge=0)
    timestamp: str | None = Field(
        default=None,
        min_length=1,
        max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH,
    )
    status: str | None = Field(default=None, min_length=1, max_length=128)
    match_time: str | None = Field(default=None, min_length=1, max_length=128)
    last_update: str | None = Field(default=None, min_length=1, max_length=128)
    outcome: str | None = Field(default=None, min_length=1, max_length=128)
    bucket_index: int | None = Field(default=None, ge=0)
    owner: str | None = Field(
        default=None, min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH
    )
    maker_address: str | None = Field(
        default=None, min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH
    )
    transaction_hash: str | None = Field(
        default=None,
        min_length=1,
        max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH,
    )
    trader_side: str | None = Field(default=None, min_length=1, max_length=128)

    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build a trade observation from decoded CLOB trade payload."""

        message_payload = _market_stream_payload(
            payload,
            expected_type="last_trade_price",
            field_name="Polymarket trade payload",
        )
        return cls.model_validate(
            {
                "topic": payload.get("topic"),
                "event_type": _message_type(payload),
                "trade_id": message_payload.get("id"),
                "market": _required_first_present_payload_item(
                    message_payload,
                    "market",
                    fallback_key="conditionId",
                    field_name="Polymarket trade market",
                ),
                "asset_id": _required_any_payload_item(
                    message_payload,
                    ("asset_id", "asset", "token_id", "tokenId"),
                    field_name="Polymarket trade asset_id",
                ),
                "side": _required_payload_item(
                    message_payload,
                    "side",
                    field_name="Polymarket trade side",
                ),
                "price": _required_payload_item(
                    message_payload,
                    "price",
                    field_name="Polymarket trade price",
                ),
                "size": message_payload.get("size"),
                "fee_rate_bps": _first_present_any_payload_item(
                    message_payload,
                    ("fee_rate_bps", "feeRateBps"),
                ),
                "timestamp": message_payload.get("timestamp"),
                "status": message_payload.get("status"),
                "match_time": message_payload.get("match_time"),
                "last_update": message_payload.get("last_update"),
                "outcome": message_payload.get("outcome"),
                "bucket_index": message_payload.get("bucket_index"),
                "owner": message_payload.get("owner"),
                "maker_address": message_payload.get("maker_address"),
                "transaction_hash": _first_present_any_payload_item(
                    message_payload,
                    ("transaction_hash", "transactionHash"),
                ),
                "trader_side": message_payload.get("trader_side"),
                "raw_payload": payload,
            }
        )

    @field_validator("price", "size", mode="before")
    @classmethod
    def parse_decimal_fields(cls, value: object) -> Decimal | None:
        return _parse_optional_decimal(value, field_name="Polymarket trade decimal field")

    @field_validator("fee_rate_bps", "bucket_index", mode="before")
    @classmethod
    def parse_optional_int_fields(cls, value: object) -> int | None:
        return _parse_optional_nonnegative_int(value, field_name="Polymarket trade integer field")

    @field_validator(
        "trade_id",
        "market",
        "asset_id",
        "timestamp",
        "status",
        "match_time",
        "last_update",
        "outcome",
        "owner",
        "maker_address",
        "transaction_hash",
        "trader_side",
    )
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Polymarket trade text field")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_mapping(value, field_name="polymarket trade payload")

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_trade_identity(self) -> Self:
        if self.trade_id is None and self.transaction_hash is None and self.timestamp is None:
            msg = "Polymarket trades must contain trade id, transaction hash, or timestamp"
            raise ValueError(msg)
        return self


class PolymarketTradeListResponse(CanonicalModel):
    """Raw Polymarket paginated trade-list response before canonical mapping."""

    limit: int = Field(gt=0)
    next_cursor: str = Field(min_length=1, max_length=_POLYMARKET_IDENTIFIER_MAX_LENGTH)
    count: int = Field(ge=0)
    data: tuple[PolymarketRawTrade, ...]
    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build a trade-list response from decoded CLOB trades payload."""

        data_payload = payload.get("data")
        if not isinstance(data_payload, list | tuple):
            msg = "Polymarket trade-list payload must contain data array"
            raise ValueError(msg)
        return cls.model_validate(
            {
                "limit": _required_payload_item(
                    payload,
                    "limit",
                    field_name="Polymarket trade-list limit",
                ),
                "next_cursor": _required_payload_item(
                    payload,
                    "next_cursor",
                    field_name="Polymarket trade-list next_cursor",
                ),
                "count": _required_payload_item(
                    payload,
                    "count",
                    field_name="Polymarket trade-list count",
                ),
                "data": tuple(_trade_from_payload(item) for item in data_payload),
                "raw_payload": payload,
            }
        )

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_mapping(value, field_name="polymarket trade-list payload")

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_count_matches_data(self) -> Self:
        if self.count != len(self.data):
            msg = "Polymarket trade-list count must match data length"
            raise ValueError(msg)
        return self


class PolymarketRawErrorResponse(CanonicalModel):
    """Raw Polymarket error payload before adapter error classification."""

    http_status: int | None = Field(default=None, ge=100, le=599)
    error_code: str | None = Field(default=None, min_length=1, max_length=128)
    message: str | None = Field(default=None, min_length=1, max_length=1024)
    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build a raw error model from one decoded Polymarket error payload."""

        return cls.model_validate(
            {
                "http_status": _first_present_payload_item(
                    payload,
                    "http_status",
                    fallback_key="status_code",
                ),
                "error_code": _first_present_any_payload_item(
                    payload,
                    ("code", "error_code", "type"),
                ),
                "message": _first_present_payload_item(
                    payload,
                    "message",
                    fallback_key="error",
                ),
                "raw_payload": payload,
            }
        )

    @field_validator("error_code", "message")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Polymarket error text field")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_mapping(value, field_name="polymarket error payload")

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_error_shape(self) -> Self:
        if self.error_code is None and self.message is None:
            msg = "Polymarket errors must include an error code or message"
            raise ValueError(msg)
        return self


def parse_polymarket_market_list_json(payload_text: str) -> PolymarketMarketListResponse:
    """Parse a Polymarket market-list JSON payload into immutable raw models."""

    payload = _decoded_json_payload(payload_text, field_name="Polymarket market-list payload")
    if not isinstance(payload, Mapping | list):
        msg = "Polymarket market-list payload must be a JSON object or array"
        raise ValueError(msg)
    return PolymarketMarketListResponse.from_exchange_payload(payload)


def parse_polymarket_order_book_json(payload_text: str) -> PolymarketRawOrderBookSnapshot:
    """Parse a Polymarket order-book JSON payload into an immutable raw model."""

    return PolymarketRawOrderBookSnapshot.from_exchange_payload(
        _decoded_json_object(payload_text, field_name="Polymarket order-book payload")
    )


def parse_polymarket_price_change_json(payload_text: str) -> PolymarketRawPriceChangeMessage:
    """Parse a Polymarket price-change JSON payload into an immutable raw model."""

    return PolymarketRawPriceChangeMessage.from_exchange_payload(
        _decoded_json_object(payload_text, field_name="Polymarket price-change payload")
    )


def parse_polymarket_trade_json(payload_text: str) -> PolymarketRawTrade:
    """Parse a Polymarket trade JSON payload into an immutable raw model."""

    return PolymarketRawTrade.from_exchange_payload(
        _decoded_json_object(payload_text, field_name="Polymarket trade payload")
    )


def parse_polymarket_trade_list_json(payload_text: str) -> PolymarketTradeListResponse:
    """Parse a Polymarket trade-list JSON payload into immutable raw models."""

    return PolymarketTradeListResponse.from_exchange_payload(
        _decoded_json_object(payload_text, field_name="Polymarket trade-list payload")
    )


def parse_polymarket_error_json(payload_text: str) -> PolymarketRawErrorResponse:
    """Parse a Polymarket error JSON payload into an immutable raw model."""

    return PolymarketRawErrorResponse.from_exchange_payload(
        _decoded_json_object(payload_text, field_name="Polymarket error payload")
    )


def _decoded_json_payload(payload_text: str, *, field_name: str) -> object:
    try:
        return json.loads(payload_text)
    except JSONDecodeError as exc:
        msg = f"{field_name} must be valid JSON"
        raise ValueError(msg) from exc


def _decoded_json_object(payload_text: str, *, field_name: str) -> Mapping[str, object]:
    payload = _decoded_json_payload(payload_text, field_name=field_name)
    if not isinstance(payload, Mapping):
        msg = f"{field_name} must be a JSON object"
        raise ValueError(msg)
    return payload


def _market_from_payload(value: object) -> PolymarketRawMarket:
    if not isinstance(value, Mapping):
        msg = "Polymarket market-list entries must be JSON objects"
        raise ValueError(msg)
    return PolymarketRawMarket.from_exchange_payload(value)


def _order_book_levels(value: object) -> tuple[PolymarketRawOrderBookLevel, ...]:
    if not isinstance(value, list | tuple):
        msg = "Polymarket order-book levels must be arrays"
        raise ValueError(msg)
    return tuple(_order_book_level(item) for item in value)


def _order_book_level(value: object) -> PolymarketRawOrderBookLevel:
    if not isinstance(value, Mapping):
        msg = "Polymarket order-book levels must be JSON objects"
        raise ValueError(msg)
    return PolymarketRawOrderBookLevel.model_validate(value)


def _price_change_from_payload(value: object) -> PolymarketRawPriceChange:
    if not isinstance(value, Mapping):
        msg = "Polymarket price_changes entries must be JSON objects"
        raise ValueError(msg)
    return PolymarketRawPriceChange.from_exchange_payload(value)


def _trade_from_payload(value: object) -> PolymarketRawTrade:
    if not isinstance(value, Mapping):
        msg = "Polymarket trade-list data entries must be JSON objects"
        raise ValueError(msg)
    return PolymarketRawTrade.from_exchange_payload(value)


def _market_stream_payload(
    payload: Mapping[str, object],
    *,
    expected_type: str,
    field_name: str,
) -> Mapping[str, object]:
    message_payload = payload.get("payload")
    if message_payload is None:
        return payload
    if not isinstance(message_payload, Mapping):
        msg = f"{field_name} payload must be a JSON object"
        raise ValueError(msg)
    message_type = _message_type(payload)
    if message_type != expected_type:
        msg = f"{field_name} type must be {expected_type}"
        raise ValueError(msg)
    return message_payload


def _mapping_items(
    value: list[object] | tuple[object, ...], *, field_name: str
) -> tuple[Mapping[str, object], ...]:
    items: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            msg = f"{field_name} entries must be JSON objects"
            raise TypeError(msg)
        items.append(item)
    return tuple(items)


def _required_payload_item(
    payload: Mapping[str, object],
    key: str,
    *,
    field_name: str,
) -> object:
    value = payload.get(key)
    if value is None:
        msg = f"{field_name} is required"
        raise ValueError(msg)
    return value


def _required_first_present_payload_item(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback_key: str,
    field_name: str,
) -> object:
    value = _first_present_payload_item(payload, key, fallback_key=fallback_key)
    if value is None:
        msg = f"{field_name} is required"
        raise ValueError(msg)
    return value


def _first_present_payload_item(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback_key: str,
) -> object:
    value = payload.get(key)
    if value is not None:
        return value
    return payload.get(fallback_key)


def _required_any_payload_item(
    payload: Mapping[str, object],
    keys: tuple[str, ...],
    *,
    field_name: str,
) -> object:
    value = _first_present_any_payload_item(payload, keys)
    if value is None:
        msg = f"{field_name} is required"
        raise ValueError(msg)
    return value


def _first_present_any_payload_item(
    payload: Mapping[str, object],
    keys: tuple[str, ...],
) -> object:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    return None


def _required_message_type(payload: Mapping[str, object], *, field_name: str) -> object:
    message_type = _message_type(payload)
    if message_type is None:
        msg = f"{field_name} type is required"
        raise ValueError(msg)
    return message_type


def _message_type(payload: Mapping[str, object]) -> object:
    return _first_present_payload_item(payload, "event_type", fallback_key="type")


def _text_tuple_from_jsonish_array(value: object, *, field_name: str) -> tuple[str, ...]:
    items = _jsonish_array_items(value, field_name=field_name)
    text_items = []
    for item in items:
        if type(item) is not str:
            msg = f"{field_name} entries must be strings"
            raise TypeError(msg)
        text_items.append(_validate_text(item, field_name=field_name))
    return tuple(text_items)


def _decimal_tuple_from_jsonish_array(
    value: object,
    *,
    field_name: str,
    min_value: Decimal | None = None,
    max_value: Decimal | None = None,
) -> tuple[Decimal, ...]:
    items = _jsonish_array_items(value, field_name=field_name)
    decimals = tuple(parse_decimal(item, field_name=field_name) for item in items)
    for decimal in decimals:
        if min_value is not None and decimal < min_value:
            msg = f"{field_name} entries must be greater than or equal to {min_value}"
            raise ValueError(msg)
        if max_value is not None and decimal > max_value:
            msg = f"{field_name} entries must be less than or equal to {max_value}"
            raise ValueError(msg)
    return decimals


def _jsonish_array_items(value: object, *, field_name: str) -> tuple[object, ...]:
    if isinstance(value, str):
        _validate_text(value, field_name=field_name)
        try:
            decoded_value = json.loads(value)
        except JSONDecodeError as exc:
            msg = f"{field_name} must be a JSON array string"
            raise ValueError(msg) from exc
        value = decoded_value
    if not isinstance(value, list | tuple):
        msg = f"{field_name} must be an array"
        raise TypeError(msg)
    return tuple(value)


def _parse_optional_decimal(value: object, *, field_name: str) -> Decimal | None:
    if value is None:
        return None
    return parse_decimal(value, field_name=field_name)


def _parse_optional_nonnegative_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        msg = f"{field_name} must be an integer"
        raise TypeError(msg)
    if isinstance(value, int):
        parsed_value = value
    elif isinstance(value, str):
        _validate_text(value, field_name=field_name)
        try:
            parsed_value = int(value)
        except ValueError as exc:
            msg = f"{field_name} must be an integer string"
            raise ValueError(msg) from exc
    else:
        msg = f"{field_name} must be an integer or integer string"
        raise TypeError(msg)
    if parsed_value < 0:
        msg = f"{field_name} must be nonnegative"
        raise ValueError(msg)
    return parsed_value


def _freeze_mapping(value: Mapping[str, object], *, field_name: str) -> Mapping[str, object]:
    try:
        return freeze_canonical_mapping(value, field_name=field_name)
    except TypeError as exc:
        raise ValueError(str(exc)) from exc


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_text(value, field_name=field_name)


def _validate_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    if len(value) > _POLYMARKET_TEXT_MAX_LENGTH:
        msg = f"{field_name} must be at most {_POLYMARKET_TEXT_MAX_LENGTH} characters"
        raise ValueError(msg)
    return value
