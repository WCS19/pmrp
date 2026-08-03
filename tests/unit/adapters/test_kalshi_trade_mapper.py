"""Tests for Kalshi trade canonical mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters import AdapterProtocolError
from pmrp.adapters.kalshi import (
    KALSHI_TRADE_MAPPER_VERSION,
    KalshiRawTrade,
    map_kalshi_trade,
    parse_kalshi_trade_json,
)
from pmrp.schemas.enums import ExchangeName, LiquidityRole, Side
from pmrp.schemas.market_data import Trade
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kalshi" / "trades"
MARKET_ID = "mkt_01j00000000000000000000000"
CONTRACT_ID = "ctr_01j00000000000000000000000"
OUTCOME_ID = "out_yes"
NO_OUTCOME_ID = "out_no"


def _received_at() -> datetime:
    return datetime(2026, 8, 2, 18, 5, 1, 123456, tzinfo=UTC)


def _fixture(name: str) -> KalshiRawTrade:
    return parse_kalshi_trade_json((FIXTURE_ROOT / name).read_text())


def _trade_payload(**msg_overrides: object) -> dict[str, object]:
    msg: dict[str, object] = {
        "trade_id": "trade_fixture_0003",
        "market_ticker": "KX-PMRP-EXAMPLE-YES",
        "yes_price": 47,
        "no_price": 53,
        "count": 18,
        "taker_side": "yes",
        "created_time": "2026-08-02T18:05:00Z",
    }
    msg.update(msg_overrides)
    return {
        "type": "trade",
        "sid": 52,
        "seq": 2103,
        "msg": msg,
    }


def test_kalshi_trade_mapper_version_is_stable() -> None:
    assert KALSHI_TRADE_MAPPER_VERSION == "kalshi_trade_mapper_v1"


def test_kalshi_trade_mapper_maps_fixture_to_yes_outcome_trade() -> None:
    trade = map_kalshi_trade(
        _fixture("trade.json"),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        received_at=_received_at(),
    )

    assert trade.trade_id == "kalshi:trade_fixture_0001"
    assert trade.exchange == ExchangeName.KALSHI.value
    assert trade.exchange_trade_id == "trade_fixture_0001"
    assert trade.market_id == MARKET_ID
    assert trade.contract_id == CONTRACT_ID
    assert trade.outcome_id == OUTCOME_ID
    assert trade.price == Decimal("0.47")
    assert trade.quantity == Decimal("18")
    assert trade.aggressor_side is Side.BUY
    assert trade.liquidity_role is LiquidityRole.UNKNOWN
    assert trade.exchange_occurred_at == datetime(2026, 8, 2, 18, 5, tzinfo=UTC)
    assert trade.received_at == _received_at()
    assert trade.sequence == 2101


def test_kalshi_trade_mapper_maps_no_outcome_price_and_relative_aggressor_side() -> None:
    trade = map_kalshi_trade(
        _fixture("trade.json"),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=NO_OUTCOME_ID,
        received_at=_received_at(),
        outcome_side="no",
    )

    assert trade.outcome_id == NO_OUTCOME_ID
    assert trade.price == Decimal("0.53")
    assert trade.aggressor_side is Side.SELL


def test_kalshi_trade_mapper_maps_no_taker_to_buy_for_no_outcome_and_sell_for_yes() -> None:
    raw_trade = KalshiRawTrade.from_exchange_payload(_trade_payload(taker_side="no"))

    yes_trade = map_kalshi_trade(
        raw_trade,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        received_at=_received_at(),
    )
    no_trade = map_kalshi_trade(
        raw_trade,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=NO_OUTCOME_ID,
        received_at=_received_at(),
        outcome_side="no",
    )

    assert yes_trade.aggressor_side is Side.SELL
    assert no_trade.aggressor_side is Side.BUY


def test_kalshi_trade_mapper_infers_missing_direct_outcome_price_from_complement() -> None:
    raw_trade = _fixture("missing_optional_field.json")

    yes_trade = map_kalshi_trade(
        raw_trade,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        received_at=_received_at(),
    )
    no_trade = map_kalshi_trade(
        raw_trade,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=NO_OUTCOME_ID,
        received_at=_received_at(),
        outcome_side="no",
    )

    assert yes_trade.price == Decimal("0.48")
    assert no_trade.price == Decimal("0.52")
    assert yes_trade.sequence is None
    assert yes_trade.aggressor_side is None


def test_kalshi_trade_mapping_is_strict_immutable_and_stably_serialized() -> None:
    trade = map_kalshi_trade(
        _fixture("trade.json"),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        received_at=_received_at(),
    )
    original_hash = canonical_sha256(trade)
    canonical = canonical_json(trade)

    assert '"price":"0.47"' in canonical
    assert Trade.model_validate_json(canonical) == trade
    assert canonical_sha256(Trade.model_validate_json(canonical)) == original_hash
    with pytest.raises(ValidationError, match="Instance is frozen"):
        trade.sequence = 2102


def test_kalshi_trade_mapper_rejects_unknown_outcome_side_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_kalshi_trade(
            _fixture("trade.json"),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            received_at=_received_at(),
            outcome_side="maybe",
        )

    assert str(exc_info.value) == "Kalshi trade mapping failed"
    assert exc_info.value.context["exchange_error_code"] == "kalshi_trade_mapping_failed"
    assert exc_info.value.context["exchange_trade_id"] == "trade_fixture_0001"
    assert "raw_payload" not in exc_info.value.context


def test_kalshi_trade_mapper_rejects_unknown_taker_side_safely() -> None:
    raw_trade = KalshiRawTrade.from_exchange_payload(_trade_payload(taker_side="unexpected_side"))

    with pytest.raises(AdapterProtocolError) as exc_info:
        map_kalshi_trade(
            raw_trade,
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Kalshi trade taker side is unsupported"
    assert exc_info.value.context["exchange_error_code"] == "kalshi_trade_taker_side_unsupported"
    assert exc_info.value.context["taker_side"] == "unexpected_side"


def test_kalshi_trade_mapper_wraps_canonical_validation_errors_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_kalshi_trade(
            _fixture("trade.json"),
            market_id="not_canonical",
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Kalshi trade mapping failed"
    assert exc_info.value.context["exchange_error_code"] == "kalshi_trade_mapping_failed"
    assert "synthetic redacted" not in str(exc_info.value)


def test_kalshi_trade_mapper_rejects_naive_received_at_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_kalshi_trade(
            _fixture("trade.json"),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            outcome_id=OUTCOME_ID,
            received_at=datetime.fromisoformat("2026-08-02T18:05:01"),
        )

    assert str(exc_info.value) == "Kalshi trade mapping failed"
    assert exc_info.value.context["sequence"] == "2101"
