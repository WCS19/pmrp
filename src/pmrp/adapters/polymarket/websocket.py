"""Polymarket market WebSocket connection contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from json import JSONDecodeError
from typing import Literal, Protocol, Self

from pydantic import Field, ValidationError, field_serializer, field_validator, model_validator

from pmrp.adapters.base.errors import AdapterEndpointCategory, AdapterProtocolError
from pmrp.adapters.polymarket.raw_models import (
    PolymarketRawOrderBookSnapshot,
    PolymarketRawPriceChangeMessage,
    PolymarketRawTrade,
)
from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
from pmrp.schemas.time import parse_utc_datetime

POLYMARKET_MARKET_WEBSOCKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
POLYMARKET_MARKET_WEBSOCKET_PATH = "/ws/market"
POLYMARKET_DEFAULT_WEBSOCKET_TIMEOUT_SECONDS = 10
POLYMARKET_MARKET_HEARTBEAT_INTERVAL_SECONDS = 10

_POLYMARKET_WEBSOCKET_ID_MAX_LENGTH = 256
_POLYMARKET_WEBSOCKET_TEXT_MAX_LENGTH = 4096
_POLYMARKET_WEBSOCKET_TIMEOUT_MAX_SECONDS = 120


class PolymarketWebSocketSequenceStatus(StrEnum):
    """Sequence availability status for Polymarket market WebSocket frames."""

    UNAVAILABLE = "unavailable"


class PolymarketWebSocketHeartbeat(CanonicalModel):
    """Application-level Polymarket market WebSocket heartbeat text frame."""

    frame_text: Literal["PING", "PONG"]

    @classmethod
    def from_text(cls, frame_text: str) -> Self:
        return cls.model_validate({"frame_text": frame_text})

    def response_text(self) -> str | None:
        if self.frame_text == "PING":
            return "PONG"
        return None


class PolymarketWebSocketSubscriptionPlan(CanonicalModel):
    """Replayable Polymarket market-stream subscription plan."""

    token_ids: tuple[str, ...] = Field(min_length=1)
    custom_feature_enabled: bool = False

    @field_validator("token_ids")
    @classmethod
    def validate_token_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_text_tuple(value, field_name="Polymarket WebSocket token_ids")

    def to_payload(self) -> dict[str, object]:
        """Return the deterministic market subscribe payload sent to transport."""

        payload: dict[str, object] = {
            "assets_ids": list(self.token_ids),
            "type": "market",
        }
        if self.custom_feature_enabled:
            payload["custom_feature_enabled"] = True
        return payload


class PolymarketWebSocketTokenUpdatePlan(CanonicalModel):
    """Replayable Polymarket market-stream token add/remove plan."""

    operation: Literal["subscribe", "unsubscribe"]
    token_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("token_ids")
    @classmethod
    def validate_token_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_text_tuple(value, field_name="Polymarket WebSocket token_ids")

    def to_payload(self) -> dict[str, object]:
        """Return the deterministic token update payload sent to transport."""

        return {
            "assets_ids": list(self.token_ids),
            "operation": self.operation,
        }


class PolymarketWebSocketSubscriptionState(CanonicalModel):
    """Local token subscription state for one market WebSocket connection."""

    token_ids: tuple[str, ...] = Field(min_length=1)
    custom_feature_enabled: bool = False

    @classmethod
    def from_plan(cls, plan: PolymarketWebSocketSubscriptionPlan) -> Self:
        return cls.model_validate(
            {
                "token_ids": plan.token_ids,
                "custom_feature_enabled": plan.custom_feature_enabled,
            }
        )

    @field_validator("token_ids")
    @classmethod
    def validate_token_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_text_tuple(value, field_name="Polymarket WebSocket token_ids")

    def apply_update(self, plan: PolymarketWebSocketTokenUpdatePlan) -> Self:
        if plan.operation == "subscribe":
            token_ids = _append_unique(self.token_ids, plan.token_ids)
        else:
            token_ids = tuple(
                token_id for token_id in self.token_ids if token_id not in plan.token_ids
            )
            if not token_ids:
                msg = "Polymarket WebSocket subscription state must retain at least one token"
                raise ValueError(msg)
        return type(self).model_validate(
            {
                "token_ids": token_ids,
                "custom_feature_enabled": self.custom_feature_enabled,
            }
        )

    def to_payload(self) -> dict[str, object]:
        return PolymarketWebSocketSubscriptionPlan(
            token_ids=self.token_ids,
            custom_feature_enabled=self.custom_feature_enabled,
        ).to_payload()


class PolymarketWebSocketUnsupportedFrame(CanonicalModel):
    """Raw unsupported Polymarket market-stream frame preserved for later slices."""

    topic: str | None = Field(default=None, min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    payload: Mapping[str, object]
    raw_payload: Mapping[str, object]

    @classmethod
    def from_exchange_payload(cls, payload: Mapping[str, object]) -> Self:
        message_payload = payload.get("payload")
        if message_payload is None:
            message_payload = payload
        if not isinstance(message_payload, Mapping):
            msg = "Polymarket WebSocket unsupported frame payload must be a JSON object"
            raise ValueError(msg)
        return cls.model_validate(
            {
                "topic": payload.get("topic"),
                "event_type": _frame_type(payload),
                "payload": message_payload,
                "raw_payload": payload,
            }
        )

    @field_validator("topic", "event_type")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Polymarket WebSocket frame text field")

    @field_validator("payload", "raw_payload")
    @classmethod
    def validate_payload(cls, value: Mapping[str, object]) -> Mapping[str, object]:
        return _freeze_payload(value, field_name="polymarket websocket frame payload")

    @field_serializer("payload", "raw_payload")
    def serialize_payload(self, value: Mapping[str, object]) -> dict[str, object]:
        return thaw_canonical_mapping(value)


class PolymarketWebSocketSequenceCheck(CanonicalModel):
    """Deterministic sequence check result for unsequenced Polymarket market frames."""

    event_type: str = Field(min_length=1, max_length=128)
    status: PolymarketWebSocketSequenceStatus
    sequence_available: bool
    invalidates_stream: bool

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str) -> str:
        return _validate_required_text(value, field_name="Polymarket WebSocket event_type")

    @model_validator(mode="after")
    def validate_unavailable_status(self) -> Self:
        if self.status is PolymarketWebSocketSequenceStatus.UNAVAILABLE and (
            self.sequence_available or self.invalidates_stream
        ):
            msg = "unavailable Polymarket sequences must not invalidate the stream"
            raise ValueError(msg)
        return self


type PolymarketWebSocketParsedFrame = (
    PolymarketWebSocketHeartbeat
    | PolymarketRawOrderBookSnapshot
    | PolymarketRawPriceChangeMessage
    | PolymarketRawTrade
    | PolymarketWebSocketUnsupportedFrame
)


class PolymarketWebSocketTransport(Protocol):
    """Async text WebSocket transport boundary."""

    async def receive_text(self, *, timeout_seconds: int) -> str:
        """Receive one text frame using an explicit timeout."""

        ...

    async def send_text(self, text: str, *, timeout_seconds: int) -> None:
        """Send one text frame using an explicit timeout."""

        ...

    async def send_json(self, payload: Mapping[str, object], *, timeout_seconds: int) -> None:
        """Send one JSON-serializable payload using an explicit timeout."""

        ...

    async def close(self) -> None:
        """Close the transport."""

        ...


class PolymarketWebSocketConnection:
    """Transport-injected Polymarket market WebSocket connection helper."""

    def __init__(
        self,
        *,
        transport: PolymarketWebSocketTransport,
        operation_timeout_seconds: int = POLYMARKET_DEFAULT_WEBSOCKET_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = transport
        self._operation_timeout_seconds = _validate_timeout_seconds(operation_timeout_seconds)
        self._subscription: PolymarketWebSocketSubscriptionState | None = None
        self._closed = False

    @property
    def operation_timeout_seconds(self) -> int:
        return self._operation_timeout_seconds

    @property
    def subscription(self) -> PolymarketWebSocketSubscriptionState | None:
        return self._subscription

    async def subscribe(
        self,
        plan: PolymarketWebSocketSubscriptionPlan,
    ) -> PolymarketWebSocketSubscriptionState:
        """Send the initial market subscription frame."""

        await self._transport.send_json(
            plan.to_payload(),
            timeout_seconds=self._operation_timeout_seconds,
        )
        self._subscription = PolymarketWebSocketSubscriptionState.from_plan(plan)
        return self._subscription

    async def resubscribe(self) -> PolymarketWebSocketSubscriptionState:
        """Replay the current market subscription after reconnect."""

        if self._subscription is None:
            raise AdapterProtocolError(
                "Polymarket WebSocket cannot resubscribe before subscribe",
                exchange="polymarket",
                endpoint_category=AdapterEndpointCategory.STREAM,
            )
        await self._transport.send_json(
            self._subscription.to_payload(),
            timeout_seconds=self._operation_timeout_seconds,
        )
        return self._subscription

    async def update_tokens(
        self,
        plan: PolymarketWebSocketTokenUpdatePlan,
    ) -> PolymarketWebSocketSubscriptionState:
        """Send a token add/remove frame and update local subscription state."""

        if self._subscription is None:
            raise AdapterProtocolError(
                "Polymarket WebSocket cannot update tokens before subscribe",
                exchange="polymarket",
                endpoint_category=AdapterEndpointCategory.STREAM,
            )
        updated_subscription = self._subscription.apply_update(plan)
        await self._transport.send_json(
            plan.to_payload(),
            timeout_seconds=self._operation_timeout_seconds,
        )
        self._subscription = updated_subscription
        return updated_subscription

    async def send_heartbeat(self) -> None:
        """Send the application-level PING frame required by the market stream."""

        await self._transport.send_text(
            "PING",
            timeout_seconds=self._operation_timeout_seconds,
        )

    async def receive_next_frame(self) -> PolymarketWebSocketParsedFrame:
        frame_text = await self._transport.receive_text(
            timeout_seconds=self._operation_timeout_seconds
        )
        if frame_text in ("PING", "PONG"):
            heartbeat = PolymarketWebSocketHeartbeat.from_text(frame_text)
            response_text = heartbeat.response_text()
            if response_text is not None:
                await self._transport.send_text(
                    response_text,
                    timeout_seconds=self._operation_timeout_seconds,
                )
            return heartbeat

        payload = _decode_frame(frame_text)
        try:
            frame_type = _frame_type(payload)
            if frame_type == "error":
                _raise_websocket_error(payload)
            if frame_type == "book":
                return PolymarketRawOrderBookSnapshot.from_exchange_payload(payload)
            if frame_type == "price_change":
                return PolymarketRawPriceChangeMessage.from_exchange_payload(payload)
            if frame_type == "last_trade_price":
                return PolymarketRawTrade.from_exchange_payload(payload)
            return PolymarketWebSocketUnsupportedFrame.from_exchange_payload(payload)
        except (TypeError, ValueError, ValidationError) as exc:
            raise AdapterProtocolError(
                "Polymarket WebSocket frame is malformed",
                exchange="polymarket",
                endpoint_category=AdapterEndpointCategory.STREAM,
            ) from exc

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._transport.close()


def check_polymarket_websocket_sequence(
    frame: PolymarketRawOrderBookSnapshot
    | PolymarketRawPriceChangeMessage
    | PolymarketRawTrade
    | PolymarketWebSocketUnsupportedFrame,
) -> PolymarketWebSocketSequenceCheck:
    """Return the explicit sequence status for Polymarket market frames."""

    return PolymarketWebSocketSequenceCheck(
        event_type=_parsed_frame_type(frame),
        status=PolymarketWebSocketSequenceStatus.UNAVAILABLE,
        sequence_available=False,
        invalidates_stream=False,
    )


def is_polymarket_heartbeat_stale(
    *,
    last_pong_at: datetime,
    checked_at: datetime,
    heartbeat_interval_seconds: int = POLYMARKET_MARKET_HEARTBEAT_INTERVAL_SECONDS,
    missed_heartbeat_limit: int = 2,
) -> bool:
    """Return whether a connection has missed too many heartbeat acknowledgements."""

    last_pong = parse_utc_datetime(last_pong_at)
    checked = parse_utc_datetime(checked_at)
    interval = _validate_positive_int(
        heartbeat_interval_seconds,
        field_name="heartbeat_interval_seconds",
    )
    missed_limit = _validate_positive_int(
        missed_heartbeat_limit,
        field_name="missed_heartbeat_limit",
    )
    return (checked - last_pong).total_seconds() > interval * missed_limit


def _decode_frame(frame_text: str) -> Mapping[str, object]:
    if frame_text in ("PING", "PONG"):
        msg = "Polymarket WebSocket heartbeat frames must be handled before JSON decoding"
        raise AdapterProtocolError(
            msg,
            exchange="polymarket",
            endpoint_category=AdapterEndpointCategory.STREAM,
        )
    try:
        payload = json.loads(frame_text)
    except JSONDecodeError as exc:
        raise AdapterProtocolError(
            "Polymarket WebSocket frame must be valid JSON",
            exchange="polymarket",
            endpoint_category=AdapterEndpointCategory.STREAM,
        ) from exc
    if not isinstance(payload, Mapping):
        raise AdapterProtocolError(
            "Polymarket WebSocket frame must be a JSON object",
            exchange="polymarket",
            endpoint_category=AdapterEndpointCategory.STREAM,
        )
    return payload


def _raise_websocket_error(payload: Mapping[str, object]) -> None:
    error_code: str | None = None
    raw_code = payload.get("code")
    if isinstance(raw_code, str):
        error_code = raw_code
    raw_type = payload.get("type")
    if error_code is None and isinstance(raw_type, str):
        error_code = raw_type
    if error_code is None:
        error_payload = payload.get("error")
        if isinstance(error_payload, Mapping):
            nested_code = error_payload.get("code")
            error_code = nested_code if isinstance(nested_code, str) else None
    raise AdapterProtocolError(
        "Polymarket WebSocket protocol error",
        exchange="polymarket",
        endpoint_category=AdapterEndpointCategory.STREAM,
        exchange_error_code=error_code,
    )


def _frame_type(payload: Mapping[str, object]) -> str:
    frame_type = payload.get("type")
    if frame_type is None:
        frame_type = payload.get("event_type")
    if not isinstance(frame_type, str):
        msg = "Polymarket WebSocket frame type is required"
        raise ValueError(msg)
    return _validate_required_text(frame_type, field_name="Polymarket WebSocket frame type")


def _parsed_frame_type(
    frame: PolymarketRawOrderBookSnapshot
    | PolymarketRawPriceChangeMessage
    | PolymarketRawTrade
    | PolymarketWebSocketUnsupportedFrame,
) -> str:
    if isinstance(frame, PolymarketRawOrderBookSnapshot):
        return frame.event_type if frame.event_type is not None else "book"
    if isinstance(frame, PolymarketRawPriceChangeMessage):
        return frame.event_type
    if isinstance(frame, PolymarketRawTrade):
        return frame.event_type if frame.event_type is not None else "last_trade_price"
    return frame.event_type


def _append_unique(
    existing_values: tuple[str, ...], new_values: tuple[str, ...]
) -> tuple[str, ...]:
    values = list(existing_values)
    for value in new_values:
        if value not in values:
            values.append(value)
    return tuple(values)


def _validate_text_tuple(value: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    if len(set(value)) != len(value):
        msg = f"{field_name} must not contain duplicate values"
        raise ValueError(msg)
    return tuple(_validate_required_text(item, field_name=field_name) for item in value)


def _freeze_payload(value: Mapping[str, object], *, field_name: str) -> Mapping[str, object]:
    try:
        return freeze_canonical_mapping(value, field_name=field_name)
    except TypeError as exc:
        raise ValueError(str(exc)) from exc


def _validate_timeout_seconds(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = "Polymarket WebSocket timeout_seconds must be an integer"
        raise TypeError(msg)
    if value <= 0:
        msg = "Polymarket WebSocket timeout_seconds must be positive"
        raise ValueError(msg)
    if value > _POLYMARKET_WEBSOCKET_TIMEOUT_MAX_SECONDS:
        msg = (
            "Polymarket WebSocket timeout_seconds must be at most "
            f"{_POLYMARKET_WEBSOCKET_TIMEOUT_MAX_SECONDS}"
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
    if len(value) > _POLYMARKET_WEBSOCKET_TEXT_MAX_LENGTH:
        msg = f"{field_name} must be at most {_POLYMARKET_WEBSOCKET_TEXT_MAX_LENGTH} characters"
        raise ValueError(msg)
    return value
