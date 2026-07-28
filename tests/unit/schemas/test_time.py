import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.time import UTCDateTime, format_utc_datetime, parse_utc_datetime

pytestmark = pytest.mark.unit


class TimestampModel(CanonicalModel):
    occurred_at: UTCDateTime


def _naive_datetime() -> datetime:
    return datetime.fromisoformat("2026-07-28T12:00:00")


def test_utc_datetime_accepts_timezone_aware_utc_datetime() -> None:
    value = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)

    model = TimestampModel(occurred_at=value)

    assert model.occurred_at == value


def test_utc_datetime_normalizes_non_utc_offset() -> None:
    value = datetime(2026, 7, 28, 6, 0, tzinfo=timezone(timedelta(hours=-6)))

    model = TimestampModel(occurred_at=value)

    assert model.occurred_at == datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def test_utc_datetime_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        TimestampModel(occurred_at=_naive_datetime())


def test_utc_datetime_accepts_json_iso_z_timestamp() -> None:
    model = TimestampModel.model_validate_json(
        """
        {
          "occurred_at": "2026-07-28T12:00:00.123456Z"
        }
        """
    )

    assert model.occurred_at == datetime(2026, 7, 28, 12, 0, 0, 123456, tzinfo=UTC)


def test_utc_datetime_serializes_with_z_suffix() -> None:
    model = TimestampModel(
        occurred_at=datetime(2026, 7, 28, 6, 0, tzinfo=timezone(timedelta(hours=-6)))
    )

    assert json.loads(model.model_dump_json()) == {"occurred_at": "2026-07-28T12:00:00Z"}


def test_parse_utc_datetime_rejects_invalid_string() -> None:
    with pytest.raises(ValueError, match="ISO 8601"):
        parse_utc_datetime("not-a-time")


def test_format_utc_datetime_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        format_utc_datetime(_naive_datetime())
