"""Typed repository for append-only portfolio accounting journals."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.identifiers import EventId
from pmrp.schemas.portfolio import AccountingJournalEntry, JournalLine
from pmrp.storage.errors import InvariantViolationError, classify_storage_error
from pmrp.storage.models import JournalEntryRow, JournalLineRow

_JOURNAL_ENTRY_ID_MAX_LENGTH = 128
_REFERENCE_TYPE_MAX_LENGTH = 64
_REFERENCE_ID_MAX_LENGTH = 128


class JournalEntryRepository:
    """Persist and query append-only accounting journal entries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, journal_entry: AccountingJournalEntry) -> None:
        """Insert one accounting journal entry and flush without committing."""

        await self.add_many((journal_entry,))

    async def add_many(self, journal_entries: Iterable[AccountingJournalEntry]) -> None:
        """Insert accounting journal entries and flush once without committing."""

        entries = tuple(journal_entries)
        if not entries:
            return

        try:
            for entry in entries:
                header_row, line_rows = journal_entry_to_rows(entry)
                self._session.add(header_row)
                for line_row in line_rows:
                    self._session.add(line_row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, journal_entry_id: str) -> AccountingJournalEntry | None:
        """Return one journal entry by durable journal entry ID."""

        journal_entry_id = _validate_text(
            journal_entry_id,
            field_name="journal_entry_id",
            max_length=_JOURNAL_ENTRY_ID_MAX_LENGTH,
        )
        statement = select(JournalEntryRow).where(
            JournalEntryRow.journal_entry_id == journal_entry_id
        )
        return await self._one_or_none(statement)

    async def get_by_source_event(
        self,
        source_event_id: EventId | str,
    ) -> AccountingJournalEntry | None:
        """Return the journal entry uniquely associated with a source event."""

        source_event_id = _validate_event_id(source_event_id)
        statement = select(JournalEntryRow).where(
            JournalEntryRow.source_event_id == str(source_event_id)
        )
        return await self._one_or_none(statement)

    async def list_by_reference(
        self,
        *,
        reference_type: str,
        reference_id: str,
    ) -> tuple[AccountingJournalEntry, ...]:
        """Return journal entries for a domain reference in deterministic order."""

        reference_type = _validate_text(
            reference_type,
            field_name="reference_type",
            max_length=_REFERENCE_TYPE_MAX_LENGTH,
        )
        reference_id = _validate_text(
            reference_id,
            field_name="reference_id",
            max_length=_REFERENCE_ID_MAX_LENGTH,
        )
        statement = (
            select(JournalEntryRow)
            .where(
                JournalEntryRow.reference_type == reference_type,
                JournalEntryRow.reference_id == reference_id,
            )
            .order_by(JournalEntryRow.occurred_at, JournalEntryRow.journal_entry_id)
        )
        return await self._all(statement)

    async def _one_or_none(
        self,
        statement: Select[tuple[JournalEntryRow]],
    ) -> AccountingJournalEntry | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        header_row = result.scalar_one_or_none()
        if header_row is None:
            return None
        line_rows = await self._line_rows_for((header_row.journal_entry_id,))
        return journal_entry_from_rows(header_row, line_rows)

    async def _all(
        self,
        statement: Select[tuple[JournalEntryRow]],
    ) -> tuple[AccountingJournalEntry, ...]:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        header_rows = tuple(result.scalars().all())
        if not header_rows:
            return ()

        line_rows = await self._line_rows_for(row.journal_entry_id for row in header_rows)
        return _journal_entries_from_rows(header_rows, line_rows)

    async def _line_rows_for(self, journal_entry_ids: Iterable[str]) -> tuple[JournalLineRow, ...]:
        ids = tuple(journal_entry_ids)
        if not ids:
            return ()

        statement = (
            select(JournalLineRow)
            .where(JournalLineRow.journal_entry_id.in_(ids))
            .order_by(JournalLineRow.journal_entry_id, JournalLineRow.line_number)
        )
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc
        return tuple(result.scalars().all())


def journal_entry_to_rows(
    journal_entry: AccountingJournalEntry,
) -> tuple[JournalEntryRow, tuple[JournalLineRow, ...]]:
    """Map a canonical accounting journal entry into storage rows."""

    header_row = JournalEntryRow(
        journal_entry_id=journal_entry.journal_entry_id,
        occurred_at=journal_entry.occurred_at,
        source_event_id=str(journal_entry.source_event_id),
        reference_type=journal_entry.reference_type,
        reference_id=journal_entry.reference_id,
        description=journal_entry.description,
        created_at=journal_entry.created_at,
    )
    line_rows = tuple(
        JournalLineRow(
            journal_entry_id=journal_entry.journal_entry_id,
            line_number=line_number,
            account_code=line.account_code,
            amount=line.amount,
            currency=line.currency,
            description=line.description,
        )
        for line_number, line in enumerate(journal_entry.lines, start=1)
    )
    return header_row, line_rows


def journal_entry_from_rows(
    header_row: JournalEntryRow,
    line_rows: Iterable[JournalLineRow],
) -> AccountingJournalEntry:
    """Map storage rows into a validated canonical accounting journal entry."""

    ordered_line_rows = tuple(sorted(line_rows, key=lambda row: row.line_number))
    _validate_line_rows_for_header(header_row, ordered_line_rows)
    return AccountingJournalEntry(
        journal_entry_id=header_row.journal_entry_id,
        occurred_at=header_row.occurred_at,
        source_event_id=EventId(header_row.source_event_id),
        reference_type=header_row.reference_type,
        reference_id=header_row.reference_id,
        lines=tuple(
            JournalLine(
                account_code=line.account_code,
                amount=line.amount,
                currency=line.currency,
                description=line.description,
            )
            for line in ordered_line_rows
        ),
        description=header_row.description,
        created_at=header_row.created_at,
    )


def _journal_entries_from_rows(
    header_rows: Iterable[JournalEntryRow],
    line_rows: Iterable[JournalLineRow],
) -> tuple[AccountingJournalEntry, ...]:
    lines_by_entry: defaultdict[str, list[JournalLineRow]] = defaultdict(list)
    for line_row in line_rows:
        lines_by_entry[line_row.journal_entry_id].append(line_row)

    return tuple(
        journal_entry_from_rows(header_row, lines_by_entry[header_row.journal_entry_id])
        for header_row in header_rows
    )


def _validate_line_rows_for_header(
    header_row: JournalEntryRow,
    line_rows: tuple[JournalLineRow, ...],
) -> None:
    if not line_rows:
        raise InvariantViolationError(
            "journal entry has no persisted lines",
            context={"journal_entry_id": header_row.journal_entry_id},
        )

    expected_line_numbers = tuple(range(1, len(line_rows) + 1))
    actual_line_numbers = tuple(line.line_number for line in line_rows)
    if actual_line_numbers != expected_line_numbers:
        raise InvariantViolationError(
            "journal entry line numbers must be contiguous",
            context={"journal_entry_id": header_row.journal_entry_id},
        )

    for line in line_rows:
        if line.journal_entry_id != header_row.journal_entry_id:
            raise InvariantViolationError(
                "journal line belongs to a different journal entry",
                context={"journal_entry_id": header_row.journal_entry_id},
            )


def _validate_text(value: str, *, field_name: str, max_length: int) -> str:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "":
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return value


def _validate_event_id(value: EventId | str) -> EventId:
    if type(value) is EventId:
        return value
    return EventId(value)
