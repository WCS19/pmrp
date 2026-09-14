"""Tests for Polymarket order-book canonical mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters import AdapterProtocolError
from pmrp.adapters.polymarket import (
    POLYMARKET_ORDER_BOOK_MAPPER_VERSION,
    PolymarketRawOrderBookSnapshot,
    PolymarketRawPriceChangeMessage,
    map_polymarket_order_book_delta,
    map_polymarket_order_book_message,
    map_polymarket_order_book_snapshot,
    parse_polymarket_order_book_json,
    parse_polymarket_price_change_json,
)
from pmrp.schemas.enums import ExchangeName, Side
from pmrp.schemas.market_data import OrderBookDelta, OrderBookDeltaAction, OrderBookSnapshot
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "polymarket" / "order_book"
MARKET_ID = "mkt_01j00000000000000000000000"
CONTRACT_ID = "ctr_01j00000000000000000000000"
YES_ASSET_ID = "101010101010101010101010101010101010101010101010101010101010101010"
NO_ASSET_ID = "202020202020202020202020202020202020202020202020202020202020202020"


def _received_at() -> datetime:
    return datetime(2026, 6, 29, 17, 15, 58, 257000, tzinfo=UTC)


def _fixture_snapshot() -> PolymarketRawOrderBookSnapshot:
    return parse_polymarket_order_book_json((FIXTURE_ROOT / "snapshot.json").read_text())


def _fixture_price_change() -> PolymarketRawPriceChangeMessage:
    return parse_polymarket_price_change_json((FIXTURE_ROOT / "price_change.json").read_text())


def test_polymarket_order_book_mapper_version_is_stable() -> None:
    assert POLYMARKET_ORDER_BOOK_MAPPER_VERSION == "polymarket_order_book_mapper_v1"


def test_polymarket_order_book_snapshot_maps_direct_token_book_exactly() -> None:
    snapshot = map_polymarket_order_book_snapshot(
        _fixture_snapshot(),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )

    assert snapshot.market_id == MARKET_ID
    assert snapshot.contract_id == CONTRACT_ID
    assert snapshot.exchange == ExchangeName.POLYMARKET.value
    assert snapshot.sequence is None
    assert snapshot.exchange_occurred_at == datetime(2026, 6, 29, 17, 15, 57, 257000, tzinfo=UTC)
    assert snapshot.received_at == _received_at()
    assert [(level.price, level.quantity) for level in snapshot.bids] == [
        (Decimal("0.48"), Decimal("1000")),
        (Decimal("0.47"), Decimal("2500")),
    ]
    assert [(level.price, level.quantity) for level in snapshot.asks] == [
        (Decimal("0.52"), Decimal("800")),
        (Decimal("0.53"), Decimal("1500")),
    ]
    assert snapshot.is_valid is True
    assert snapshot.snapshot_reason == "initial"


def test_polymarket_order_book_snapshot_sorts_canonical_levels() -> None:
    message = PolymarketRawOrderBookSnapshot.from_exchange_payload(
        {
            "event_type": "book",
            "market": "0x1111111111111111111111111111111111111111111111111111111111111111",
            "asset_id": YES_ASSET_ID,
            "timestamp": "1782753357257",
            "bids": [
                {"price": "0.45", "size": "1"},
                {"price": "0.49", "size": "2"},
                {"price": "0.46", "size": "3"},
            ],
            "asks": [
                {"price": "0.55", "size": "4"},
                {"price": "0.51", "size": "5"},
                {"price": "0.52", "size": "6"},
            ],
        }
    )

    snapshot = map_polymarket_order_book_snapshot(
        message,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
        snapshot_reason="recovery",
    )

    assert [level.price for level in snapshot.bids] == [
        Decimal("0.49"),
        Decimal("0.46"),
        Decimal("0.45"),
    ]
    assert [level.price for level in snapshot.asks] == [
        Decimal("0.51"),
        Decimal("0.52"),
        Decimal("0.55"),
    ]
    assert snapshot.snapshot_reason == "recovery"


def test_polymarket_price_change_maps_expected_token_delta_only() -> None:
    delta = map_polymarket_order_book_delta(
        _fixture_price_change(),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )

    assert delta.market_id == MARKET_ID
    assert delta.contract_id == CONTRACT_ID
    assert delta.exchange == ExchangeName.POLYMARKET.value
    assert delta.sequence is None
    assert delta.previous_sequence is None
    assert delta.exchange_occurred_at == datetime(2026, 6, 29, 17, 15, 57, 257000, tzinfo=UTC)
    assert len(delta.changes) == 1
    change = delta.changes[0]
    assert change.side is Side.BUY
    assert change.price == Decimal("0.50")
    assert change.quantity == Decimal("200")
    assert change.action is OrderBookDeltaAction.UPSERT


def test_polymarket_zero_size_sell_change_maps_to_delete() -> None:
    delta = map_polymarket_order_book_delta(
        _fixture_price_change(),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        expected_asset_id=NO_ASSET_ID,
        received_at=_received_at(),
    )

    assert len(delta.changes) == 1
    change = delta.changes[0]
    assert change.side is Side.SELL
    assert change.price == Decimal("0.50")
    assert change.quantity == Decimal("0")
    assert change.action is OrderBookDeltaAction.DELETE


@pytest.mark.parametrize(
    ("message", "expected_type"),
    [
        (_fixture_snapshot(), OrderBookSnapshot),
        (_fixture_price_change(), OrderBookDelta),
    ],
)
def test_polymarket_order_book_message_mapper_dispatches_by_raw_model(
    message: PolymarketRawOrderBookSnapshot | PolymarketRawPriceChangeMessage,
    expected_type: type[OrderBookSnapshot] | type[OrderBookDelta],
) -> None:
    mapped = map_polymarket_order_book_message(
        message,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )

    assert isinstance(mapped, expected_type)


def test_polymarket_order_book_mapping_is_strict_immutable_and_stably_serialized() -> None:
    mapped = map_polymarket_order_book_snapshot(
        _fixture_snapshot(),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )
    original_hash = canonical_sha256(mapped)
    canonical = canonical_json(mapped)

    assert '"exchange":"polymarket"' in canonical
    assert OrderBookSnapshot.model_validate_json(canonical) == mapped
    assert canonical_sha256(OrderBookSnapshot.model_validate_json(canonical)) == original_hash
    with pytest.raises(ValidationError, match="Instance is frozen"):
        mapped.snapshot_reason = "changed"


def test_polymarket_order_book_delta_json_round_trip_is_stable() -> None:
    mapped = map_polymarket_order_book_delta(
        _fixture_price_change(),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        expected_asset_id=YES_ASSET_ID,
        received_at=_received_at(),
    )
    original_hash = canonical_sha256(mapped)
    canonical = canonical_json(mapped)

    assert '"action":"upsert"' in canonical
    assert OrderBookDelta.model_validate_json(canonical) == mapped
    assert canonical_sha256(OrderBookDelta.model_validate_json(canonical)) == original_hash


def test_polymarket_snapshot_mapper_rejects_asset_mismatch_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_order_book_snapshot(
            _fixture_snapshot(),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            expected_asset_id=NO_ASSET_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == (
        "Polymarket order-book snapshot asset id does not match expected contract"
    )
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert exc_info.value.context["exchange"] == ExchangeName.POLYMARKET.value
    assert exc_info.value.context["endpoint_category"] == "stream"
    assert exc_info.value.context["exchange_error_code"] == ("polymarket_order_book_asset_mismatch")
    assert "raw_payload" not in exc_info.value.context


def test_polymarket_price_change_mapper_rejects_missing_token_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_order_book_delta(
            _fixture_price_change(),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            expected_asset_id="303030303030303030303030303030303030303030303030303030303030303030",
            received_at=_received_at(),
        )

    assert str(exc_info.value) == (
        "Polymarket price-change message did not include expected contract token"
    )
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert exc_info.value.context["exchange_error_code"] == "polymarket_price_change_asset_missing"
    assert exc_info.value.context["price_change_count"] == "2"
    assert "raw_payload" not in exc_info.value.context


def test_polymarket_order_book_mapper_wraps_validation_errors_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_order_book_snapshot(
            _fixture_snapshot(),
            market_id="not_canonical",
            contract_id=CONTRACT_ID,
            expected_asset_id=YES_ASSET_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Polymarket order-book snapshot mapping failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert exc_info.value.context["exchange_error_code"] == (
        "polymarket_order_book_snapshot_mapping_failed"
    )
    assert "synthetic redacted" not in str(exc_info.value)


def test_polymarket_order_book_mapper_rejects_invalid_timestamps_safely() -> None:
    message = PolymarketRawOrderBookSnapshot.from_exchange_payload(
        {
            "event_type": "book",
            "market": "0x1111111111111111111111111111111111111111111111111111111111111111",
            "asset_id": YES_ASSET_ID,
            "timestamp": "secret timestamp",
            "bids": [{"price": "0.48", "size": "1"}],
            "asks": [{"price": "0.52", "size": "1"}],
        }
    )

    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_order_book_snapshot(
            message,
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            expected_asset_id=YES_ASSET_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Polymarket order-book snapshot mapping failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert "secret timestamp" not in str(exc_info.value)


def test_polymarket_order_book_mapper_rejects_naive_received_at_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_polymarket_order_book_delta(
            _fixture_price_change(),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            expected_asset_id=YES_ASSET_ID,
            received_at=datetime.fromisoformat("2026-06-29T17:15:58"),
        )

    assert str(exc_info.value) == "Polymarket order-book delta mapping failed"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
