"""Typed repository for transactional outbox message persistence."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.storage.errors import classify_storage_error
from pmrp.storage.models import OutboxMessageRow
from pmrp.storage.repositories.event_contracts import (
    CanonicalEventContract,
    canonical_event_payload,
    default_event_partition_key,
    validated_event_envelope,
)

CANONICAL_EVENTS_TOPIC = "canonical-events"


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

    envelope = validated_event_envelope(event)
    payload = canonical_event_payload(event)

    return OutboxMessageRow(
        event_id=str(envelope.event_id),
        topic=_validate_topic(topic),
        partition_key=_validate_partition_key(partition_key)
        if partition_key is not None
        else default_event_partition_key(envelope),
        payload=payload,
    )


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
