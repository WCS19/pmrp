"""Deterministic canonical JSON serialization and hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.time import format_utc_datetime


def to_canonical_data(value: object) -> object:
    """Convert supported canonical values into stable JSON-compatible data."""

    if isinstance(value, CanonicalModel):
        return to_canonical_data(value.model_dump(mode="python", by_alias=True))
    if isinstance(value, Decimal):
        if not value.is_finite():
            msg = "canonical Decimal values must be finite"
            raise ValueError(msg)
        return str(value)
    if isinstance(value, datetime):
        return format_utc_datetime(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        canonical_mapping: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                msg = "canonical mapping keys must be strings"
                raise TypeError(msg)
            canonical_mapping[key] = to_canonical_data(item)
        return canonical_mapping
    if isinstance(value, set | frozenset):
        msg = "canonical serialization does not accept unordered sets"
        raise TypeError(msg)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [to_canonical_data(item) for item in value]
    if isinstance(value, bool | int | str) or value is None:
        return value
    if isinstance(value, float):
        msg = "canonical serialization does not accept floats"
        raise TypeError(msg)
    msg = f"unsupported canonical serialization type: {type(value).__name__}"
    raise TypeError(msg)


def canonical_json(value: object) -> str:
    """Serialize a supported value into deterministic canonical JSON."""

    return json.dumps(
        to_canonical_data(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a supported value into deterministic UTF-8 JSON bytes."""

    return canonical_json(value).encode("utf-8")


def canonical_sha256(value: object) -> str:
    """Hash canonical JSON bytes using SHA-256 with an algorithm prefix."""

    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"
