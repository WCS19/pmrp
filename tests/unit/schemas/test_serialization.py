from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import Side
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.time import UTCDateTime

pytestmark = pytest.mark.unit


class SerializationModel(CanonicalModel):
    event_id: EventId
    occurred_at: UTCDateTime
    side: Side
    amount: Money


def test_canonical_json_serializes_decimal_datetime_enum_and_identifier() -> None:
    model = SerializationModel(
        event_id=EventId("evt_01j00000000000000000000000"),
        occurred_at=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
        side=Side.BUY,
        amount=Money(amount=Decimal("1.2300"), currency="USD"),
    )

    assert canonical_json(model) == (
        '{"amount":{"amount":"1.2300","currency":"USD"},'
        '"event_id":"evt_01j00000000000000000000000",'
        '"occurred_at":"2026-07-28T12:00:00Z",'
        '"side":"buy"}'
    )


def test_canonical_json_round_trip_through_model_validation() -> None:
    model = SerializationModel(
        event_id=EventId("evt_01j00000000000000000000000"),
        occurred_at=datetime(2026, 7, 28, 12, 0, tzinfo=UTC),
        side=Side.SELL,
        amount=Money(amount=Decimal("-1.2300"), currency="USD"),
    )

    assert SerializationModel.model_validate_json(canonical_json(model)) == model


def test_canonical_hash_is_deterministic_for_sorted_keys() -> None:
    first = {"b": Decimal("2.0"), "a": Decimal("1.0")}
    second = {"a": Decimal("1.0"), "b": Decimal("2.0")}

    assert canonical_json(first) == canonical_json(second)
    assert canonical_sha256(first) == canonical_sha256(second)


def test_canonical_hash_has_algorithm_prefix() -> None:
    assert canonical_sha256({"value": Decimal("1")}).startswith("sha256:")


def test_canonical_serialization_rejects_float() -> None:
    with pytest.raises(TypeError, match="does not accept floats"):
        canonical_json({"price": 0.42})


def test_canonical_serialization_rejects_unordered_sets() -> None:
    with pytest.raises(TypeError, match="unordered sets"):
        canonical_json({"values": {"a", "b"}})
