"""Kalshi raw payload models."""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from json import JSONDecodeError
from typing import Literal, Self

from pydantic import Field, field_serializer, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
from pmrp.schemas.time import UTCDateTime

_KALSHI_TEXT_MAX_LENGTH = 4096
_KALSHI_TICKER_MAX_LENGTH = 256

KalshiOrderBookMessageType = Literal["snapshot", "delta"]
KalshiOrderBookSide = Literal["yes", "no"]
KalshiOrderBookDeltaAction = Literal["insert", "update", "delete"]


class KalshiOrderBookSequenceStatus(StrEnum):
    """Relationship between an order-book message sequence and local state."""

    OK = "ok"
    DUPLICATE = "duplicate"
    STALE = "stale"
    GAP = "gap"
    MISSING = "missing"


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


class KalshiRawOrderBookLevel(CanonicalModel):
    """One raw Kalshi order-book price level before canonical mapping."""

    price: int = Field(ge=0, le=100)
    quantity: int = Field(ge=0)


class KalshiRawOrderBookMessage(CanonicalModel):
    """Raw Kalshi order-book snapshot or delta message before canonical mapping."""

    market_ticker: str = Field(min_length=1, max_length=_KALSHI_TICKER_MAX_LENGTH)
    message_type: KalshiOrderBookMessageType

    subscription_id: int | None = Field(default=None, ge=0)
    sequence: int | None = Field(default=None, ge=0)

    side: KalshiOrderBookSide | None = None
    price: int | None = Field(default=None, ge=0, le=100)
    quantity: int | None = Field(default=None, ge=0)
    action: KalshiOrderBookDeltaAction | None = None

    yes: tuple[KalshiRawOrderBookLevel, ...] = ()
    no: tuple[KalshiRawOrderBookLevel, ...] = ()

    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build a raw order-book message from one decoded Kalshi payload."""

        message_payload = _order_book_message_payload(payload)
        message_type = _order_book_message_type(payload)
        model_payload: dict[str, object] = {
            "market_ticker": _required_payload_item(
                message_payload,
                "market_ticker",
                field_name="Kalshi order-book market_ticker",
            ),
            "message_type": message_type,
            "subscription_id": _first_present_payload_item(
                payload,
                "sid",
                fallback_key="subscription_id",
            ),
            "sequence": _first_present_payload_item(payload, "seq", fallback_key="sequence"),
            "raw_payload": payload,
        }

        if message_type == "snapshot":
            model_payload["yes"] = _order_book_levels(message_payload.get("yes", ()))
            model_payload["no"] = _order_book_levels(message_payload.get("no", ()))
        else:
            model_payload["side"] = _required_payload_item(
                message_payload,
                "side",
                field_name="Kalshi order-book delta side",
            )
            model_payload["price"] = _required_payload_item(
                message_payload,
                "price",
                field_name="Kalshi order-book delta price",
            )
            model_payload["quantity"] = _first_present_payload_item(
                message_payload,
                "quantity",
                fallback_key="size",
            )
            model_payload["action"] = _required_payload_item(
                message_payload,
                "action",
                field_name="Kalshi order-book delta action",
            )

        return cls.model_validate(model_payload)

    @field_validator("market_ticker")
    @classmethod
    def validate_market_ticker(cls, value: str) -> str:
        validated = _validate_optional_text(value, field_name="Kalshi order-book market_ticker")
        if validated is None:
            msg = "Kalshi order-book market_ticker is required"
            raise ValueError(msg)
        return validated

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        try:
            return freeze_canonical_mapping(value, field_name="kalshi order-book payload")
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_message_shape(self) -> Self:
        if self.message_type == "snapshot":
            if self.side is not None or self.price is not None or self.action is not None:
                msg = "Kalshi order-book snapshots must not contain delta fields"
                raise ValueError(msg)
            if self.quantity is not None:
                msg = "Kalshi order-book snapshots must not contain delta quantity"
                raise ValueError(msg)
            if not self.yes and not self.no:
                msg = "Kalshi order-book snapshots must contain at least one side"
                raise ValueError(msg)
            _validate_unique_prices(self.yes, field_name="yes")
            _validate_unique_prices(self.no, field_name="no")
            return self

        if self.side is None or self.price is None or self.action is None:
            msg = "Kalshi order-book deltas must include side, price, and action"
            raise ValueError(msg)
        if self.yes or self.no:
            msg = "Kalshi order-book deltas must not contain snapshot levels"
            raise ValueError(msg)
        if self.action == "delete":
            if self.quantity not in (None, 0):
                msg = "Kalshi order-book delete deltas must not include positive quantity"
                raise ValueError(msg)
        elif self.quantity is None:
            msg = "Kalshi order-book insert and update deltas must include quantity"
            raise ValueError(msg)
        return self


class KalshiOrderBookSequenceCheck(CanonicalModel):
    """Deterministic result of checking one Kalshi order-book message sequence."""

    previous_sequence: int | None = Field(default=None, ge=0)
    expected_sequence: int | None = Field(default=None, ge=0)
    received_sequence: int | None = Field(default=None, ge=0)
    status: KalshiOrderBookSequenceStatus
    invalidates_book: bool

    @model_validator(mode="after")
    def validate_sequence_status(self) -> Self:
        if self.previous_sequence is None and self.expected_sequence is not None:
            msg = "expected_sequence must be absent when previous_sequence is absent"
            raise ValueError(msg)
        if (
            self.previous_sequence is not None
            and self.expected_sequence != self.previous_sequence + 1
        ):
            msg = "expected_sequence must equal previous_sequence plus one"
            raise ValueError(msg)
        if self.status == KalshiOrderBookSequenceStatus.GAP and not self.invalidates_book:
            msg = "sequence gaps must invalidate the local book"
            raise ValueError(msg)
        if (
            self.status == KalshiOrderBookSequenceStatus.MISSING
            and self.invalidates_book
            and self.previous_sequence is None
        ):
            msg = "missing initial sequence must not invalidate an untracked book"
            raise ValueError(msg)
        if (
            self.status != KalshiOrderBookSequenceStatus.GAP
            and self.invalidates_book
            and self.status != KalshiOrderBookSequenceStatus.MISSING
        ):
            msg = "only gaps or missing tracked sequences may invalidate the local book"
            raise ValueError(msg)
        return self


class KalshiRawTrade(CanonicalModel):
    """Raw Kalshi trade message before canonical mapping."""

    trade_id: str = Field(min_length=1, max_length=_KALSHI_TICKER_MAX_LENGTH)
    market_ticker: str = Field(min_length=1, max_length=_KALSHI_TICKER_MAX_LENGTH)

    yes_price: int | None = Field(default=None, ge=0, le=100)
    no_price: int | None = Field(default=None, ge=0, le=100)
    count: int = Field(gt=0)

    taker_side: str | None = Field(default=None, min_length=1, max_length=128)
    created_time: UTCDateTime

    subscription_id: int | None = Field(default=None, ge=0)
    sequence: int | None = Field(default=None, ge=0)

    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        """Build a raw trade message from one decoded Kalshi payload."""

        message_payload = _message_payload(payload, field_name="Kalshi trade payload")
        sequence = _first_present_payload_item(payload, "seq", fallback_key="sequence")
        if sequence is None:
            sequence = message_payload.get("sequence")

        return cls.model_validate(
            {
                "trade_id": _required_first_present_payload_item(
                    message_payload,
                    "trade_id",
                    fallback_key="id",
                    field_name="Kalshi trade_id",
                ),
                "market_ticker": _required_payload_item(
                    message_payload,
                    "market_ticker",
                    field_name="Kalshi trade market_ticker",
                ),
                "yes_price": _first_present_payload_item(
                    message_payload,
                    "yes_price",
                    fallback_key="price",
                ),
                "no_price": message_payload.get("no_price"),
                "count": _required_first_present_payload_item(
                    message_payload,
                    "count",
                    fallback_key="quantity",
                    field_name="Kalshi trade count",
                ),
                "taker_side": _first_present_payload_item(
                    message_payload,
                    "taker_side",
                    fallback_key="side",
                ),
                "created_time": _required_first_present_payload_item(
                    message_payload,
                    "created_time",
                    fallback_key="created_at",
                    field_name="Kalshi trade created_time",
                ),
                "subscription_id": _first_present_payload_item(
                    payload,
                    "sid",
                    fallback_key="subscription_id",
                ),
                "sequence": sequence,
                "raw_payload": payload,
            }
        )

    @field_validator("trade_id", "market_ticker", "taker_side")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Kalshi raw trade text field")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        try:
            return freeze_canonical_mapping(value, field_name="kalshi trade payload")
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_trade_shape(self) -> Self:
        if self.yes_price is None and self.no_price is None:
            msg = "Kalshi trades must include at least one raw price"
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


def parse_kalshi_order_book_message_json(payload_text: str) -> KalshiRawOrderBookMessage:
    """Parse a Kalshi order-book JSON payload into an immutable raw model."""

    try:
        payload = json.loads(payload_text)
    except JSONDecodeError as exc:
        msg = "Kalshi order-book payload must be valid JSON"
        raise ValueError(msg) from exc
    if not isinstance(payload, Mapping):
        msg = "Kalshi order-book payload must be a JSON object"
        raise ValueError(msg)
    return KalshiRawOrderBookMessage.from_exchange_payload(payload)


def parse_kalshi_trade_json(payload_text: str) -> KalshiRawTrade:
    """Parse a Kalshi trade JSON payload into an immutable raw model."""

    try:
        payload = json.loads(payload_text)
    except JSONDecodeError as exc:
        msg = "Kalshi trade payload must be valid JSON"
        raise ValueError(msg) from exc
    if not isinstance(payload, Mapping):
        msg = "Kalshi trade payload must be a JSON object"
        raise ValueError(msg)
    return KalshiRawTrade.from_exchange_payload(payload)


def check_kalshi_order_book_sequence(
    *,
    previous_sequence: int | None,
    message: KalshiRawOrderBookMessage,
) -> KalshiOrderBookSequenceCheck:
    """Classify a Kalshi order-book message sequence without mutating local state."""

    _validate_optional_nonnegative_int(previous_sequence, field_name="previous_sequence")
    received_sequence = message.sequence
    expected_sequence = None if previous_sequence is None else previous_sequence + 1

    if received_sequence is None:
        return KalshiOrderBookSequenceCheck(
            previous_sequence=previous_sequence,
            expected_sequence=expected_sequence,
            received_sequence=None,
            status=KalshiOrderBookSequenceStatus.MISSING,
            invalidates_book=previous_sequence is not None,
        )
    if previous_sequence is None or received_sequence == expected_sequence:
        return KalshiOrderBookSequenceCheck(
            previous_sequence=previous_sequence,
            expected_sequence=expected_sequence,
            received_sequence=received_sequence,
            status=KalshiOrderBookSequenceStatus.OK,
            invalidates_book=False,
        )
    if received_sequence == previous_sequence:
        status = KalshiOrderBookSequenceStatus.DUPLICATE
    elif received_sequence < previous_sequence:
        status = KalshiOrderBookSequenceStatus.STALE
    else:
        status = KalshiOrderBookSequenceStatus.GAP

    return KalshiOrderBookSequenceCheck(
        previous_sequence=previous_sequence,
        expected_sequence=expected_sequence,
        received_sequence=received_sequence,
        status=status,
        invalidates_book=status == KalshiOrderBookSequenceStatus.GAP,
    )


def _market_from_payload(value: object) -> KalshiRawMarket:
    if not isinstance(value, Mapping):
        msg = "Kalshi market-list markets must contain JSON objects"
        raise ValueError(msg)
    return KalshiRawMarket.from_exchange_payload(value)


def _order_book_message_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    return _message_payload(payload, field_name="Kalshi order-book payload")


def _order_book_message_type(payload: Mapping[str, object]) -> KalshiOrderBookMessageType:
    raw_message_type = _first_present_payload_item(payload, "type", fallback_key="message_type")
    if raw_message_type in ("snapshot", "orderbook_snapshot"):
        return "snapshot"
    if raw_message_type in ("delta", "orderbook_delta"):
        return "delta"
    msg = "Kalshi order-book payload type must be snapshot or delta"
    raise ValueError(msg)


def _order_book_levels(value: object) -> tuple[KalshiRawOrderBookLevel, ...]:
    if not isinstance(value, list | tuple):
        msg = "Kalshi order-book snapshot levels must be arrays"
        raise ValueError(msg)
    return tuple(_order_book_level(item) for item in value)


def _order_book_level(value: object) -> KalshiRawOrderBookLevel:
    if isinstance(value, Mapping):
        return KalshiRawOrderBookLevel.model_validate(value)
    if isinstance(value, list | tuple) and len(value) == 2:
        price, quantity = value
        return KalshiRawOrderBookLevel.model_validate({"price": price, "quantity": quantity})
    msg = "Kalshi order-book levels must be objects or [price, quantity] arrays"
    raise ValueError(msg)


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


def _message_payload(payload: Mapping[str, object], *, field_name: str) -> Mapping[str, object]:
    message_payload = payload.get("msg")
    if message_payload is None:
        return payload
    if not isinstance(message_payload, Mapping):
        msg = f"{field_name} msg must be a JSON object"
        raise ValueError(msg)
    return message_payload


def _validate_unique_prices(
    levels: tuple[KalshiRawOrderBookLevel, ...],
    *,
    field_name: str,
) -> None:
    prices = [level.price for level in levels]
    if len(set(prices)) != len(prices):
        msg = f"Kalshi order-book {field_name} side must not contain duplicate prices"
        raise ValueError(msg)


def _validate_optional_nonnegative_int(value: int | None, *, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field_name} must be an integer"
        raise TypeError(msg)
    if value < 0:
        msg = f"{field_name} must be nonnegative"
        raise ValueError(msg)


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
