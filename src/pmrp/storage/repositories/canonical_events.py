"""Typed repository for immutable canonical event persistence."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.serialization import canonical_sha256, to_canonical_data
from pmrp.storage.errors import InvariantViolationError, classify_storage_error
from pmrp.storage.models import CanonicalEventRow, EventIdRow
from pmrp.storage.repositories.event_contracts import (
    CanonicalEventContract,
    canonical_event_payload,
    validated_event_envelope,
)


class CanonicalEventRepository:
    """Persist canonical events for replay, audit, and durable publication."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_event(self, event: CanonicalEventContract) -> None:
        """Insert one canonical event and flush without committing."""

        await self.add_events((event,))

    async def add_events(self, events: Iterable[CanonicalEventContract]) -> None:
        """Insert canonical events and global event IDs, then flush once."""

        rows = tuple(canonical_event_to_rows(event) for event in events)
        try:
            for event_id_row, canonical_event_row in rows:
                self._session.add(event_id_row)
                self._session.add(canonical_event_row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc


def canonical_event_to_rows(
    event: CanonicalEventContract,
) -> tuple[EventIdRow, CanonicalEventRow]:
    """Map one canonical event contract into durable event storage rows."""

    envelope = validated_event_envelope(event)
    return (
        EventIdRow(
            event_id=str(envelope.event_id),
            occurred_at=envelope.occurred_at,
        ),
        _canonical_event_row(event, envelope=envelope),
    )


def _canonical_event_row(
    event: CanonicalEventContract,
    *,
    envelope: EventEnvelope,
) -> CanonicalEventRow:
    payload = canonical_event_payload(event)
    return CanonicalEventRow(
        occurred_at=envelope.occurred_at,
        event_id=str(envelope.event_id),
        event_type=envelope.event_type,
        schema_version=int(envelope.schema_version),
        received_at=envelope.received_at,
        published_at=envelope.published_at,
        producer=envelope.producer,
        exchange=envelope.exchange,
        market_id=_optional_identifier(envelope.market_id),
        account_id=_optional_identifier(envelope.account_id),
        strategy_id=_optional_identifier(envelope.strategy_id),
        order_id=_optional_identifier(envelope.order_id),
        correlation_id=str(envelope.correlation_id),
        causation_id=_optional_identifier(envelope.causation_id),
        trace_id=envelope.trace_id,
        replay_session_id=_optional_identifier(envelope.replay_session_id),
        simulation_session_id=_optional_identifier(envelope.simulation_session_id),
        quality_flags=[flag.value for flag in envelope.quality_flags],
        attributes=_canonical_attributes(envelope),
        payload=payload,
        payload_hash=canonical_sha256(event),
    )


def _canonical_attributes(envelope: EventEnvelope) -> dict[str, object]:
    attributes = to_canonical_data(envelope.attributes)
    if not isinstance(attributes, dict):
        raise InvariantViolationError("canonical event attributes must serialize as a JSON object")
    return attributes


def _optional_identifier(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)
