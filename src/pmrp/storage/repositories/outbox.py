"""Typed repository for transactional outbox message persistence."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.serialization import to_canonical_data
from pmrp.storage.errors import InvariantViolationError, classify_storage_error
from pmrp.storage.models import OutboxMessageRow

CANONICAL_EVENTS_TOPIC = "canonical-events"


class CanonicalEventContract(Protocol):
    """Canonical event object with an envelope used for outbox routing."""

    envelope: EventEnvelope


class OutboxMessageRepository:
    """Persist canonical events into the transactional outbox."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_event(
        self,
        event: CanonicalEventContract,
        *,
        topic: str = CANONICAL_EVENTS_TOPIC,
        partition_key: str | None = None,
    ) -> None:
        """Insert one outbox message and flush without committing."""

        await self.add_events((event,), topic=topic, partition_key=partition_key)

    async def add_events(
        self,
        events: Iterable[CanonicalEventContract],
        *,
        topic: str = CANONICAL_EVENTS_TOPIC,
        partition_key: str | None = None,
    ) -> None:
        """Insert outbox messages for canonical events and flush once."""

        rows = tuple(
            outbox_message_to_row(event, topic=topic, partition_key=partition_key)
            for event in events
        )
        try:
            for row in rows:
                self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc


def outbox_message_to_row(
    event: CanonicalEventContract,
    *,
    topic: str = CANONICAL_EVENTS_TOPIC,
    partition_key: str | None = None,
) -> OutboxMessageRow:
    """Map one canonical event contract into an outbox row."""

    envelope = _validated_envelope(event)
    payload = to_canonical_data(event)
    if not isinstance(payload, dict):
        raise InvariantViolationError("outbox event payload must serialize as a JSON object")

    return OutboxMessageRow(
        event_id=str(envelope.event_id),
        topic=_validate_topic(topic),
        partition_key=_validate_partition_key(partition_key)
        if partition_key is not None
        else _default_partition_key(envelope),
        payload=payload,
    )


def _validated_envelope(event: CanonicalEventContract) -> EventEnvelope:
    if not isinstance(event, CanonicalModel):
        msg = "outbox event must be a canonical model"
        raise TypeError(msg)
    envelope = getattr(event, "envelope", None)
    if not isinstance(envelope, EventEnvelope):
        msg = "outbox event requires an EventEnvelope"
        raise TypeError(msg)
    return envelope


def _default_partition_key(envelope: EventEnvelope) -> str | None:
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


def _validate_topic(topic: str) -> str:
    if type(topic) is not str:
        msg = "outbox topic must be a string"
        raise TypeError(msg)
    if topic == "" or topic.strip() != topic:
        raise ValueError("outbox topic must be nonempty without surrounding whitespace")
    return topic


def _validate_partition_key(partition_key: str) -> str:
    if type(partition_key) is not str:
        msg = "outbox partition_key must be a string"
        raise TypeError(msg)
    if partition_key == "" or partition_key.strip() != partition_key:
        raise ValueError("outbox partition_key must be nonempty without surrounding whitespace")
    return partition_key
