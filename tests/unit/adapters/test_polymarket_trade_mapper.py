"""Tests for Polymarket trade canonical mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters import AdapterProtocolError
from pmrp.adapters.polymarket import (
    POLYMARKET_TRADE_MAPPER_VERSION,
    PolymarketRawTrade,
    map_polymarket_trade,
    parse_polymarket_trade_json,
    parse_polymarket_trade_list_json,
)
from pmrp.schemas.enums import ExchangeName, LiquidityRole, Side
from pmrp.schemas.market_data import Trade
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "polymarket" / "trades"
MARKET_ID = "mkt_01j00000000000000000000000"
CONTRACT_ID = "ctr_01j00000000000000000000000"
OUTCOME_ID = "out_yes"
YES_ASSET_ID = "101010101010101010101010101010101010101010101010101010101010101010"
NO_ASSET_ID = "202020202020202020202020202020202020202020202020202020202020202020"


def _received_at() -> datetime:
    return datetime(2026, 6, 29, 17, 15, 58, 257000, tzinfo=UTC)


def _fixture_market_trade() -> PolymarketRawTrade:
    return parse_polymarket_trade_json((FIXTURE_ROOT / "trade.json").read_text())


def _fixture_rest_trade() -> PolymarketRawTrade:
    response = parse_polymarket_trade_list_json((FIXTURE_ROOT / "trade_list.json").read_text())
    return response.data[0]


def _trade_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_type": "last_trade_price",
        "market": "0x1111111111111111111111111111111111111111111111111111111111111111",
        "asset_id": YES_ASSET_ID,
        "side": "BUY",
        "price": "0.456",
        "size": "219.217767",
        "timestamp": "1782753357257",
    }
    payload.update(overrides)
    return payload


def test_polymarket_trade_mapper_version_is_stable() -> None:
    assert POLYMARKET_TRADE_MAPPER_VERSION == "polymarket_trade_mapper_v1"


def test_polymarket_trade_mapper_maps_market_channel_fixture() -> None:
    raw_trade = _fixture_market_trade()

    trade = map_polymarket_trade(
        raw_trade,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )

    assert trade.trade_id == f"polymarket:{raw_trade.transaction_hash}"
    assert trade.exchange == ExchangeName.POLYMARKET.value
    assert trade.exchange_trade_id == raw_trade.transaction_hash
    assert trade.market_id == MARKET_ID
    assert trade.contract_id == CONTRACT_ID
    assert trade.outcome_id == OUTCOME_ID
    assert trade.price == Decimal("0.456")
    assert trade.quantity == Decimal("219.217767")
    assert trade.aggressor_side is Side.BUY
    assert trade.liquidity_role is LiquidityRole.UNKNOWN
    assert trade.exchange_occurred_at == datetime(2026, 6, 29, 17, 15, 57, 257000, tzinfo=UTC)
    assert trade.received_at == _received_at()
    assert trade.sequence is None


def test_polymarket_trade_mapper_maps_rest_trade_id_and_match_time() -> None:
    trade = map_polymarket_trade(
        _fixture_rest_trade(),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )

    assert trade.trade_id == "polymarket:trade_fixture_0001"
    assert trade.exchange_trade_id == "trade_fixture_0001"
    assert trade.price == Decimal("0.5")
    assert trade.quantity == Decimal("100000000")
    assert trade.aggressor_side is Side.BUY
    assert trade.exchange_occurred_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_polymarket_trade_mapper_maps_sell_side() -> None:
    raw_trade = PolymarketRawTrade.from_exchange_payload(_trade_payload(side="SELL"))

    trade = map_polymarket_trade(
        raw_trade,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )

    assert trade.aggressor_side is Side.SELL


def test_polymarket_trade_mapper_uses_explicit_exchange_time_override() -> None:
    exchange_time = datetime(2026, 6, 29, 17, 16, tzinfo=UTC)

    trade = map_polymarket_trade(
        _fixture_market_trade(),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
        exchange_occurred_at=exchange_time,
    )

    assert trade.exchange_occurred_at == exchange_time


def test_polymarket_trade_mapper_generates_stable_identity_when_exchange_id_is_absent() -> None:
    raw_trade = PolymarketRawTrade.from_exchange_payload(
        _trade_payload(transaction_hash=None, id=None)
    )

    trade = map_polymarket_trade(
        raw_trade,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )

    assert trade.exchange_trade_id.startswith("generated:")
    assert trade.trade_id.startswith("polymarket:generated:")
    assert canonical_sha256(trade) == canonical_sha256(
        map_polymarket_trade(
            raw_trade,
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            expected_asset_id=YES_ASSET_ID,
            received_at=_received_at(),
        )
    )


def test_polymarket_trade_mapping_is_strict_immutable_and_stably_serialized() -> None:
    trade = map_polymarket_trade(
        _fixture_market_trade(),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )
    original_hash = canonical_sha256(trade)
    canonical = canonical_json(trade)

    assert '"exchange":"polymarket"' in canonical
    assert '"price":"0.456"' in canonical
    assert Trade.model_validate_json(canonical) == trade
    assert canonical_sha256(Trade.model_validate_json(canonical)) == original_hash
    with pytest.raises(ValidationError, match="Instance is frozen"):
        trade.sequence = 1


def test_polymarket_trade_mapper_rejects_asset_mismatch_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_trade(
            _fixture_market_trade(),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            expected_asset_id=NO_ASSET_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Polymarket trade asset id does not match expected contract"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert exc_info.value.context["exchange"] == ExchangeName.POLYMARKET.value
    assert exc_info.value.context["endpoint_category"] == "stream"
    assert exc_info.value.context["exchange_error_code"] == "polymarket_trade_asset_mismatch"
    assert "raw_payload" not in exc_info.value.context


def test_polymarket_trade_mapper_rejects_missing_size_safely() -> None:
    raw_trade = PolymarketRawTrade.from_exchange_payload(_trade_payload(size=None))

    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_trade(
            raw_trade,
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            expected_asset_id=YES_ASSET_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Polymarket trade mapping failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert exc_info.value.context["exchange_error_code"] == "polymarket_trade_mapping_failed"


def test_polymarket_trade_mapper_wraps_validation_errors_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_trade(
            _fixture_market_trade(),
            market_id="not_canonical",
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            expected_asset_id=YES_ASSET_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Polymarket trade mapping failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert exc_info.value.context["exchange_error_code"] == "polymarket_trade_mapping_failed"
    assert "synthetic redacted" not in str(exc_info.value)


def test_polymarket_trade_mapper_rejects_invalid_timestamp_safely() -> None:
    raw_trade = PolymarketRawTrade.from_exchange_payload(
        _trade_payload(timestamp="secret timestamp")
    )

    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_trade(
            raw_trade,
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            expected_asset_id=YES_ASSET_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Polymarket trade mapping failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert "secret timestamp" not in str(exc_info.value)


def test_polymarket_trade_mapper_rejects_naive_received_at_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_trade(
            _fixture_market_trade(),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            expected_asset_id=YES_ASSET_ID,
            received_at=datetime.fromisoformat("2026-06-29T17:15:58"),
        )

    assert str(exc_info.value) == "Polymarket trade mapping failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
