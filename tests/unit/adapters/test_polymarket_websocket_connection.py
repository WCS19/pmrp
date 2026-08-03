"""Tests for Polymarket WebSocket connection contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from pmrp.adapters import AdapterProtocolError
from pmrp.adapters.polymarket import (
    POLYMARKET_MARKET_HEARTBEAT_INTERVAL_SECONDS,
    POLYMARKET_MARKET_WEBSOCKET_URL,
    PolymarketRawOrderBookSnapshot,
    PolymarketRawPriceChangeMessage,
    PolymarketRawTrade,
    PolymarketWebSocketConnection,
    PolymarketWebSocketHeartbeat,
    PolymarketWebSocketSequenceStatus,
    PolymarketWebSocketSubscriptionPlan,
    PolymarketWebSocketTokenUpdatePlan,
    PolymarketWebSocketUnsupportedFrame,
    check_polymarket_websocket_sequence,
    is_polymarket_heartbeat_stale,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit


class FakePolymarketWebSocketTransport:
    def __init__(self, incoming_frames: Sequence[str]) -> None:
        self._incoming_frames = list(incoming_frames)
        self.received_timeouts: list[int] = []
        self.sent_texts: list[str] = []
        self.sent_json_payloads: list[Mapping[str, object]] = []
        self.sent_timeouts: list[int] = []
        self.close_count = 0

    async def receive_text(self, *, timeout_seconds: int) -> str:
        self.received_timeouts.append(timeout_seconds)
        return self._incoming_frames.pop(0)

    async def send_text(self, text: str, *, timeout_seconds: int) -> None:
        self.sent_texts.append(text)
        self.sent_timeouts.append(timeout_seconds)

    async def send_json(self, payload: Mapping[str, object], *, timeout_seconds: int) -> None:
        self.sent_json_payloads.append(payload)
        self.sent_timeouts.append(timeout_seconds)

    async def close(self) -> None:
        self.close_count += 1


def _frame(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _book_frame(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "topic": "market",
        "type": "book",
        "payload": {
            "market": "0x1111111111111111111111111111111111111111111111111111111111111111",
            "tokenId": "101010101010101010101010101010101010101010101010101010101010101010",
            "timestamp": "1782753357257",
            "hash": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "bids": [{"price": "0.48", "size": "1000"}],
            "asks": [{"price": "0.52", "size": "800"}],
            "minOrderSize": "5",
            "tickSize": "0.01",
        },
    }
    payload.update(overrides)
    return payload


def _price_change_frame(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "topic": "market",
        "type": "price_change",
        "payload": {
            "market": "0x1111111111111111111111111111111111111111111111111111111111111111",
            "priceChanges": [
                {
                    "tokenId": (
                        "101010101010101010101010101010101010101010101010101010101010101010"
                    ),
                    "price": "0.50",
                    "size": "200",
                    "side": "BUY",
                    "bestBid": "0.50",
                    "bestAsk": "0.52",
                }
            ],
            "timestamp": "1782753357257",
        },
    }
    payload.update(overrides)
    return payload


def _trade_frame(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "topic": "market",
        "type": "last_trade_price",
        "payload": {
            "market": "0x1111111111111111111111111111111111111111111111111111111111111111",
            "tokenId": "101010101010101010101010101010101010101010101010101010101010101010",
            "price": "0.456",
            "side": "SELL",
            "timestamp": "1782753357257",
            "transactionHash": (
                "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
            ),
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_polymarket_websocket_subscribe_sends_documented_market_frame() -> None:
    transport = FakePolymarketWebSocketTransport(())
    connection = PolymarketWebSocketConnection(transport=transport, operation_timeout_seconds=7)
    plan = PolymarketWebSocketSubscriptionPlan(
        token_ids=(
            "101010101010101010101010101010101010101010101010101010101010101010",
            "202020202020202020202020202020202020202020202020202020202020202020",
        ),
        custom_feature_enabled=True,
    )

    state = await connection.subscribe(plan)

    assert POLYMARKET_MARKET_WEBSOCKET_URL.endswith("/ws/market")
    assert state.token_ids == plan.token_ids
    assert transport.sent_json_payloads == [
        {
            "assets_ids": list(plan.token_ids),
            "type": "market",
            "custom_feature_enabled": True,
        }
    ]
    assert transport.sent_timeouts == [7]


@pytest.mark.asyncio
async def test_polymarket_websocket_token_updates_and_resubscribe_are_replayable() -> None:
    transport = FakePolymarketWebSocketTransport(())
    connection = PolymarketWebSocketConnection(transport=transport, operation_timeout_seconds=8)
    await connection.subscribe(
        PolymarketWebSocketSubscriptionPlan(token_ids=("token_fixture_0001",))
    )

    updated = await connection.update_tokens(
        PolymarketWebSocketTokenUpdatePlan(
            operation="subscribe",
            token_ids=("token_fixture_0002",),
        )
    )
    await connection.resubscribe()

    assert updated.token_ids == ("token_fixture_0001", "token_fixture_0002")
    assert transport.sent_json_payloads == [
        {"assets_ids": ["token_fixture_0001"], "type": "market"},
        {"assets_ids": ["token_fixture_0002"], "operation": "subscribe"},
        {
            "assets_ids": ["token_fixture_0001", "token_fixture_0002"],
            "type": "market",
        },
    ]
    assert transport.sent_timeouts == [8, 8, 8]


@pytest.mark.asyncio
async def test_polymarket_websocket_unsubscribe_updates_local_state() -> None:
    transport = FakePolymarketWebSocketTransport(())
    connection = PolymarketWebSocketConnection(transport=transport)
    await connection.subscribe(
        PolymarketWebSocketSubscriptionPlan(token_ids=("token_fixture_0001", "token_fixture_0002"))
    )

    updated = await connection.update_tokens(
        PolymarketWebSocketTokenUpdatePlan(
            operation="unsubscribe",
            token_ids=("token_fixture_0001",),
        )
    )

    assert updated.token_ids == ("token_fixture_0002",)
    assert transport.sent_json_payloads[-1] == {
        "assets_ids": ["token_fixture_0001"],
        "operation": "unsubscribe",
    }


@pytest.mark.asyncio
async def test_polymarket_websocket_rejects_updates_before_initial_subscribe() -> None:
    connection = PolymarketWebSocketConnection(transport=FakePolymarketWebSocketTransport(()))

    with pytest.raises(AdapterProtocolError, match="before subscribe"):
        await connection.resubscribe()
    with pytest.raises(AdapterProtocolError, match="before subscribe"):
        await connection.update_tokens(
            PolymarketWebSocketTokenUpdatePlan(
                operation="subscribe",
                token_ids=("token_fixture_0001",),
            )
        )


@pytest.mark.asyncio
async def test_polymarket_websocket_heartbeat_send_and_receive() -> None:
    transport = FakePolymarketWebSocketTransport(["PONG", "PING"])
    connection = PolymarketWebSocketConnection(transport=transport, operation_timeout_seconds=6)

    await connection.send_heartbeat()
    pong = await connection.receive_next_frame()
    ping = await connection.receive_next_frame()

    assert isinstance(pong, PolymarketWebSocketHeartbeat)
    assert pong.frame_text == "PONG"
    assert isinstance(ping, PolymarketWebSocketHeartbeat)
    assert ping.frame_text == "PING"
    assert transport.sent_texts == ["PING", "PONG"]
    assert transport.sent_timeouts == [6, 6]
    assert transport.received_timeouts == [6, 6]


@pytest.mark.asyncio
async def test_polymarket_websocket_parses_market_stream_data_frames() -> None:
    transport = FakePolymarketWebSocketTransport(
        [
            _frame(_book_frame()),
            _frame(_price_change_frame()),
            _frame(_trade_frame()),
        ]
    )
    connection = PolymarketWebSocketConnection(transport=transport)

    book = await connection.receive_next_frame()
    price_change = await connection.receive_next_frame()
    trade = await connection.receive_next_frame()

    assert isinstance(book, PolymarketRawOrderBookSnapshot)
    assert book.topic == "market"
    assert book.event_type == "book"
    assert book.tick_size is not None
    assert isinstance(price_change, PolymarketRawPriceChangeMessage)
    assert price_change.price_changes[0].best_bid is not None
    assert isinstance(trade, PolymarketRawTrade)
    assert trade.event_type == "last_trade_price"
    assert trade.size is None

    sequence_check = check_polymarket_websocket_sequence(book)
    assert sequence_check.event_type == "book"
    assert sequence_check.status is PolymarketWebSocketSequenceStatus.UNAVAILABLE
    assert sequence_check.invalidates_stream is False


@pytest.mark.asyncio
async def test_polymarket_websocket_preserves_unsupported_market_frames() -> None:
    transport = FakePolymarketWebSocketTransport(
        [
            _frame(
                {
                    "topic": "market",
                    "type": "tick_size_change",
                    "payload": {
                        "market": (
                            "0x1111111111111111111111111111111111111111111111111111111111111111"
                        ),
                        "tokenId": (
                            "101010101010101010101010101010101010101010101010101010101010101010"
                        ),
                        "oldTickSize": "0.01",
                        "newTickSize": "0.001",
                        "timestamp": "1782753357257",
                    },
                }
            )
        ]
    )
    connection = PolymarketWebSocketConnection(transport=transport)

    frame = await connection.receive_next_frame()

    assert isinstance(frame, PolymarketWebSocketUnsupportedFrame)
    assert frame.topic == "market"
    assert frame.event_type == "tick_size_change"
    assert frame.raw_payload["type"] == "tick_size_change"
    with pytest.raises(TypeError):
        frame.raw_payload["type"] = "changed"


@pytest.mark.asyncio
async def test_polymarket_websocket_rejects_malformed_and_error_frames_safely() -> None:
    invalid_json = PolymarketWebSocketConnection(
        transport=FakePolymarketWebSocketTransport(["{secret_frame"]),
    )
    non_object = PolymarketWebSocketConnection(
        transport=FakePolymarketWebSocketTransport(["[]"]),
    )
    malformed_book = PolymarketWebSocketConnection(
        transport=FakePolymarketWebSocketTransport(
            [_frame(_book_frame(payload={"market": "secret_market"}))]
        ),
    )
    error_frame = PolymarketWebSocketConnection(
        transport=FakePolymarketWebSocketTransport(
            [_frame({"type": "error", "code": "invalid_subscription", "message": "secret text"})]
        ),
    )

    with pytest.raises(AdapterProtocolError, match="valid JSON") as invalid_json_exc:
        await invalid_json.receive_next_frame()
    with pytest.raises(AdapterProtocolError, match="JSON object"):
        await non_object.receive_next_frame()
    with pytest.raises(AdapterProtocolError, match="frame is malformed") as malformed_book_exc:
        await malformed_book.receive_next_frame()
    with pytest.raises(AdapterProtocolError) as exc_info:
        await error_frame.receive_next_frame()

    assert invalid_json_exc.value.__cause__ is None
    assert malformed_book_exc.value.__cause__ is None
    assert exc_info.value.context["exchange_error_code"] == "invalid_subscription"
    assert "secret text" not in str(exc_info.value)


def test_polymarket_websocket_plans_reject_duplicates_and_blank_values() -> None:
    with pytest.raises(ValidationError, match="duplicate values"):
        PolymarketWebSocketSubscriptionPlan(token_ids=("token_fixture_0001", "token_fixture_0001"))
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        PolymarketWebSocketTokenUpdatePlan(
            operation="subscribe",
            token_ids=(" token_fixture_0001 ",),
        )


def test_polymarket_websocket_heartbeat_stale_detection_is_clock_injected() -> None:
    last_pong_at = datetime(2026, 8, 2, 18, 0, tzinfo=UTC)

    assert POLYMARKET_MARKET_HEARTBEAT_INTERVAL_SECONDS == 10
    assert is_polymarket_heartbeat_stale(
        last_pong_at=last_pong_at,
        checked_at=last_pong_at + timedelta(seconds=21),
    )
    assert not is_polymarket_heartbeat_stale(
        last_pong_at=last_pong_at,
        checked_at=last_pong_at + timedelta(seconds=20),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        is_polymarket_heartbeat_stale(
            last_pong_at=last_pong_at.replace(tzinfo=None),
            checked_at=last_pong_at,
        )


def test_polymarket_websocket_models_are_strict_immutable_and_hashable() -> None:
    plan = PolymarketWebSocketSubscriptionPlan(token_ids=("token_fixture_0001",))
    original_hash = canonical_sha256(plan)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        plan.custom_feature_enabled = True
    with pytest.raises(ValidationError, match="Input should be a valid boolean"):
        PolymarketWebSocketSubscriptionPlan(
            token_ids=("token_fixture_0001",),
            custom_feature_enabled="true",
        )

    assert canonical_sha256(plan) == original_hash
    assert canonical_json(plan).startswith('{"custom_feature_enabled":false')


@pytest.mark.asyncio
async def test_polymarket_websocket_connection_close_is_idempotent() -> None:
    transport = FakePolymarketWebSocketTransport(())
    connection = PolymarketWebSocketConnection(transport=transport)

    await connection.close()
    await connection.close()

    assert transport.close_count == 1
