"""Tests for Polymarket raw payload models."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters.polymarket import (
    PolymarketMarketListResponse,
    PolymarketRawErrorResponse,
    PolymarketRawMarket,
    PolymarketRawOrderBookLevel,
    PolymarketRawOrderBookSnapshot,
    PolymarketRawPriceChange,
    PolymarketRawPriceChangeMessage,
    PolymarketRawTrade,
    parse_polymarket_error_json,
    parse_polymarket_market_list_json,
    parse_polymarket_order_book_json,
    parse_polymarket_price_change_json,
    parse_polymarket_trade_json,
    parse_polymarket_trade_list_json,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "polymarket"


def _market_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "pm_market_fixture_0001",
        "question": "Will the PMRP fixture market resolve yes?",
        "conditionId": "0x1111111111111111111111111111111111111111111111111111111111111111",
        "questionID": "0x2222222222222222222222222222222222222222222222222222222222222222",
        "slug": "pmrp-fixture-market",
        "category": "Technology",
        "active": True,
        "closed": False,
        "archived": False,
        "enableOrderBook": True,
        "negRisk": False,
        "outcomes": '["Yes","No"]',
        "outcomePrices": '["0.42","0.58"]',
        "clobTokenIds": (
            '["101010101010101010101010101010101010101010101010101010101010101010",'
            '"202020202020202020202020202020202020202020202020202020202020202020"]'
        ),
        "volume": "1234.50",
        "liquidity": "987.65",
        "orderPriceMinTickSize": "0.01",
        "orderMinSize": "5",
        "startDate": "2026-08-01T00:00:00Z",
        "endDate": "2026-12-31T00:00:00Z",
        "createdAt": "2026-07-15T12:00:00Z",
        "updatedAt": "2026-08-02T18:00:00Z",
    }
    payload.update(overrides)
    return payload


def _order_book_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "book",
        "market": "0x1111111111111111111111111111111111111111111111111111111111111111",
        "asset_id": "101010101010101010101010101010101010101010101010101010101010101010",
        "timestamp": "1757908892351",
        "hash": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "bids": [{"price": "0.48", "size": "1000"}],
        "asks": [{"price": "0.52", "size": "800"}],
        "min_order_size": "5",
        "tick_size": "0.01",
        "neg_risk": False,
        "last_trade_price": "0.49",
    }
    payload.update(overrides)
    return payload


def _price_change_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "price_change",
        "market": "0x1111111111111111111111111111111111111111111111111111111111111111",
        "timestamp": "1757908892352",
        "price_changes": [
            {
                "asset_id": "101010101010101010101010101010101010101010101010101010101010101010",
                "price": "0.50",
                "size": "200",
                "side": "BUY",
                "best_bid": "0.50",
                "best_ask": "0.52",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _trade_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "last_trade_price",
        "asset_id": "101010101010101010101010101010101010101010101010101010101010101010",
        "fee_rate_bps": "0",
        "market": "0x1111111111111111111111111111111111111111111111111111111111111111",
        "price": "0.456",
        "side": "BUY",
        "size": "219.217767",
        "timestamp": "1757908892353",
    }
    payload.update(overrides)
    return payload


def test_polymarket_market_list_fixture_parses_and_preserves_raw_payload() -> None:
    response = parse_polymarket_market_list_json(
        (FIXTURE_ROOT / "markets" / "list_success.json").read_text()
    )
    market = response.markets[0]

    assert market.market_id == "pm_market_fixture_0001"
    assert market.condition_id.startswith("0x1111")
    assert market.outcomes == ("Yes", "No")
    assert market.outcome_prices == (Decimal("0.42"), Decimal("0.58"))
    assert len(market.clob_token_ids) == 2
    assert market.enable_order_book is True
    assert market.volume == Decimal("1234.50")
    assert isinstance(response.raw_payload, tuple)
    assert response.raw_payload[0]["fixture_note"] == "synthetic redacted Polymarket market"


def test_polymarket_market_list_accepts_object_wrapped_payload() -> None:
    response = PolymarketMarketListResponse.from_exchange_payload(
        {"markets": [_market_payload()], "next_cursor": "cursor_fixture_001"}
    )

    assert response.markets[0].question == "Will the PMRP fixture market resolve yes?"
    assert response.next_cursor == "cursor_fixture_001"
    assert response.raw_payload["next_cursor"] == "cursor_fixture_001"


def test_polymarket_market_rejects_mismatched_outcome_token_mapping() -> None:
    with pytest.raises(ValidationError, match="map one-to-one"):
        PolymarketRawMarket.from_exchange_payload(
            _market_payload(clobTokenIds='["101010101010101010101010101010101010"]')
        )


def test_polymarket_market_rejects_float_financial_fields() -> None:
    with pytest.raises(TypeError, match="float input"):
        PolymarketRawMarket.from_exchange_payload(_market_payload(volume=1.5))


def test_polymarket_market_raw_payload_is_immutable_after_validation() -> None:
    market = PolymarketRawMarket.from_exchange_payload(_market_payload())
    original_hash = canonical_sha256(market)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        market.question = "Changed"
    with pytest.raises(TypeError):
        market.raw_payload["question"] = "Changed"

    assert canonical_sha256(market) == original_hash


def test_polymarket_order_book_fixture_parses_decimal_levels() -> None:
    snapshot = parse_polymarket_order_book_json(
        (FIXTURE_ROOT / "order_book" / "snapshot.json").read_text()
    )

    assert snapshot.topic == "market"
    assert snapshot.event_type == "book"
    assert snapshot.asset_id.startswith("101010")
    assert snapshot.timestamp == "2026-06-29T17:15:57.257000Z"
    assert snapshot.bids[0].price == Decimal("0.48")
    assert snapshot.bids[0].size == Decimal("1000")
    assert snapshot.asks[1].price == Decimal("0.53")
    assert snapshot.tick_size == Decimal("0.01")
    assert snapshot.last_trade_price == Decimal("0.49")
    assert snapshot.raw_payload["fixture_note"] == "synthetic redacted Polymarket order book"


def test_polymarket_order_book_rejects_float_prices_and_invalid_json() -> None:
    with pytest.raises(TypeError, match="float input"):
        PolymarketRawOrderBookLevel.model_validate({"price": 0.48, "size": "1000"})
    with pytest.raises(ValueError, match="valid JSON"):
        parse_polymarket_order_book_json("{")
    with pytest.raises(ValueError, match="JSON object"):
        parse_polymarket_order_book_json("[]")


def test_polymarket_order_book_json_round_trip_and_stable_hash() -> None:
    snapshot = PolymarketRawOrderBookSnapshot.from_exchange_payload(_order_book_payload())
    canonical = canonical_json(snapshot)

    assert '"price":"0.48"' in canonical
    assert PolymarketRawOrderBookSnapshot.model_validate_json(canonical) == snapshot
    assert canonical_sha256(snapshot) == canonical_sha256(
        PolymarketRawOrderBookSnapshot.model_validate_json(canonical)
    )


def test_polymarket_price_change_fixture_parses_with_zero_size_removal() -> None:
    message = parse_polymarket_price_change_json(
        (FIXTURE_ROOT / "order_book" / "price_change.json").read_text()
    )

    assert message.topic == "market"
    assert message.event_type == "price_change"
    assert message.timestamp == "1782753357257"
    assert len(message.price_changes) == 2
    assert message.price_changes[0].side == "BUY"
    assert message.price_changes[1].side == "SELL"
    assert message.price_changes[1].size == Decimal("0")
    assert message.price_changes[0].best_bid == Decimal("0.50")


def test_polymarket_price_change_rejects_empty_changes_and_unknown_side() -> None:
    with pytest.raises(ValidationError, match="at least one change"):
        PolymarketRawPriceChangeMessage.from_exchange_payload(
            _price_change_payload(price_changes=[])
        )
    with pytest.raises(ValidationError, match="Input should be 'BUY' or 'SELL'"):
        PolymarketRawPriceChange.from_exchange_payload(
            {
                "asset_id": "101010101010101010101010101010101010",
                "price": "0.50",
                "size": "200",
                "side": "BID",
            }
        )


def test_polymarket_trade_fixture_parses_market_channel_trade() -> None:
    trade = parse_polymarket_trade_json((FIXTURE_ROOT / "trades" / "trade.json").read_text())

    assert trade.topic == "market"
    assert trade.event_type == "last_trade_price"
    assert trade.asset_id.startswith("101010")
    assert trade.price == Decimal("0.456")
    assert trade.size == Decimal("219.217767")
    assert trade.fee_rate_bps == 0
    assert trade.transaction_hash is not None
    assert trade.side == "BUY"
    assert trade.timestamp == "1782753357257"


def test_polymarket_trade_accepts_market_channel_trade_without_size() -> None:
    trade = PolymarketRawTrade.from_exchange_payload(
        {
            "topic": "market",
            "type": "last_trade_price",
            "payload": {
                "tokenId": ("101010101010101010101010101010101010101010101010101010101010101010"),
                "market": ("0x1111111111111111111111111111111111111111111111111111111111111111"),
                "price": "0.456",
                "side": "SELL",
                "timestamp": "1782753357257",
            },
        }
    )

    assert trade.size is None
    assert trade.side == "SELL"
    assert trade.asset_id.startswith("101010")


def test_polymarket_trade_list_fixture_parses_authenticated_trade_shape() -> None:
    response = parse_polymarket_trade_list_json(
        (FIXTURE_ROOT / "trades" / "trade_list.json").read_text()
    )
    trade = response.data[0]

    assert response.limit == 100
    assert response.count == 1
    assert response.next_cursor == "MTAw"
    assert trade.trade_id == "trade_fixture_0001"
    assert trade.transaction_hash is not None
    assert trade.fee_rate_bps == 30
    assert trade.bucket_index == 0
    assert response.raw_payload["fixture_note"] == "synthetic redacted Polymarket trade list"


def test_polymarket_trade_rejects_float_price_and_nonpositive_size() -> None:
    with pytest.raises(TypeError, match="float input"):
        PolymarketRawTrade.from_exchange_payload(_trade_payload(price=0.456))
    with pytest.raises(ValidationError, match="greater than 0"):
        PolymarketRawTrade.from_exchange_payload(_trade_payload(size="0"))


def test_polymarket_trade_requires_identity_hint() -> None:
    with pytest.raises(ValidationError, match="trade id, transaction hash, or timestamp"):
        PolymarketRawTrade.from_exchange_payload(_trade_payload(timestamp=None))


def test_polymarket_error_fixture_parses_and_preserves_raw_payload() -> None:
    error = parse_polymarket_error_json((FIXTURE_ROOT / "errors" / "bad_request.json").read_text())

    assert error.http_status == 400
    assert error.error_code == "invalid_request"
    assert error.message == "invalid token id"
    assert error.raw_payload["fixture_note"] == "synthetic redacted Polymarket error"


def test_polymarket_error_rejects_payload_without_code_or_message() -> None:
    with pytest.raises(ValidationError, match="error code or message"):
        PolymarketRawErrorResponse.from_exchange_payload({"status_code": 400})


def test_polymarket_raw_models_generate_json_schema() -> None:
    assert PolymarketRawMarket.model_json_schema()["title"] == "PolymarketRawMarket"
    assert PolymarketRawOrderBookSnapshot.model_json_schema()["title"] == (
        "PolymarketRawOrderBookSnapshot"
    )
    assert PolymarketRawTrade.model_json_schema()["title"] == "PolymarketRawTrade"
