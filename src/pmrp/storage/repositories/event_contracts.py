"""Shared helpers for storage repositories that accept canonical events."""

from __future__ import annotations

from typing import Protocol

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.serialization import to_canonical_data
from pmrp.storage.errors import InvariantViolationError


class CanonicalEventContract(Protocol):
    """Canonical event object with an envelope used for durable storage."""

    envelope: EventEnvelope


def validated_event_envelope(event: CanonicalEventContract) -> EventEnvelope:
    """Return the event envelope after validating the canonical event contract."""

    if not isinstance(event, CanonicalModel):
        msg = "canonical event must be a canonical model"
        raise TypeError(msg)
    envelope = getattr(event, "envelope", None)
    if not isinstance(envelope, EventEnvelope):
        msg = "canonical event requires an EventEnvelope"
        raise TypeError(msg)
    return envelope


def canonical_event_payload(event: CanonicalEventContract) -> dict[str, object]:
    """Serialize a canonical event into JSON-compatible payload data."""

    payload = to_canonical_data(event)
    if not isinstance(payload, dict):
        raise InvariantViolationError("canonical event payload must serialize as a JSON object")
    return payload


def default_event_partition_key(envelope: EventEnvelope) -> str | None:
    """Derive the default event partition key from canonical lineage."""

    if envelope.market_id is not None:
        if envelope.exchange is not None:
            return f"{envelope.exchange}:{envelope.market_id}"
        return str(envelope.market_id)
    if envelope.strategy_id is not None:
        return str(envelope.strategy_id)
    if envelope.order_id is not None:
        return str(envelope.order_id)
    if envelope.account_id is not None:
        return str(envelope.account_id)
    return None
