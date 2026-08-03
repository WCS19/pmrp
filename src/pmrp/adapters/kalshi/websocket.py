"""Kalshi WebSocket connection contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from json import JSONDecodeError
from typing import Protocol, Self

from pydantic import Field, ValidationError, field_serializer, field_validator, model_validator

from pmrp.adapters.base.errors import AdapterEndpointCategory, AdapterProtocolError
from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.immutability import (
    freeze_canonical_mapping,
    thaw_canonical_mapping,
)
from pmrp.schemas.time import UTCDateTime, parse_utc_datetime

KALSHI_WEBSOCKET_PATH = "/trade-api/v2/ws"
KALSHI_DEFAULT_WEBSOCKET_TIMEOUT_SECONDS = 10

_KALSHI_WEBSOCKET_TEXT_MAX_LENGTH = 4096
_KALSHI_WEBSOCKET_ID_MAX_LENGTH = 256
_KALSHI_WEBSOCKET_TIMEOUT_MAX_SECONDS = 120


class KalshiWebSocketChannel(StrEnum):
    """Kalshi market-data WebSocket channels supported by the M5 slice."""

    ORDER_BOOK = "order_book"
    TRADES = "trades"


class KalshiWebSocketSequenceStatus(StrEnum):
    """Relationship between a WebSocket frame sequence and local stream state."""

    OK = "ok"
    DUPLICATE = "duplicate"
    STALE = "stale"
    GAP = "gap"
    MISSING = "missing"


class KalshiWebSocketHello(CanonicalModel):
    """Initial Kalshi WebSocket hello frame."""

    connection_id: str = Field(min_length=1, max_length=_KALSHI_WEBSOCKET_ID_MAX_LENGTH)
    heartbeat_interval_seconds: int = Field(gt=0, le=_KALSHI_WEBSOCKET_TIMEOUT_MAX_SECONDS)
    server_time: UTCDateTime | None = None
    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        return cls.model_validate(
            {
                "connection_id": _required_payload_item(
                    payload,
                    "connection_id",
                    field_name="Kalshi WebSocket connection_id",
                ),
                "heartbeat_interval_seconds": _required_payload_item(
                    payload,
                    "heartbeat_interval_seconds",
                    field_name="Kalshi WebSocket heartbeat_interval_seconds",
                ),
                "server_time": payload.get("server_time"),
                "raw_payload": payload,
            }
        )

    @field_validator("connection_id")
    @classmethod
    def validate_connection_id(cls, value: str) -> str:
        return _validate_required_text(value, field_name="Kalshi WebSocket connection_id")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_payload(value, field_name="kalshi websocket hello payload")

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)


class KalshiWebSocketSubscribePlan(CanonicalModel):
    """Replayable Kalshi market-data subscription plan."""

    request_id: str = Field(min_length=1, max_length=_KALSHI_WEBSOCKET_ID_MAX_LENGTH)
    channels: tuple[KalshiWebSocketChannel, ...] = Field(min_length=1)
    market_tickers: tuple[str, ...] = Field(min_length=1)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str) -> str:
        return _validate_required_text(value, field_name="Kalshi WebSocket request_id")

    @field_validator("market_tickers")
    @classmethod
    def validate_market_tickers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for ticker in value:
            _validate_required_text(ticker, field_name="Kalshi WebSocket market_ticker")
        return value

    @model_validator(mode="after")
    def validate_unique_values(self) -> Self:
        _validate_unique(self.channels, field_name="Kalshi WebSocket channels")
        _validate_unique(self.market_tickers, field_name="Kalshi WebSocket market_tickers")
        return self

    def to_payload(self) -> dict[str, object]:
        """Return the deterministic subscribe payload sent over the transport."""

        return {
            "type": "subscribe",
            "request_id": self.request_id,
            "channels": [channel.value for channel in self.channels],
            "market_tickers": list(self.market_tickers),
        }


class KalshiWebSocketSubscription(CanonicalModel):
    """One accepted Kalshi WebSocket subscription."""

    subscription_id: str = Field(min_length=1, max_length=_KALSHI_WEBSOCKET_ID_MAX_LENGTH)
    channel: KalshiWebSocketChannel

    @field_validator("subscription_id")
    @classmethod
    def validate_subscription_id(cls, value: str) -> str:
        return _validate_required_text(value, field_name="Kalshi WebSocket subscription_id")


class KalshiWebSocketSubscriptionAck(CanonicalModel):
    """Kalshi WebSocket subscription acknowledgement."""

    request_id: str = Field(min_length=1, max_length=_KALSHI_WEBSOCKET_ID_MAX_LENGTH)
    subscriptions: tuple[KalshiWebSocketSubscription, ...] = Field(min_length=1)
    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        subscriptions_payload = payload.get("subscriptions")
        if not isinstance(subscriptions_payload, list | tuple):
            msg = "Kalshi WebSocket subscription acknowledgement must contain subscriptions"
            raise ValueError(msg)
        return cls.model_validate(
            {
                "request_id": _required_payload_item(
                    payload,
                    "request_id",
                    field_name="Kalshi WebSocket request_id",
                ),
                "subscriptions": tuple(
                    _subscription_from_payload(item) for item in subscriptions_payload
                ),
                "raw_payload": payload,
            }
        )

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str) -> str:
        return _validate_required_text(value, field_name="Kalshi WebSocket request_id")

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_payload(value, field_name="kalshi websocket subscription ack payload")

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)

    @model_validator(mode="after")
    def validate_unique_subscription_ids(self) -> Self:
        _validate_unique(
            tuple(subscription.subscription_id for subscription in self.subscriptions),
            field_name="Kalshi WebSocket subscription ids",
        )
        return self


class KalshiWebSocketPing(CanonicalModel):
    """Kalshi WebSocket heartbeat ping frame."""

    sent_at: UTCDateTime
    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        return cls.model_validate(
            {
                "sent_at": _required_payload_item(
                    payload,
                    "sent_at",
                    field_name="Kalshi WebSocket ping sent_at",
                ),
                "raw_payload": payload,
            }
        )

    def pong_payload(self) -> dict[str, object]:
        return {"type": "pong", "sent_at": self.raw_payload["sent_at"]}

    @field_validator("raw_payload")
    @classmethod
    def validate_raw_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_payload(value, field_name="kalshi websocket ping payload")

    @field_serializer("raw_payload")
    def serialize_raw_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)


class KalshiWebSocketDataFrame(CanonicalModel):
    """Raw Kalshi WebSocket market-data frame."""

    message_type: str = Field(min_length=1, max_length=128)
    channel: KalshiWebSocketChannel
    market_ticker: str | None = Field(default=None, min_length=1, max_length=256)
    sequence: int | None = Field(default=None, ge=0)
    payload: Mapping[str, object]
    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        message_type = _frame_type(payload)
        message_payload = _message_payload(payload)
        return cls.model_validate(
            {
                "message_type": message_type,
                "channel": _data_channel(payload, message_type=message_type),
                "market_ticker": _first_present_payload_item(
                    message_payload,
                    "market_ticker",
                    fallback_key="ticker",
                ),
                "sequence": _first_present_payload_item(payload, "seq", fallback_key="sequence"),
                "payload": message_payload,
                "raw_payload": payload,
            }
        )

    @field_validator("message_type", "market_ticker")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Kalshi WebSocket data text field")

    @field_validator("payload", "raw_payload")
    @classmethod
    def validate_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_payload(value, field_name="kalshi websocket data payload")

    @field_serializer("payload", "raw_payload")
    def serialize_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)


class KalshiWebSocketSequenceCheck(CanonicalModel):
    """Deterministic result of checking a Kalshi WebSocket sequence."""

    previous_sequence: int | None = Field(default=None, ge=0)
    expected_sequence: int | None = Field(default=None, ge=0)
    received_sequence: int | None = Field(default=None, ge=0)
    status: KalshiWebSocketSequenceStatus
    invalidates_stream: bool

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
        if self.status == KalshiWebSocketSequenceStatus.GAP and not self.invalidates_stream:
            msg = "sequence gaps must invalidate the local stream"
            raise ValueError(msg)
        if (
            self.status != KalshiWebSocketSequenceStatus.GAP
            and self.invalidates_stream
            and self.status != KalshiWebSocketSequenceStatus.MISSING
        ):
            msg = "only gaps or missing tracked sequences may invalidate the local stream"
            raise ValueError(msg)
        return self


type KalshiWebSocketParsedFrame = (
    KalshiWebSocketHello
    | KalshiWebSocketSubscriptionAck
    | KalshiWebSocketPing
    | KalshiWebSocketDataFrame
)


class KalshiWebSocketTransport(Protocol):
    """Async text WebSocket transport boundary."""

    async def receive_text(self, *, timeout_seconds: int) -> str:
        """Receive one text frame using an explicit timeout."""

        ...

    async def send_json(self, payload: Mapping[str, object], *, timeout_seconds: int) -> None:
        """Send one JSON-serializable payload using an explicit timeout."""

        ...

    async def close(self) -> None:
        """Close the transport."""

        ...


class KalshiWebSocketConnection:
    """Transport-injected Kalshi WebSocket connection helper."""

    def __init__(
        self,
        *,
        transport: KalshiWebSocketTransport,
        operation_timeout_seconds: int = KALSHI_DEFAULT_WEBSOCKET_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = transport
        self._operation_timeout_seconds = _validate_timeout_seconds(operation_timeout_seconds)
        self._closed = False

    @property
    def operation_timeout_seconds(self) -> int:
        return self._operation_timeout_seconds

    async def receive_hello(self) -> KalshiWebSocketHello:
        frame = await self.receive_next_frame()
        if not isinstance(frame, KalshiWebSocketHello):
            raise AdapterProtocolError(
                "Kalshi WebSocket expected hello frame",
                exchange="kalshi",
                endpoint_category=AdapterEndpointCategory.STREAM,
            )
        return frame

    async def subscribe(
        self,
        plan: KalshiWebSocketSubscribePlan,
    ) -> KalshiWebSocketSubscriptionAck:
        await self._transport.send_json(
            plan.to_payload(),
            timeout_seconds=self._operation_timeout_seconds,
        )
        frame = await self.receive_next_frame()
        if not isinstance(frame, KalshiWebSocketSubscriptionAck):
            raise AdapterProtocolError(
                "Kalshi WebSocket expected subscription acknowledgement",
                exchange="kalshi",
                endpoint_category=AdapterEndpointCategory.STREAM,
                context={"request_id": plan.request_id},
            )
        if frame.request_id != plan.request_id:
            raise AdapterProtocolError(
                "Kalshi WebSocket subscription acknowledgement request mismatch",
                exchange="kalshi",
                endpoint_category=AdapterEndpointCategory.STREAM,
                context={"request_id": plan.request_id},
            )
        return frame

    async def receive_next_frame(self) -> KalshiWebSocketParsedFrame:
        payload = _decode_frame(
            await self._transport.receive_text(timeout_seconds=self._operation_timeout_seconds)
        )
        try:
            frame_type = _frame_type(payload)
            if frame_type in ("hello", "system.hello"):
                return KalshiWebSocketHello.from_exchange_payload(payload)
            if frame_type in ("subscribed", "subscription.accepted"):
                return KalshiWebSocketSubscriptionAck.from_exchange_payload(payload)
            if frame_type == "ping":
                ping = KalshiWebSocketPing.from_exchange_payload(payload)
                await self._transport.send_json(
                    ping.pong_payload(),
                    timeout_seconds=self._operation_timeout_seconds,
                )
                return ping
            if frame_type == "error":
                _raise_websocket_error(payload)
            return KalshiWebSocketDataFrame.from_exchange_payload(payload)
        except (TypeError, ValueError, ValidationError) as exc:
            raise AdapterProtocolError(
                "Kalshi WebSocket frame is malformed",
                exchange="kalshi",
                endpoint_category=AdapterEndpointCategory.STREAM,
            ) from exc

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._transport.close()


def check_kalshi_websocket_sequence(
    *,
    previous_sequence: int | None,
    frame: KalshiWebSocketDataFrame,
) -> KalshiWebSocketSequenceCheck:
    """Classify one frame sequence without mutating stream state."""

    _validate_optional_nonnegative_int(previous_sequence, field_name="previous_sequence")
    received_sequence = frame.sequence
    expected_sequence = None if previous_sequence is None else previous_sequence + 1

    if received_sequence is None:
        return KalshiWebSocketSequenceCheck(
            previous_sequence=previous_sequence,
            expected_sequence=expected_sequence,
            received_sequence=None,
            status=KalshiWebSocketSequenceStatus.MISSING,
            invalidates_stream=previous_sequence is not None,
        )
    if previous_sequence is None or received_sequence == expected_sequence:
        return KalshiWebSocketSequenceCheck(
            previous_sequence=previous_sequence,
            expected_sequence=expected_sequence,
            received_sequence=received_sequence,
            status=KalshiWebSocketSequenceStatus.OK,
            invalidates_stream=False,
        )
    if received_sequence == previous_sequence:
        status = KalshiWebSocketSequenceStatus.DUPLICATE
    elif received_sequence < previous_sequence:
        status = KalshiWebSocketSequenceStatus.STALE
    else:
        status = KalshiWebSocketSequenceStatus.GAP

    return KalshiWebSocketSequenceCheck(
        previous_sequence=previous_sequence,
        expected_sequence=expected_sequence,
        received_sequence=received_sequence,
        status=status,
        invalidates_stream=status == KalshiWebSocketSequenceStatus.GAP,
    )


def is_kalshi_heartbeat_stale(
    *,
    last_received_at: datetime,
    checked_at: datetime,
    heartbeat_interval_seconds: int,
    missed_heartbeat_limit: int = 2,
) -> bool:
    """Return whether a connection has missed too many heartbeats."""

    last_received = parse_utc_datetime(last_received_at)
    checked = parse_utc_datetime(checked_at)
    interval = _validate_positive_int(
        heartbeat_interval_seconds,
        field_name="heartbeat_interval_seconds",
    )
    missed_limit = _validate_positive_int(
        missed_heartbeat_limit,
        field_name="missed_heartbeat_limit",
    )
    return (checked - last_received).total_seconds() > interval * missed_limit


def _decode_frame(frame_text: str) -> Mapping[str, object]:
    try:
        payload = json.loads(frame_text)
    except JSONDecodeError as exc:
        raise AdapterProtocolError(
            "Kalshi WebSocket frame must be valid JSON",
            exchange="kalshi",
            endpoint_category=AdapterEndpointCategory.STREAM,
        ) from exc
    if not isinstance(payload, Mapping):
        raise AdapterProtocolError(
            "Kalshi WebSocket frame must be a JSON object",
            exchange="kalshi",
            endpoint_category=AdapterEndpointCategory.STREAM,
        )
    return payload


def _raise_websocket_error(payload: Mapping[str, object]) -> None:
    error_payload = payload.get("error")
    if isinstance(error_payload, Mapping):
        error_code = _first_present_payload_item(error_payload, "code", fallback_key="error_code")
    else:
        error_code = payload.get("code")
    raise AdapterProtocolError(
        "Kalshi WebSocket protocol error",
        exchange="kalshi",
        endpoint_category=AdapterEndpointCategory.STREAM,
        exchange_error_code=error_code if isinstance(error_code, str) else None,
    )


def _subscription_from_payload(value: object) -> KalshiWebSocketSubscription:
    if not isinstance(value, Mapping):
        msg = "Kalshi WebSocket subscriptions must contain JSON objects"
        raise ValueError(msg)
    return KalshiWebSocketSubscription.model_validate(
        {
            "subscription_id": value.get("subscription_id"),
            "channel": _subscription_channel(value.get("channel")),
        }
    )


def _data_channel(
    payload: Mapping[str, object],
    *,
    message_type: str,
) -> KalshiWebSocketChannel:
    raw_channel = payload.get("channel")
    if raw_channel in ("order_book", "orderbook", "market_data.order_books"):
        return KalshiWebSocketChannel.ORDER_BOOK
    if raw_channel in ("trades", "trade", "market_data.trades"):
        return KalshiWebSocketChannel.TRADES
    if message_type.startswith("orderbook"):
        return KalshiWebSocketChannel.ORDER_BOOK
    if message_type == "trade":
        return KalshiWebSocketChannel.TRADES
    msg = "Kalshi WebSocket data frame channel is unsupported"
    raise ValueError(msg)


def _subscription_channel(value: object) -> KalshiWebSocketChannel:
    if value in ("order_book", "orderbook", "market_data.order_books"):
        return KalshiWebSocketChannel.ORDER_BOOK
    if value in ("trades", "trade", "market_data.trades"):
        return KalshiWebSocketChannel.TRADES
    msg = "Kalshi WebSocket subscription channel is unsupported"
    raise ValueError(msg)


def _message_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    message_payload = payload.get("msg")
    if message_payload is None:
        return payload
    if not isinstance(message_payload, Mapping):
        msg = "Kalshi WebSocket frame msg must be a JSON object"
        raise ValueError(msg)
    return message_payload


def _frame_type(payload: Mapping[str, object]) -> str:
    frame_type = payload.get("type")
    if not isinstance(frame_type, str):
        msg = "Kalshi WebSocket frame type is required"
        raise ValueError(msg)
    return _validate_required_text(frame_type, field_name="Kalshi WebSocket frame type")


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


def _validate_unique(values: tuple[object, ...], *, field_name: str) -> None:
    if len(set(values)) != len(values):
        msg = f"{field_name} must not contain duplicate values"
        raise ValueError(msg)


def _freeze_payload(value: Mapping[str, object], *, field_name: str) -> Mapping[str, object]:
    try:
        return freeze_canonical_mapping(value, field_name=field_name)
    except TypeError as exc:
        raise ValueError(str(exc)) from exc


def _validate_optional_nonnegative_int(value: int | None, *, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field_name} must be an integer"
        raise TypeError(msg)
    if value < 0:
        msg = f"{field_name} must be nonnegative"
        raise ValueError(msg)


def _validate_timeout_seconds(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = "Kalshi WebSocket timeout_seconds must be an integer"
        raise TypeError(msg)
    if value <= 0:
        msg = "Kalshi WebSocket timeout_seconds must be positive"
        raise ValueError(msg)
    if value > _KALSHI_WEBSOCKET_TIMEOUT_MAX_SECONDS:
        msg = (
            "Kalshi WebSocket timeout_seconds must be at most "
            f"{_KALSHI_WEBSOCKET_TIMEOUT_MAX_SECONDS}"
        )
        raise ValueError(msg)
    return value


def _validate_positive_int(value: int, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field_name} must be an integer"
        raise TypeError(msg)
    if value <= 0:
        msg = f"{field_name} must be positive"
        raise ValueError(msg)
    return value


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_required_text(value, field_name=field_name)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    if len(value) > _KALSHI_WEBSOCKET_TEXT_MAX_LENGTH:
        msg = f"{field_name} must be at most {_KALSHI_WEBSOCKET_TEXT_MAX_LENGTH} characters"
        raise ValueError(msg)
    return value
