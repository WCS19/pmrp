"""Tests for Kalshi raw order-book payload models."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters.kalshi import (
    KalshiOrderBookSequenceStatus,
    KalshiRawOrderBookLevel,
    KalshiRawOrderBookMessage,
    check_kalshi_order_book_sequence,
    parse_kalshi_order_book_message_json,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kalshi" / "order_book"


def _snapshot_payload(
    *,
    msg_overrides: Mapping[str, object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    msg: dict[str, object] = {
        "market_ticker": "KX-PMRP-EXAMPLE-YES",
        "yes": [[47, 125], [46, 240]],
        "no": [[52, 130], [53, 90]],
    }
    if msg_overrides is not None:
        msg.update(msg_overrides)
    payload: dict[str, object] = {
        "type": "orderbook_snapshot",
        "sid": 42,
        "seq": 1001,
        "msg": msg,
    }
    payload.update(overrides)
    return payload


def _delta_payload(
    *,
    msg_overrides: Mapping[str, object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    msg: dict[str, object] = {
        "market_ticker": "KX-PMRP-EXAMPLE-YES",
        "side": "yes",
        "price": 48,
        "quantity": 75,
        "action": "insert",
    }
    if msg_overrides is not None:
        msg.update(msg_overrides)
    payload: dict[str, object] = {
        "type": "orderbook_delta",
        "sid": 42,
        "seq": 1002,
        "msg": msg,
    }
    payload.update(overrides)
    return payload


def test_kalshi_order_book_snapshot_fixture_parses_and_preserves_raw_payload() -> None:
    message = parse_kalshi_order_book_message_json((FIXTURE_ROOT / "snapshot.json").read_text())

    assert message.market_ticker == "KX-PMRP-EXAMPLE-YES"
    assert message.message_type == "snapshot"
    assert message.subscription_id == 42
    assert message.sequence == 1001
    assert [(level.price, level.quantity) for level in message.yes] == [(47, 125), (46, 240)]
    assert [(level.price, level.quantity) for level in message.no] == [(52, 130), (53, 90)]
    assert message.raw_payload["type"] == "orderbook_snapshot"


@pytest.mark.parametrize(
    ("fixture_name", "expected_sequence", "expected_side", "expected_action", "expected_quantity"),
    [
        ("delta_insert.json", 1002, "yes", "insert", 75),
        ("delta_update.json", 1003, "yes", "update", 180),
        ("delta_delete.json", 1004, "no", "delete", 0),
    ],
)
def test_kalshi_order_book_delta_fixtures_parse(
    fixture_name: str,
    expected_sequence: int,
    expected_side: str,
    expected_action: str,
    expected_quantity: int,
) -> None:
    message = parse_kalshi_order_book_message_json((FIXTURE_ROOT / fixture_name).read_text())

    assert message.message_type == "delta"
    assert message.sequence == expected_sequence
    assert message.side == expected_side
    assert message.action == expected_action
    assert message.quantity == expected_quantity
    assert message.yes == ()
    assert message.no == ()


def test_kalshi_order_book_raw_message_rejects_unknown_model_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        KalshiRawOrderBookMessage.model_validate(
            {
                "market_ticker": "KX-PMRP-EXAMPLE-YES",
                "message_type": "snapshot",
                "sequence": 1001,
                "yes": [{"price": 47, "quantity": 125}],
                "raw_payload": _snapshot_payload(),
                "unexpected": "not allowed outside raw_payload",
            }
        )


def test_kalshi_order_book_raw_payload_is_immutable_after_validation() -> None:
    message = KalshiRawOrderBookMessage.from_exchange_payload(_snapshot_payload())
    original_hash = canonical_sha256(message)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        message.sequence = 1002
    with pytest.raises(TypeError):
        message.raw_payload["seq"] = 1002

    assert canonical_sha256(message) == original_hash


def test_kalshi_order_book_rejects_float_prices() -> None:
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        KalshiRawOrderBookMessage.model_validate(
            {
                "market_ticker": "KX-PMRP-EXAMPLE-YES",
                "message_type": "delta",
                "sequence": 1002,
                "side": "yes",
                "price": 48.5,
                "quantity": 75,
                "action": "insert",
                "raw_payload": _delta_payload(),
            }
        )


def test_kalshi_order_book_rejects_negative_quantities() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        KalshiRawOrderBookLevel.model_validate({"price": 47, "quantity": -1})


def test_kalshi_order_book_rejects_duplicate_snapshot_prices() -> None:
    with pytest.raises(ValidationError, match="duplicate prices"):
        KalshiRawOrderBookMessage.from_exchange_payload(
            _snapshot_payload(msg_overrides={"yes": [[47, 125], [47, 240]]})
        )


def test_kalshi_order_book_rejects_empty_snapshot() -> None:
    with pytest.raises(ValidationError, match="at least one side"):
        KalshiRawOrderBookMessage.from_exchange_payload(
            _snapshot_payload(msg_overrides={"yes": [], "no": []})
        )


def test_kalshi_order_book_delta_requires_price() -> None:
    with pytest.raises(ValueError, match="price is required"):
        KalshiRawOrderBookMessage.from_exchange_payload(
            _delta_payload(msg_overrides={"price": None})
        )


def test_kalshi_order_book_insert_delta_requires_quantity() -> None:
    with pytest.raises(ValidationError, match="insert and update"):
        KalshiRawOrderBookMessage.from_exchange_payload(
            _delta_payload(msg_overrides={"quantity": None})
        )


def test_kalshi_order_book_delete_delta_rejects_positive_quantity() -> None:
    with pytest.raises(ValidationError, match="delete deltas"):
        KalshiRawOrderBookMessage.from_exchange_payload(
            _delta_payload(msg_overrides={"action": "delete", "quantity": 10})
        )


def test_kalshi_order_book_json_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        parse_kalshi_order_book_message_json("{")


def test_kalshi_order_book_json_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_kalshi_order_book_message_json("[]")


def test_kalshi_order_book_json_round_trip_and_stable_hash() -> None:
    message = KalshiRawOrderBookMessage.from_exchange_payload(_snapshot_payload())
    canonical = canonical_json(message)

    assert '"market_ticker":"KX-PMRP-EXAMPLE-YES"' in canonical
    assert KalshiRawOrderBookMessage.model_validate_json(canonical) == message
    assert canonical_sha256(message) == canonical_sha256(
        KalshiRawOrderBookMessage.model_validate_json(canonical)
    )


def test_kalshi_order_book_sequence_check_identifies_increment() -> None:
    message = KalshiRawOrderBookMessage.from_exchange_payload(_delta_payload(seq=1002))

    check = check_kalshi_order_book_sequence(previous_sequence=1001, message=message)

    assert check.expected_sequence == 1002
    assert check.status is KalshiOrderBookSequenceStatus.OK
    assert check.invalidates_book is False


def test_kalshi_order_book_sequence_check_identifies_duplicate_fixture() -> None:
    message = parse_kalshi_order_book_message_json(
        (FIXTURE_ROOT / "duplicate_sequence.json").read_text()
    )

    check = check_kalshi_order_book_sequence(previous_sequence=1004, message=message)

    assert check.status is KalshiOrderBookSequenceStatus.DUPLICATE
    assert check.invalidates_book is False


def test_kalshi_order_book_sequence_check_identifies_stale_message() -> None:
    message = KalshiRawOrderBookMessage.from_exchange_payload(_delta_payload(seq=1002))

    check = check_kalshi_order_book_sequence(previous_sequence=1004, message=message)

    assert check.status is KalshiOrderBookSequenceStatus.STALE
    assert check.invalidates_book is False


def test_kalshi_order_book_sequence_check_identifies_gap_fixture() -> None:
    message = parse_kalshi_order_book_message_json((FIXTURE_ROOT / "sequence_gap.json").read_text())

    check = check_kalshi_order_book_sequence(previous_sequence=1004, message=message)

    assert check.expected_sequence == 1005
    assert check.received_sequence == 1007
    assert check.status is KalshiOrderBookSequenceStatus.GAP
    assert check.invalidates_book is True


def test_kalshi_order_book_sequence_check_identifies_missing_sequence() -> None:
    tracked = check_kalshi_order_book_sequence(
        previous_sequence=1004,
        message=KalshiRawOrderBookMessage.from_exchange_payload(_delta_payload(seq=None)),
    )
    initial = check_kalshi_order_book_sequence(
        previous_sequence=None,
        message=KalshiRawOrderBookMessage.from_exchange_payload(_delta_payload(seq=None)),
    )

    assert tracked.status is KalshiOrderBookSequenceStatus.MISSING
    assert tracked.invalidates_book is True
    assert initial.status is KalshiOrderBookSequenceStatus.MISSING
    assert initial.invalidates_book is False


def test_kalshi_order_book_sequence_check_rejects_invalid_previous_sequence() -> None:
    message = KalshiRawOrderBookMessage.from_exchange_payload(_delta_payload())

    with pytest.raises(TypeError, match="must be an integer"):
        check_kalshi_order_book_sequence(previous_sequence=True, message=message)
    with pytest.raises(ValueError, match="must be nonnegative"):
        check_kalshi_order_book_sequence(previous_sequence=-1, message=message)


def test_kalshi_order_book_json_schema_generation() -> None:
    assert KalshiRawOrderBookLevel.model_json_schema()["title"] == "KalshiRawOrderBookLevel"
    assert KalshiRawOrderBookMessage.model_json_schema()["title"] == "KalshiRawOrderBookMessage"
