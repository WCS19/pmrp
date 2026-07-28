from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pmrp.schemas.enums import DataQualityFlag
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping

pytestmark = pytest.mark.unit


def test_freeze_canonical_mapping_deeply_freezes_nested_containers() -> None:
    frozen = freeze_canonical_mapping(
        {
            "source": "unit_test",
            "flags": [DataQualityFlag.REPLAYED],
            "nested": {"amount": Decimal("1.25")},
        },
        field_name="test metadata",
    )
    nested = frozen["nested"]

    with pytest.raises(TypeError, match="does not support item assignment"):
        frozen["source"] = "changed"
    assert isinstance(nested, Mapping)
    with pytest.raises(TypeError, match="does not support item assignment"):
        nested["amount"] = Decimal("2.50")
    assert thaw_canonical_mapping(frozen) == {
        "source": "unit_test",
        "flags": [DataQualityFlag.REPLAYED],
        "nested": {"amount": Decimal("1.25")},
    }


def test_freeze_canonical_mapping_normalizes_datetime_values_to_utc() -> None:
    frozen = freeze_canonical_mapping(
        {"checked_at": datetime.fromisoformat("2026-07-28T13:00:00-06:00")},
        field_name="test metadata",
    )

    assert frozen["checked_at"] == datetime(2026, 7, 28, 19, 0, tzinfo=UTC)


def test_freeze_canonical_mapping_rejects_naive_datetime_values() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        freeze_canonical_mapping(
            {"checked_at": datetime.fromisoformat("2026-07-28T19:00:00")},
            field_name="test metadata",
        )


def test_freeze_canonical_mapping_rejects_float_values() -> None:
    with pytest.raises(TypeError, match="must not contain floats"):
        freeze_canonical_mapping({"probability": 0.5}, field_name="test metadata")


def test_freeze_canonical_mapping_rejects_bytes_values() -> None:
    with pytest.raises(TypeError, match="must not contain bytes"):
        freeze_canonical_mapping({"payload": b"raw"}, field_name="test metadata")


def test_freeze_canonical_mapping_rejects_mutable_bytearray_values() -> None:
    with pytest.raises(TypeError, match="must not contain bytes"):
        freeze_canonical_mapping({"payload": bytearray(b"raw")}, field_name="test metadata")


def test_freeze_canonical_mapping_rejects_arbitrary_objects() -> None:
    with pytest.raises(TypeError, match="unsupported test metadata value type"):
        freeze_canonical_mapping({"object": object()}, field_name="test metadata")


def test_freeze_canonical_mapping_rejects_nonfinite_decimal_values() -> None:
    with pytest.raises(ValueError, match="must be finite"):
        freeze_canonical_mapping({"amount": Decimal("NaN")}, field_name="test metadata")
