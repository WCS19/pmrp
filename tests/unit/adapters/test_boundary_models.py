"""Tests for shared adapter request and response boundary contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pmrp.adapters import (
    MarketDataChannel,
    MarketListRequest,
    MarketSubscription,
    RawBalance,
    RawExchangeEvent,
    RawFill,
    RawMarket,
    RawOpenOrder,
    RawPosition,
)
from pmrp.schemas.enums import Environment, MarketStatus
from pmrp.schemas.serialization import canonical_json, canonical_sha256


def _market_list_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "exchange": "kalshi",
        "environment": Environment.TEST,
        "requested_at": "2026-08-02T16:50:00Z",
        "correlation_id": "corr_01j00000000000000000000001",
        "limit": 100,
        "cursor": "next-page",
        "status_filter": (MarketStatus.OPEN, MarketStatus.HALTED),
        "include_closed": False,
    }
    payload.update(overrides)
    return payload


def _subscription_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "exchange": "kalshi",
        "environment": Environment.TEST,
        "exchange_market_id": "KXMARKET-25",
        "exchange_contract_id": "KXMARKET-25-YES",
        "channels": (MarketDataChannel.ORDER_BOOK, MarketDataChannel.TRADES),
        "depth": 20,
        "requested_at": "2026-08-02T16:50:00Z",
        "correlation_id": "corr_01j00000000000000000000001",
    }
    payload.update(overrides)
    return payload


def _raw_event_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "raw_record_id": "raw_01j00000000000000000000001",
        "exchange": "kalshi",
        "environment": Environment.TEST,
        "connection_id": "conn_01j00000000000000000000001",
        "endpoint": "/trade-api/v2/markets",
        "channel": "markets",
        "message_type": "snapshot",
        "received_at": "2026-08-02T16:50:00Z",
        "exchange_occurred_at": "2026-08-02T16:49:59Z",
        "sequence": 10,
        "content_type": "application/json",
        "compression": None,
        "payload_text": '{"ticker":"KXMARKET-25"}',
        "payload_bytes_b64": None,
        "payload_hash": "8cf852971bb0e67109c194ac90c08cb9648f9c6c821fd78e3b6a8f887cd849d8",
        "parser_version": "kalshi-market-v1",
        "transport_metadata": {"request_id": "req_01j00000000000000000000001"},
    }
    payload.update(overrides)
    return payload


def _raw_market_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "exchange": "kalshi",
        "environment": Environment.TEST,
        "exchange_market_id": "KXMARKET-25",
        "exchange_event_id": "KXEVENT-25",
        "status": MarketStatus.OPEN,
        "title": "Will the market resolve yes?",
        "raw_event": _raw_event_payload(),
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
def test_market_list_request_accepts_valid_payload() -> None:
    request = MarketListRequest.model_validate(_market_list_payload())

    assert request.exchange == "kalshi"
    assert request.environment is Environment.TEST
    assert request.status_filter == (MarketStatus.OPEN, MarketStatus.HALTED)


@pytest.mark.unit
def test_market_list_request_rejects_duplicate_status_filter() -> None:
    with pytest.raises(ValidationError, match="status_filter"):
        MarketListRequest.model_validate(
            _market_list_payload(status_filter=(MarketStatus.OPEN, MarketStatus.OPEN))
        )


@pytest.mark.unit
def test_market_list_request_rejects_raw_enum_string() -> None:
    with pytest.raises(ValidationError, match="Input should be an instance of Environment"):
        MarketListRequest.model_validate(_market_list_payload(environment="test"))


@pytest.mark.unit
def test_market_list_request_rejects_blank_cursor() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        MarketListRequest.model_validate(_market_list_payload(cursor=" next-page "))


@pytest.mark.unit
def test_market_subscription_accepts_valid_payload() -> None:
    subscription = MarketSubscription.model_validate(_subscription_payload())

    assert subscription.exchange_market_id == "KXMARKET-25"
    assert subscription.channels == (MarketDataChannel.ORDER_BOOK, MarketDataChannel.TRADES)


@pytest.mark.unit
def test_market_subscription_rejects_empty_channels() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        MarketSubscription.model_validate(_subscription_payload(channels=()))


@pytest.mark.unit
def test_market_subscription_rejects_duplicate_channels() -> None:
    with pytest.raises(ValidationError, match="channels"):
        MarketSubscription.model_validate(
            _subscription_payload(
                channels=(MarketDataChannel.ORDER_BOOK, MarketDataChannel.ORDER_BOOK),
            )
        )


@pytest.mark.unit
def test_market_subscription_rejects_nonpositive_depth() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        MarketSubscription.model_validate(_subscription_payload(depth=0))


@pytest.mark.unit
def test_raw_exchange_event_accepts_payload_text() -> None:
    event = RawExchangeEvent.model_validate(_raw_event_payload())

    assert event.exchange == "kalshi"
    assert event.payload_text == '{"ticker":"KXMARKET-25"}'
    assert event.payload_bytes_b64 is None
    assert event.transport_metadata == {"request_id": "req_01j00000000000000000000001"}


@pytest.mark.unit
def test_raw_exchange_event_accepts_payload_bytes_b64() -> None:
    event = RawExchangeEvent.model_validate(
        _raw_event_payload(payload_text=None, payload_bytes_b64="eyJ0aWNrZXIiOiJLWCJ9")
    )

    assert event.payload_text is None
    assert event.payload_bytes_b64 == "eyJ0aWNrZXIiOiJLWCJ9"


@pytest.mark.unit
def test_raw_exchange_event_rejects_missing_payload() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        RawExchangeEvent.model_validate(
            _raw_event_payload(payload_text=None, payload_bytes_b64=None)
        )


@pytest.mark.unit
def test_raw_exchange_event_rejects_duplicate_payload_storage() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        RawExchangeEvent.model_validate(
            _raw_event_payload(payload_bytes_b64="eyJ0aWNrZXIiOiJLWCJ9")
        )


@pytest.mark.unit
def test_raw_exchange_event_rejects_negative_sequence() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        RawExchangeEvent.model_validate(_raw_event_payload(sequence=-1))


@pytest.mark.unit
def test_raw_exchange_event_rejects_mutable_or_blank_metadata() -> None:
    with pytest.raises(ValidationError, match="nonempty strings"):
        RawExchangeEvent.model_validate(
            _raw_event_payload(transport_metadata={"request_id": " req "})
        )


@pytest.mark.unit
def test_raw_exchange_event_metadata_is_immutable_after_validation() -> None:
    event = RawExchangeEvent.model_validate(_raw_event_payload())

    with pytest.raises(TypeError):
        event.transport_metadata["request_id"] = "changed"


@pytest.mark.unit
def test_raw_market_accepts_matching_raw_event_scope() -> None:
    market = RawMarket.model_validate(_raw_market_payload())

    assert market.exchange_market_id == "KXMARKET-25"
    assert market.raw_event.exchange == market.exchange
    assert market.raw_event.environment is market.environment


@pytest.mark.unit
def test_raw_market_rejects_mismatched_raw_event_exchange() -> None:
    with pytest.raises(ValidationError, match="raw_event exchange"):
        RawMarket.model_validate(
            _raw_market_payload(raw_event=_raw_event_payload(exchange="polymarket"))
        )


@pytest.mark.unit
def test_raw_market_rejects_mismatched_raw_event_environment() -> None:
    with pytest.raises(ValidationError, match="raw_event environment"):
        RawMarket.model_validate(
            _raw_market_payload(raw_event=_raw_event_payload(environment=Environment.PRODUCTION))
        )


@pytest.mark.unit
def test_account_raw_response_wrappers_accept_matching_raw_event_scope() -> None:
    raw_event = RawExchangeEvent.model_validate(_raw_event_payload())

    open_order = RawOpenOrder.model_validate(
        {
            "exchange": "kalshi",
            "environment": Environment.TEST,
            "exchange_order_id": "order-123",
            "client_order_id": "client-123",
            "exchange_market_id": "KXMARKET-25",
            "raw_event": raw_event,
        }
    )
    position = RawPosition.model_validate(
        {
            "exchange": "kalshi",
            "environment": Environment.TEST,
            "exchange_position_id": "position-123",
            "exchange_market_id": "KXMARKET-25",
            "exchange_contract_id": "KXMARKET-25-YES",
            "raw_event": raw_event,
        }
    )
    balance = RawBalance.model_validate(
        {
            "exchange": "kalshi",
            "environment": Environment.TEST,
            "exchange_account_id": "account-123",
            "currency": "USDC",
            "raw_event": raw_event,
        }
    )
    fill = RawFill.model_validate(
        {
            "exchange": "kalshi",
            "environment": Environment.TEST,
            "exchange_fill_id": "fill-123",
            "exchange_order_id": "order-123",
            "raw_event": raw_event,
        }
    )

    assert open_order.raw_event is raw_event
    assert position.raw_event is raw_event
    assert balance.currency == "USDC"
    assert fill.exchange_fill_id == "fill-123"


@pytest.mark.unit
def test_boundary_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RawExchangeEvent.model_validate(_raw_event_payload(unexpected=True))


@pytest.mark.unit
def test_boundary_models_are_immutable_after_validation() -> None:
    event = RawExchangeEvent.model_validate(_raw_event_payload())
    original_hash = canonical_sha256(event)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        event.payload_hash = "changed"

    assert canonical_sha256(event) == original_hash


@pytest.mark.unit
def test_boundary_models_json_round_trip_and_stable_hash() -> None:
    market = RawMarket.model_validate(_raw_market_payload())
    canonical = canonical_json(market)

    assert '"transport_metadata":{"request_id":"req_01j00000000000000000000001"}' in canonical
    assert RawMarket.model_validate_json(canonical) == market
    assert canonical_sha256(market) == canonical_sha256(RawMarket.model_validate_json(canonical))


@pytest.mark.unit
def test_boundary_models_json_schema_generation() -> None:
    assert MarketListRequest.model_json_schema()["title"] == "MarketListRequest"
    assert MarketSubscription.model_json_schema()["title"] == "MarketSubscription"
    assert RawExchangeEvent.model_json_schema()["title"] == "RawExchangeEvent"
    assert RawMarket.model_json_schema()["title"] == "RawMarket"
