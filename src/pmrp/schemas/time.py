"""UTC datetime validation and serialization helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer


def parse_utc_datetime(value: object) -> datetime:
    """Validate timezone awareness and normalize datetimes to UTC."""

    if isinstance(value, str):
        parsed_value = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            value = datetime.fromisoformat(parsed_value)
        except ValueError as exc:
            msg = "datetime string must be ISO 8601"
            raise ValueError(msg) from exc

    if not isinstance(value, datetime):
        msg = "datetime value must be a datetime or ISO 8601 string"
        raise TypeError(msg)

    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        msg = "datetime value must be timezone-aware"
        raise ValueError(msg)

    return value.astimezone(UTC)


def format_utc_datetime(value: datetime) -> str:
    """Serialize a datetime in normalized UTC ISO 8601 form."""

    utc_value = parse_utc_datetime(value)
    return utc_value.isoformat().replace("+00:00", "Z")


type UTCDateTime = Annotated[
    datetime,
    BeforeValidator(parse_utc_datetime),
    PlainSerializer(format_utc_datetime, return_type=str, when_used="json"),
]
