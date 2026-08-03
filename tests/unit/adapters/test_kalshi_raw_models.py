"""Tests for Kalshi raw market payload models."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters.kalshi import (
    KalshiMarketListResponse,
    KalshiRawMarket,
    parse_kalshi_market_list_json,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kalshi" / "markets"


def _market_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticker": "KX-PMRP-EXAMPLE-YES",
        "event_ticker": "KX-PMRP-EXAMPLE",
        "market_type": "binary",
        "title": "Will the PMRP fixture resolve yes?",
        "subtitle": "Redacted synthetic Kalshi market fixture",
        "category": "Technology",
        "status": "open",
        "open_time": "2026-08-02T18:00:00Z",
        "close_time": "2026-09-01T22:00:00Z",
        "expiration_time": "2026-09-01T23:00:00Z",
        "expected_expiration_time": "2026-09-01T23:00:00Z",
        "yes_bid": 47,
        "yes_ask": 48,
        "no_bid": 52,
        "no_ask": 53,
        "last_price": 47,
        "volume": 1250,
        "open_interest": 640,
        "tick_size": 1,
        "minimum_order_size": 1,
    }
    payload.update(overrides)
    return payload


def _response_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "markets": [_market_payload()],
        "cursor": "cursor_fixture_markets_002",
    }
    payload.update(overrides)
    return payload


def test_kalshi_raw_market_preserves_original_payload() -> None:
    payload = _market_payload(exchange_extra_field="preserved")

    market = KalshiRawMarket.from_exchange_payload(payload)

    assert market.ticker == "KX-PMRP-EXAMPLE-YES"
    assert market.raw_payload["exchange_extra_field"] == "preserved"


def test_kalshi_raw_market_rejects_unknown_model_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        KalshiRawMarket.model_validate(
            {
                **_market_payload(),
                "raw_payload": _market_payload(),
                "unexpected": "not allowed outside raw_payload",
            }
        )


def test_kalshi_raw_market_rejects_blank_text() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        KalshiRawMarket.from_exchange_payload(_market_payload(ticker=" KX-PMRP "))


def test_kalshi_raw_market_rejects_float_prices() -> None:
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        KalshiRawMarket.from_exchange_payload(_market_payload(yes_bid=47.5))


def test_kalshi_raw_market_rejects_price_outside_cent_range() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 100"):
        KalshiRawMarket.from_exchange_payload(_market_payload(yes_ask=101))


def test_kalshi_raw_market_rejects_close_before_open() -> None:
    with pytest.raises(ValidationError, match="close_time"):
        KalshiRawMarket.from_exchange_payload(
            _market_payload(
                open_time="2026-09-01T22:00:00Z",
                close_time="2026-08-02T18:00:00Z",
            )
        )


def test_kalshi_market_list_response_accepts_decoded_payload_and_preserves_raw_payload() -> None:
    response = KalshiMarketListResponse.from_exchange_payload(
        _response_payload(exchange_response_extra="preserved")
    )

    assert len(response.markets) == 1
    assert response.cursor == "cursor_fixture_markets_002"
    assert response.raw_payload["exchange_response_extra"] == "preserved"


def test_kalshi_market_list_response_rejects_missing_markets_array() -> None:
    with pytest.raises(ValueError, match="markets array"):
        KalshiMarketListResponse.from_exchange_payload({"cursor": None})


def test_kalshi_market_list_response_rejects_duplicate_tickers() -> None:
    market = _market_payload()

    with pytest.raises(ValidationError, match="duplicate tickers"):
        KalshiMarketListResponse.from_exchange_payload({"markets": [market, market]})


def test_kalshi_market_list_response_rejects_blank_cursor() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        KalshiMarketListResponse.from_exchange_payload(_response_payload(cursor=" cursor "))


@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    [
        ("list_success.json", "open"),
        ("optional_fields.json", "open"),
        ("unknown_status.json", "exchange_specific_future_status"),
    ],
)
def test_kalshi_market_fixtures_parse(fixture_name: str, expected_status: str) -> None:
    response = parse_kalshi_market_list_json((FIXTURE_ROOT / fixture_name).read_text())

    assert response.markets[0].status == expected_status


def test_kalshi_unknown_status_fixture_preserves_unknown_fields() -> None:
    response = parse_kalshi_market_list_json((FIXTURE_ROOT / "unknown_status.json").read_text())

    assert response.markets[0].raw_payload["unexpected_status_reason"] == (
        "synthetic redacted fixture value"
    )


def test_kalshi_optional_fields_fixture_allows_absent_optional_fields() -> None:
    response = parse_kalshi_market_list_json((FIXTURE_ROOT / "optional_fields.json").read_text())
    market = response.markets[0]

    assert market.subtitle is None
    assert market.open_time is None
    assert market.no_bid is None


def test_kalshi_market_list_json_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        parse_kalshi_market_list_json("{")


def test_kalshi_market_list_json_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_kalshi_market_list_json("[]")


def test_kalshi_raw_models_are_immutable_after_validation() -> None:
    response = KalshiMarketListResponse.from_exchange_payload(_response_payload())
    original_hash = canonical_sha256(response)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        response.cursor = None
    with pytest.raises(TypeError):
        response.raw_payload["cursor"] = None

    assert canonical_sha256(response) == original_hash


def test_kalshi_raw_models_json_round_trip_and_stable_hash() -> None:
    response = KalshiMarketListResponse.from_exchange_payload(_response_payload())
    canonical = canonical_json(response)

    assert '"ticker":"KX-PMRP-EXAMPLE-YES"' in canonical
    assert KalshiMarketListResponse.model_validate_json(canonical) == response
    assert canonical_sha256(response) == canonical_sha256(
        KalshiMarketListResponse.model_validate_json(canonical)
    )


def test_kalshi_raw_models_json_schema_generation() -> None:
    assert KalshiRawMarket.model_json_schema()["title"] == "KalshiRawMarket"
    assert KalshiMarketListResponse.model_json_schema()["title"] == "KalshiMarketListResponse"
