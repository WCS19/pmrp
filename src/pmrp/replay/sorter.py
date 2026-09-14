"""Deterministic replay event ordering."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from pmrp.replay.errors import ReplayOrderingError
from pmrp.schemas.events import EventEnvelope

REPLAY_ORDERING_POLICY_VERSION = "occurred-sequence-received-v1"

_EXCHANGE_SEQUENCE_ATTRIBUTE = "exchange_sequence"
_SOURCE_PARTITION_ATTRIBUTE = "source_partition"
_PRESENT_SEQUENCE_GROUP = 0
_MISSING_SEQUENCE_GROUP = 1
_MISSING_SEQUENCE_VALUE = 0
_MISSING_SOURCE_PARTITION = ""

type ReplayEventOrderingKey = tuple[datetime, tuple[int, int], datetime, str, str]


def replay_event_ordering_key(event: EventEnvelope) -> ReplayEventOrderingKey:
    """Return the documented deterministic replay tie-break key for one event."""

    return (
        event.occurred_at,
        _exchange_sequence_key(event),
        event.received_at,
        _source_partition(event),
        str(event.event_id),
    )


def sort_replay_events(events: Iterable[EventEnvelope]) -> tuple[EventEnvelope, ...]:
    """Return replay events in deterministic canonical replay order."""

    return tuple(sorted(events, key=replay_event_ordering_key))


def _exchange_sequence_key(event: EventEnvelope) -> tuple[int, int]:
    raw_sequence = event.attributes.get(_EXCHANGE_SEQUENCE_ATTRIBUTE)
    if raw_sequence is None:
        return (_MISSING_SEQUENCE_GROUP, _MISSING_SEQUENCE_VALUE)
    if type(raw_sequence) is not int:
        raise ReplayOrderingError(
            "Replay event exchange sequence must be a nonnegative integer when present",
            reason_code="replay_ordering_sequence_invalid",
            context={
                "event_id": str(event.event_id),
                "attribute": _EXCHANGE_SEQUENCE_ATTRIBUTE,
            },
        )
    if raw_sequence < 0:
        raise ReplayOrderingError(
            "Replay event exchange sequence must be a nonnegative integer when present",
            reason_code="replay_ordering_sequence_invalid",
            context={
                "event_id": str(event.event_id),
                "attribute": _EXCHANGE_SEQUENCE_ATTRIBUTE,
            },
        )
    return (_PRESENT_SEQUENCE_GROUP, raw_sequence)


def _source_partition(event: EventEnvelope) -> str:
    raw_partition = event.attributes.get(_SOURCE_PARTITION_ATTRIBUTE)
    if raw_partition is None:
        return _MISSING_SOURCE_PARTITION
    if type(raw_partition) is not str:
        raise ReplayOrderingError(
            "Replay event source partition must be a stable string when present",
            reason_code="replay_ordering_partition_invalid",
            context={
                "event_id": str(event.event_id),
                "attribute": _SOURCE_PARTITION_ATTRIBUTE,
            },
        )
    if raw_partition == "" or raw_partition.strip() != raw_partition:
        raise ReplayOrderingError(
            "Replay event source partition must be a stable string when present",
            reason_code="replay_ordering_partition_invalid",
            context={
                "event_id": str(event.event_id),
                "attribute": _SOURCE_PARTITION_ATTRIBUTE,
            },
        )
    return raw_partition
