"""Tests for Kalshi order-book canonical mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters import AdapterProtocolError
from pmrp.adapters.kalshi import (
    KALSHI_ORDER_BOOK_MAPPER_VERSION,
    KalshiRawOrderBookMessage,
    map_kalshi_order_book_delta,
    map_kalshi_order_book_message,
    map_kalshi_order_book_snapshot,
    parse_kalshi_order_book_message_json,
)
from pmrp.schemas.enums import ExchangeName, Side
from pmrp.schemas.market_data import OrderBookDelta, OrderBookDeltaAction, OrderBookSnapshot
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kalshi" / "order_book"
MARKET_ID = "mkt_01j00000000000000000000000"
CONTRACT_ID = "ctr_01j00000000000000000000000"


def _received_at() -> datetime:
    return datetime(2026, 7, 28, 19, 1, 2, 123456, tzinfo=UTC)


def _exchange_occurred_at() -> datetime:
    return datetime(2026, 7, 28, 19, 1, 1, tzinfo=UTC)


def _fixture(name: str) -> KalshiRawOrderBookMessage:
    return parse_kalshi_order_book_message_json((FIXTURE_ROOT / name).read_text())


def test_kalshi_order_book_mapper_version_is_stable() -> None:
    assert KALSHI_ORDER_BOOK_MAPPER_VERSION == "kalshi_order_book_mapper_v1"


def test_kalshi_order_book_snapshot_maps_yes_bids_and_no_asks_exactly() -> None:
    snapshot = map_kalshi_order_book_snapshot(
        _fixture("snapshot.json"),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        received_at=_received_at(),
        exchange_occurred_at=_exchange_occurred_at(),
    )

    assert snapshot.market_id == MARKET_ID
    assert snapshot.contract_id == CONTRACT_ID
    assert snapshot.exchange == ExchangeName.KALSHI.value
    assert snapshot.sequence == 1001
    assert snapshot.received_at == _received_at()
    assert snapshot.exchange_occurred_at == _exchange_occurred_at()
    assert [(level.price, level.quantity) for level in snapshot.bids] == [
        (Decimal("0.47"), Decimal("125")),
        (Decimal("0.46"), Decimal("240")),
    ]
    assert [(level.price, level.quantity) for level in snapshot.asks] == [
        (Decimal("0.47"), Decimal("90")),
        (Decimal("0.48"), Decimal("130")),
    ]
    assert snapshot.snapshot_reason == "initial"
    assert snapshot.is_valid is True


def test_kalshi_order_book_snapshot_sorts_canonical_levels() -> None:
    message = KalshiRawOrderBookMessage.from_exchange_payload(
        {
            "type": "orderbook_snapshot",
            "seq": 10,
            "msg": {
                "market_ticker": "KX-PMRP-EXAMPLE-YES",
                "yes": [[45, 1], [49, 2], [46, 3]],
                "no": [[51, 4], [54, 5], [52, 6]],
            },
        }
    )

    snapshot = map_kalshi_order_book_snapshot(
        message,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        received_at=_received_at(),
        snapshot_reason="recovery",
    )

    assert [level.price for level in snapshot.bids] == [
        Decimal("0.49"),
        Decimal("0.46"),
        Decimal("0.45"),
    ]
    assert [level.price for level in snapshot.asks] == [
        Decimal("0.46"),
        Decimal("0.48"),
        Decimal("0.49"),
    ]
    assert snapshot.snapshot_reason == "recovery"


def test_kalshi_order_book_yes_delta_maps_to_buy_upsert() -> None:
    delta = map_kalshi_order_book_delta(
        _fixture("delta_insert.json"),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        received_at=_received_at(),
        previous_sequence=1001,
    )

    assert delta.sequence == 1002
    assert delta.previous_sequence == 1001
    assert len(delta.changes) == 1
    change = delta.changes[0]
    assert change.side is Side.BUY
    assert change.price == Decimal("0.48")
    assert change.quantity == Decimal("75")
    assert change.action is OrderBookDeltaAction.UPSERT


def test_kalshi_order_book_update_delta_maps_to_upsert() -> None:
    delta = map_kalshi_order_book_delta(
        _fixture("delta_update.json"),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        received_at=_received_at(),
        previous_sequence=1002,
    )

    assert delta.changes[0].side is Side.BUY
    assert delta.changes[0].price == Decimal("0.47")
    assert delta.changes[0].quantity == Decimal("180")
    assert delta.changes[0].action is OrderBookDeltaAction.UPSERT


def test_kalshi_order_book_no_delete_delta_maps_to_sell_delete_at_complement_price() -> None:
    delta = map_kalshi_order_book_delta(
        _fixture("delta_delete.json"),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        received_at=_received_at(),
        previous_sequence=1003,
    )

    change = delta.changes[0]
    assert change.side is Side.SELL
    assert change.price == Decimal("0.47")
    assert change.quantity == Decimal("0")
    assert change.action is OrderBookDeltaAction.DELETE


@pytest.mark.parametrize(
    ("fixture_name", "expected_type"),
    [
        ("snapshot.json", OrderBookSnapshot),
        ("delta_insert.json", OrderBookDelta),
    ],
)
def test_kalshi_order_book_message_mapper_dispatches_by_raw_message_type(
    fixture_name: str,
    expected_type: type[OrderBookSnapshot] | type[OrderBookDelta],
) -> None:
    mapped = map_kalshi_order_book_message(
        _fixture(fixture_name),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        received_at=_received_at(),
        previous_sequence=1001,
    )

    assert isinstance(mapped, expected_type)


def test_kalshi_order_book_mapping_is_strict_immutable_and_stably_serialized() -> None:
    mapped = map_kalshi_order_book_snapshot(
        _fixture("snapshot.json"),
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        received_at=_received_at(),
    )
    original_hash = canonical_sha256(mapped)
    canonical = canonical_json(mapped)

    assert '"price":"0.47"' in canonical
    assert OrderBookSnapshot.model_validate_json(canonical) == mapped
    assert canonical_sha256(OrderBookSnapshot.model_validate_json(canonical)) == original_hash
    with pytest.raises(ValidationError, match="Instance is frozen"):
        mapped.sequence = 1002


def test_kalshi_order_book_snapshot_mapper_rejects_delta_message_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_kalshi_order_book_snapshot(
            _fixture("delta_insert.json"),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Kalshi order-book message is not a snapshot"
    assert exc_info.value.context["exchange"] == ExchangeName.KALSHI.value
    assert exc_info.value.context["endpoint_category"] == "stream"
    assert exc_info.value.context["exchange_error_code"] == "kalshi_order_book_wrong_message_type"
    assert "raw_payload" not in exc_info.value.context


def test_kalshi_order_book_delta_mapper_rejects_snapshot_message_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_kalshi_order_book_delta(
            _fixture("snapshot.json"),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            received_at=_received_at(),
            previous_sequence=None,
        )

    assert str(exc_info.value) == "Kalshi order-book message is not a delta"
    assert exc_info.value.context["exchange_error_code"] == "kalshi_order_book_wrong_message_type"


def test_kalshi_order_book_mapper_wraps_canonical_validation_errors_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_kalshi_order_book_snapshot(
            _fixture("snapshot.json"),
            market_id="not_canonical",
            contract_id=CONTRACT_ID,
            received_at=_received_at(),
        )

    assert str(exc_info.value) == "Kalshi order-book snapshot mapping failed"
    assert exc_info.value.context["exchange_error_code"] == (
        "kalshi_order_book_snapshot_mapping_failed"
    )
    assert "synthetic redacted" not in str(exc_info.value)


def test_kalshi_order_book_mapper_rejects_naive_received_at_safely() -> None:
    with pytest.raises(AdapterProtocolError) as exc_info:
        map_kalshi_order_book_delta(
            _fixture("delta_insert.json"),
            market_id=MARKET_ID,
            contract_id=CONTRACT_ID,
            received_at=datetime.fromisoformat("2026-07-28T19:01:02"),
            previous_sequence=1001,
        )

    assert str(exc_info.value) == "Kalshi order-book delta mapping failed"
    assert exc_info.value.context["sequence"] == "1002"
