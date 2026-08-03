"""Tests for Kalshi WebSocket connection contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from pmrp.adapters import AdapterProtocolError
from pmrp.adapters.kalshi import (
    KalshiWebSocketChannel,
    KalshiWebSocketConnection,
    KalshiWebSocketDataFrame,
    KalshiWebSocketHello,
    KalshiWebSocketPing,
    KalshiWebSocketSequenceStatus,
    KalshiWebSocketSubscribePlan,
    KalshiWebSocketSubscriptionAck,
    check_kalshi_websocket_sequence,
    is_kalshi_heartbeat_stale,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit


class FakeKalshiWebSocketTransport:
    def __init__(self, incoming_frames: Sequence[str]) -> None:
        self._incoming_frames = list(incoming_frames)
        self.received_timeouts: list[int] = []
        self.sent_payloads: list[Mapping[str, object]] = []
        self.sent_timeouts: list[int] = []
        self.close_count = 0

    async def receive_text(self, *, timeout_seconds: int) -> str:
        self.received_timeouts.append(timeout_seconds)
        return self._incoming_frames.pop(0)

    async def send_json(self, payload: Mapping[str, object], *, timeout_seconds: int) -> None:
        self.sent_payloads.append(payload)
        self.sent_timeouts.append(timeout_seconds)

    async def close(self) -> None:
        self.close_count += 1


def _frame(payload: Mapping[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _hello_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "system.hello",
        "connection_id": "conn_fixture_0001",
        "heartbeat_interval_seconds": 20,
        "server_time": "2026-08-02T18:00:00Z",
    }
    payload.update(overrides)
    return payload


def _subscription_ack_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "subscription.accepted",
        "request_id": "subreq_fixture_0001",
        "subscriptions": [
            {"subscription_id": "sub_fixture_order_book", "channel": "order_book"},
            {"subscription_id": "sub_fixture_trades", "channel": "trades"},
        ],
    }
    payload.update(overrides)
    return payload


def _data_frame_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "type": "orderbook_delta",
        "seq": 101,
        "msg": {
            "market_ticker": "KX-PMRP-EXAMPLE-YES",
            "side": "yes",
            "price": 48,
            "quantity": 75,
            "action": "insert",
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_kalshi_websocket_connection_receives_server_hello() -> None:
    transport = FakeKalshiWebSocketTransport([_frame(_hello_payload())])
    connection = KalshiWebSocketConnection(transport=transport, operation_timeout_seconds=7)

    hello = await connection.receive_hello()

    assert hello.connection_id == "conn_fixture_0001"
    assert hello.heartbeat_interval_seconds == 20
    assert hello.server_time.isoformat() == "2026-08-02T18:00:00+00:00"
    assert hello.raw_payload["type"] == "system.hello"
    assert transport.received_timeouts == [7]


@pytest.mark.asyncio
async def test_kalshi_websocket_connection_subscribe_sends_replayable_payload() -> None:
    transport = FakeKalshiWebSocketTransport([_frame(_subscription_ack_payload())])
    connection = KalshiWebSocketConnection(transport=transport, operation_timeout_seconds=8)
    plan = KalshiWebSocketSubscribePlan(
        request_id="subreq_fixture_0001",
        channels=(KalshiWebSocketChannel.ORDER_BOOK, KalshiWebSocketChannel.TRADES),
        market_tickers=("KX-PMRP-EXAMPLE-YES",),
    )

    ack = await connection.subscribe(plan)

    assert isinstance(ack, KalshiWebSocketSubscriptionAck)
    assert [subscription.subscription_id for subscription in ack.subscriptions] == [
        "sub_fixture_order_book",
        "sub_fixture_trades",
    ]
    assert transport.sent_payloads == [
        {
            "type": "subscribe",
            "request_id": "subreq_fixture_0001",
            "channels": ["order_book", "trades"],
            "market_tickers": ["KX-PMRP-EXAMPLE-YES"],
        }
    ]
    assert transport.sent_timeouts == [8]
    assert transport.received_timeouts == [8]


@pytest.mark.asyncio
async def test_kalshi_websocket_connection_rejects_forbidden_subscribe() -> None:
    transport = FakeKalshiWebSocketTransport(
        [
            _frame(
                {
                    "type": "error",
                    "error": {
                        "code": "forbidden_channel",
                        "message": "synthetic forbidden channel",
                    },
                }
            )
        ]
    )
    connection = KalshiWebSocketConnection(transport=transport)
    plan = KalshiWebSocketSubscribePlan(
        request_id="subreq_fixture_0001",
        channels=(KalshiWebSocketChannel.ORDER_BOOK,),
        market_tickers=("KX-PMRP-EXAMPLE-YES",),
    )

    with pytest.raises(AdapterProtocolError) as exc_info:
        await connection.subscribe(plan)

    assert exc_info.value.context["exchange_error_code"] == "forbidden_channel"
    assert "synthetic forbidden channel" not in str(exc_info.value)


def test_kalshi_websocket_subscribe_plan_rejects_duplicates_and_blank_values() -> None:
    with pytest.raises(ValidationError, match="duplicate values"):
        KalshiWebSocketSubscribePlan(
            request_id="subreq_fixture_0001",
            channels=(KalshiWebSocketChannel.ORDER_BOOK, KalshiWebSocketChannel.ORDER_BOOK),
            market_tickers=("KX-PMRP-EXAMPLE-YES",),
        )
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        KalshiWebSocketSubscribePlan(
            request_id=" subreq_fixture_0001 ",
            channels=(KalshiWebSocketChannel.ORDER_BOOK,),
            market_tickers=("KX-PMRP-EXAMPLE-YES",),
        )


@pytest.mark.asyncio
async def test_kalshi_websocket_connection_responds_to_heartbeat_ping() -> None:
    transport = FakeKalshiWebSocketTransport(
        [_frame({"type": "ping", "sent_at": "2026-08-02T18:00:20Z"})]
    )
    connection = KalshiWebSocketConnection(transport=transport, operation_timeout_seconds=6)

    ping = await connection.receive_next_frame()

    assert isinstance(ping, KalshiWebSocketPing)
    assert ping.sent_at.isoformat() == "2026-08-02T18:00:20+00:00"
    assert transport.sent_payloads == [{"type": "pong", "sent_at": "2026-08-02T18:00:20Z"}]
    assert transport.sent_timeouts == [6]


@pytest.mark.asyncio
async def test_kalshi_websocket_connection_parses_data_frame_and_sequence() -> None:
    transport = FakeKalshiWebSocketTransport([_frame(_data_frame_payload(seq=102))])
    connection = KalshiWebSocketConnection(transport=transport)

    frame = await connection.receive_next_frame()

    assert isinstance(frame, KalshiWebSocketDataFrame)
    assert frame.channel is KalshiWebSocketChannel.ORDER_BOOK
    assert frame.market_ticker == "KX-PMRP-EXAMPLE-YES"
    assert frame.sequence == 102
    assert frame.payload["price"] == 48
    check = check_kalshi_websocket_sequence(previous_sequence=101, frame=frame)
    assert check.expected_sequence == 102
    assert check.status is KalshiWebSocketSequenceStatus.OK
    assert check.invalidates_stream is False


def test_kalshi_websocket_sequence_check_identifies_duplicate_stale_gap_and_missing() -> None:
    duplicate = KalshiWebSocketDataFrame.from_exchange_payload(_data_frame_payload(seq=101))
    stale = KalshiWebSocketDataFrame.from_exchange_payload(_data_frame_payload(seq=100))
    gap = KalshiWebSocketDataFrame.from_exchange_payload(_data_frame_payload(seq=105))
    missing = KalshiWebSocketDataFrame.from_exchange_payload(
        _data_frame_payload(seq=None, sequence=None)
    )

    duplicate_check = check_kalshi_websocket_sequence(previous_sequence=101, frame=duplicate)
    stale_check = check_kalshi_websocket_sequence(previous_sequence=101, frame=stale)
    gap_check = check_kalshi_websocket_sequence(previous_sequence=101, frame=gap)
    missing_check = check_kalshi_websocket_sequence(previous_sequence=101, frame=missing)

    assert duplicate_check.status is KalshiWebSocketSequenceStatus.DUPLICATE
    assert duplicate_check.invalidates_stream is False
    assert stale_check.status is KalshiWebSocketSequenceStatus.STALE
    assert stale_check.invalidates_stream is False
    assert gap_check.status is KalshiWebSocketSequenceStatus.GAP
    assert gap_check.invalidates_stream is True
    assert missing_check.status is KalshiWebSocketSequenceStatus.MISSING
    assert missing_check.invalidates_stream is True


@pytest.mark.asyncio
async def test_kalshi_websocket_connection_rejects_malformed_frames() -> None:
    invalid_json = KalshiWebSocketConnection(
        transport=FakeKalshiWebSocketTransport(["{"]),
    )
    non_object = KalshiWebSocketConnection(
        transport=FakeKalshiWebSocketTransport(["[]"]),
    )
    unsupported_channel = KalshiWebSocketConnection(
        transport=FakeKalshiWebSocketTransport([_frame({"type": "quote", "seq": 1})]),
    )

    with pytest.raises(AdapterProtocolError, match="valid JSON"):
        await invalid_json.receive_next_frame()
    with pytest.raises(AdapterProtocolError, match="JSON object"):
        await non_object.receive_next_frame()
    with pytest.raises(AdapterProtocolError, match="frame is malformed"):
        await unsupported_channel.receive_next_frame()


def test_kalshi_websocket_heartbeat_stale_detection_is_clock_injected() -> None:
    last_received_at = datetime(2026, 8, 2, 18, 0, tzinfo=UTC)

    assert is_kalshi_heartbeat_stale(
        last_received_at=last_received_at,
        checked_at=last_received_at + timedelta(seconds=41),
        heartbeat_interval_seconds=20,
    )
    assert not is_kalshi_heartbeat_stale(
        last_received_at=last_received_at,
        checked_at=last_received_at + timedelta(seconds=40),
        heartbeat_interval_seconds=20,
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        is_kalshi_heartbeat_stale(
            last_received_at=last_received_at.replace(tzinfo=None),
            checked_at=last_received_at,
            heartbeat_interval_seconds=20,
        )


def test_kalshi_websocket_models_are_strict_and_immutable() -> None:
    hello = KalshiWebSocketHello.from_exchange_payload(_hello_payload())
    original_hash = canonical_sha256(hello)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        hello.connection_id = "conn_fixture_0002"
    with pytest.raises(TypeError):
        hello.raw_payload["connection_id"] = "conn_fixture_0002"
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        KalshiWebSocketHello.from_exchange_payload(_hello_payload(heartbeat_interval_seconds=20.5))

    assert canonical_sha256(hello) == original_hash
    assert canonical_json(hello).startswith('{"connection_id":"conn_fixture_0001"')


@pytest.mark.asyncio
async def test_kalshi_websocket_connection_close_is_idempotent() -> None:
    transport = FakeKalshiWebSocketTransport(())
    connection = KalshiWebSocketConnection(transport=transport)

    await connection.close()
    await connection.close()

    assert transport.close_count == 1
