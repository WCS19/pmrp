"""Tests for Kalshi raw trade payload models."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters.kalshi import KalshiRawTrade, parse_kalshi_trade_json
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kalshi" / "trades"


def _trade_payload(
    *,
    msg_overrides: Mapping[str, object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    msg: dict[str, object] = {
        "trade_id": "trade_fixture_0001",
        "market_ticker": "KX-PMRP-EXAMPLE-YES",
        "yes_price": 47,
        "no_price": 53,
        "count": 18,
        "taker_side": "yes",
        "created_time": "2026-08-02T18:05:00Z",
    }
    if msg_overrides is not None:
        msg.update(msg_overrides)
    payload: dict[str, object] = {
        "type": "trade",
        "sid": 52,
        "seq": 2101,
        "msg": msg,
    }
    payload.update(overrides)
    return payload


def test_kalshi_trade_fixture_parses_and_preserves_raw_payload() -> None:
    trade = parse_kalshi_trade_json((FIXTURE_ROOT / "trade.json").read_text())

    assert trade.trade_id == "trade_fixture_0001"
    assert trade.market_ticker == "KX-PMRP-EXAMPLE-YES"
    assert trade.subscription_id == 52
    assert trade.sequence == 2101
    assert trade.yes_price == 47
    assert trade.no_price == 53
    assert trade.count == 18
    assert trade.taker_side == "yes"
    assert trade.created_time.isoformat() == "2026-08-02T18:05:00+00:00"
    assert trade.raw_payload["type"] == "trade"


def test_kalshi_duplicate_trade_fixture_preserves_exchange_trade_identity() -> None:
    original = parse_kalshi_trade_json((FIXTURE_ROOT / "trade.json").read_text())
    duplicate = parse_kalshi_trade_json((FIXTURE_ROOT / "duplicate_trade.json").read_text())

    assert duplicate.trade_id == original.trade_id
    assert duplicate.sequence == 2102
    assert canonical_sha256(duplicate) != canonical_sha256(original)


def test_kalshi_trade_missing_optional_fields_fixture_parses() -> None:
    trade = parse_kalshi_trade_json((FIXTURE_ROOT / "missing_optional_field.json").read_text())

    assert trade.trade_id == "trade_fixture_0002"
    assert trade.sequence is None
    assert trade.no_price is None
    assert trade.taker_side is None
    assert trade.yes_price == 48


def test_kalshi_trade_accepts_alternate_exchange_field_names() -> None:
    trade = KalshiRawTrade.from_exchange_payload(
        {
            "message_type": "trade",
            "subscription_id": 52,
            "sequence": 2101,
            "id": "trade_fixture_0001",
            "market_ticker": "KX-PMRP-EXAMPLE-YES",
            "price": 47,
            "quantity": 18,
            "side": "yes",
            "created_at": "2026-08-02T18:05:00Z",
        }
    )

    assert trade.trade_id == "trade_fixture_0001"
    assert trade.yes_price == 47
    assert trade.count == 18
    assert trade.taker_side == "yes"


def test_kalshi_trade_rejects_unknown_model_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        KalshiRawTrade.model_validate(
            {
                "trade_id": "trade_fixture_0001",
                "market_ticker": "KX-PMRP-EXAMPLE-YES",
                "yes_price": 47,
                "count": 18,
                "created_time": "2026-08-02T18:05:00Z",
                "raw_payload": _trade_payload(),
                "unexpected": "not allowed outside raw_payload",
            }
        )


def test_kalshi_trade_rejects_blank_text_fields() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        KalshiRawTrade.from_exchange_payload(
            _trade_payload(msg_overrides={"trade_id": " trade_fixture_0001 "})
        )
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        KalshiRawTrade.from_exchange_payload(_trade_payload(msg_overrides={"taker_side": " yes "}))


def test_kalshi_trade_rejects_float_prices_and_quantities() -> None:
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        KalshiRawTrade.from_exchange_payload(_trade_payload(msg_overrides={"yes_price": 47.5}))
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        KalshiRawTrade.from_exchange_payload(_trade_payload(msg_overrides={"count": 18.5}))


def test_kalshi_trade_rejects_nonpositive_quantity() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        KalshiRawTrade.from_exchange_payload(_trade_payload(msg_overrides={"count": 0}))


def test_kalshi_trade_rejects_price_outside_cent_range() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 100"):
        KalshiRawTrade.from_exchange_payload(_trade_payload(msg_overrides={"yes_price": 101}))


def test_kalshi_trade_requires_at_least_one_price() -> None:
    with pytest.raises(ValidationError, match="at least one raw price"):
        KalshiRawTrade.from_exchange_payload(
            _trade_payload(msg_overrides={"yes_price": None, "no_price": None})
        )


def test_kalshi_trade_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="trade_id is required"):
        KalshiRawTrade.from_exchange_payload(_trade_payload(msg_overrides={"trade_id": None}))
    with pytest.raises(ValueError, match="created_time is required"):
        KalshiRawTrade.from_exchange_payload(_trade_payload(msg_overrides={"created_time": None}))


def test_kalshi_trade_rejects_naive_created_time() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        KalshiRawTrade.from_exchange_payload(
            _trade_payload(msg_overrides={"created_time": "2026-08-02T18:05:00"})
        )


def test_kalshi_trade_json_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        parse_kalshi_trade_json("{")


def test_kalshi_trade_json_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_kalshi_trade_json("[]")


def test_kalshi_trade_raw_payload_is_immutable_after_validation() -> None:
    trade = KalshiRawTrade.from_exchange_payload(_trade_payload())
    original_hash = canonical_sha256(trade)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        trade.sequence = 2102
    with pytest.raises(TypeError):
        trade.raw_payload["seq"] = 2102

    assert canonical_sha256(trade) == original_hash


def test_kalshi_trade_json_round_trip_and_stable_hash() -> None:
    trade = KalshiRawTrade.from_exchange_payload(_trade_payload())
    canonical = canonical_json(trade)

    assert '"trade_id":"trade_fixture_0001"' in canonical
    assert KalshiRawTrade.model_validate_json(canonical) == trade
    assert canonical_sha256(trade) == canonical_sha256(
        KalshiRawTrade.model_validate_json(canonical)
    )


def test_kalshi_trade_json_schema_generation() -> None:
    assert KalshiRawTrade.model_json_schema()["title"] == "KalshiRawTrade"
