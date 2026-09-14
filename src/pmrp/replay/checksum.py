"""Replay dataset checksum helpers."""

from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256

from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.serialization import canonical_json_bytes


def calculate_replay_dataset_checksum(events: Iterable[EventEnvelope]) -> str:
    """Return the deterministic checksum for a loaded replay event sequence."""

    digest = sha256()
    for event in events:
        digest.update(canonical_json_bytes(event))
        digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"
