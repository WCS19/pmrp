"""Tests for portfolio journal entry persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.schemas.portfolio import AccountingJournalEntry, JournalLine
from pmrp.storage import InvariantViolationError, PersistenceTimeoutError
from pmrp.storage.models import JournalEntryRow, JournalLineRow
from pmrp.storage.repositories import (
    JournalEntryRepository,
    journal_entry_from_rows,
    journal_entry_to_rows,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_journal_entry_to_rows_preserves_exact_values_and_line_order() -> None:
    journal = _journal_entry()

    header_row, line_rows = journal_entry_to_rows(journal)

    assert header_row.journal_entry_id == "journal_repo_0001"
    assert header_row.occurred_at == NOW
    assert header_row.source_event_id == "evt_journal_repo_0001"
    assert header_row.reference_type == "fill"
    assert header_row.reference_id == "fill_journal_repo_0001"
    assert header_row.description == "Fill accounting for repository test."
    assert header_row.created_at == NOW + timedelta(seconds=1)
    assert [(line.line_number, line.account_code, line.amount) for line in line_rows] == [
        (1, "cash", Decimal("-2.50")),
        (2, "position_cost", Decimal("2.50")),
    ]
    assert {line.currency for line in line_rows} == {"USD"}


def test_journal_entry_from_rows_round_trips_canonical_journal_with_sorted_lines() -> None:
    journal = _journal_entry()
    header_row, line_rows = journal_entry_to_rows(journal)

    result = journal_entry_from_rows(header_row, tuple(reversed(line_rows)))

    assert result == journal


def test_journal_entry_from_rows_rejects_missing_lines() -> None:
    header_row, _ = journal_entry_to_rows(_journal_entry())

    with pytest.raises(InvariantViolationError, match="no persisted lines") as exc_info:
        journal_entry_from_rows(header_row, ())

    assert exc_info.value.context == {"journal_entry_id": "journal_repo_0001"}


def test_journal_entry_from_rows_rejects_non_contiguous_line_numbers() -> None:
    header_row, line_rows = journal_entry_to_rows(_journal_entry())
    line_rows[1].line_number = 3

    with pytest.raises(InvariantViolationError, match="line numbers"):
        journal_entry_from_rows(header_row, line_rows)


@pytest.mark.asyncio
async def test_repository_add_inserts_header_and_lines_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    await repository.add(_journal_entry())

    assert len(session.added) == 3
    assert isinstance(session.added[0], JournalEntryRow)
    assert [line.line_number for line in session.added[1:]] == [1, 2]
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_add_many_flushes_once_for_multiple_journals() -> None:
    session = _FakeSession()
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    await repository.add_many(
        (
            _journal_entry(journal_entry_id="journal_repo_0001"),
            _journal_entry(
                journal_entry_id="journal_repo_0002",
                source_event_id="evt_journal_repo_0002",
                reference_id="fill_journal_repo_0002",
            ),
        )
    )

    assert len(session.added) == 6
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_add_many_noops_empty_batch() -> None:
    session = _FakeSession()
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    await repository.add_many(())

    assert session.added == []
    assert session.flushed == 0
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_add_classifies_sqlalchemy_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_journal_entry())


@pytest.mark.asyncio
async def test_repository_get_queries_header_then_ordered_lines() -> None:
    journal = _journal_entry()
    header_row, line_rows = journal_entry_to_rows(journal)
    session = _FakeSession(results=(header_row, line_rows))
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    result = await repository.get("journal_repo_0001")

    assert result == journal
    assert len(session.statements) == 2
    assert "journal_entries.journal_entry_id = 'journal_repo_0001'" in _compile(
        session.statements[0]
    )
    line_sql = _compile(session.statements[1])
    assert "journal_lines.journal_entry_id IN ('journal_repo_0001')" in line_sql
    assert "ORDER BY pmrp_portfolio.journal_lines.journal_entry_id" in line_sql
    assert "pmrp_portfolio.journal_lines.line_number" in line_sql


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    result = await repository.get("journal_repo_0001")

    assert result is None
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_repository_get_by_source_event_uses_unique_source_event_query() -> None:
    journal = _journal_entry()
    header_row, line_rows = journal_entry_to_rows(journal)
    session = _FakeSession(results=(header_row, line_rows))
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    result = await repository.get_by_source_event("evt_journal_repo_0001")  # type: ignore[arg-type]

    assert result == journal
    assert "journal_entries.source_event_id = 'evt_journal_repo_0001'" in _compile(
        session.statements[0]
    )


@pytest.mark.asyncio
async def test_repository_list_by_reference_uses_documented_query_path() -> None:
    first = _journal_entry()
    second = _journal_entry(
        journal_entry_id="journal_repo_0002",
        source_event_id="evt_journal_repo_0002",
    )
    first_header, first_lines = journal_entry_to_rows(first)
    second_header, second_lines = journal_entry_to_rows(second)
    session = _FakeSession(results=((first_header, second_header), (*first_lines, *second_lines)))
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    result = await repository.list_by_reference(
        reference_type="fill",
        reference_id="fill_journal_repo_0001",
    )

    assert result == (first, second)
    header_sql = _compile(session.statements[0])
    assert "journal_entries.reference_type = 'fill'" in header_sql
    assert "journal_entries.reference_id = 'fill_journal_repo_0001'" in header_sql
    assert "ORDER BY pmrp_portfolio.journal_entries.occurred_at" in header_sql


@pytest.mark.asyncio
async def test_repository_list_by_reference_rejects_invalid_reference_filter() -> None:
    session = _FakeSession()
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="reference_type"):
        await repository.list_by_reference(reference_type="", reference_id="fill_journal_repo_0001")

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = JournalEntryRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.get("journal_repo_0001")


def _journal_entry(**overrides: object) -> AccountingJournalEntry:
    payload: dict[str, object] = {
        "journal_entry_id": "journal_repo_0001",
        "occurred_at": NOW,
        "source_event_id": "evt_journal_repo_0001",
        "reference_type": "fill",
        "reference_id": "fill_journal_repo_0001",
        "lines": (
            JournalLine(
                account_code="cash",
                amount=Decimal("-2.50"),
                currency="USD",
                description="Cash movement.",
            ),
            JournalLine(
                account_code="position_cost",
                amount=Decimal("2.50"),
                currency="USD",
                description="Position cost.",
            ),
        ),
        "description": "Fill accounting for repository test.",
        "created_at": NOW + timedelta(seconds=1),
    }
    payload.update(overrides)
    return AccountingJournalEntry(**payload)  # type: ignore[arg-type]


def _compile(statement: ClauseElement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


class _FakeSession:
    def __init__(
        self,
        *,
        results: tuple[object, ...] = (),
        execute_error: Exception | None = None,
        flush_error: Exception | None = None,
    ) -> None:
        self.added: list[JournalEntryRow | JournalLineRow] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: JournalEntryRow | JournalLineRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        if self._flush_error is not None:
            raise self._flush_error
        self.flushed += 1

    async def execute(self, statement: ClauseElement) -> _FakeResult:
        if self._execute_error is not None:
            raise self._execute_error
        self.statements.append(statement)
        value = self._results.pop(0) if self._results else None
        return _FakeResult(value)


class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> JournalEntryRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._value)


class _FakeScalars:
    def __init__(self, value: object) -> None:
        self._value = value

    def all(self) -> list[Any]:
        if self._value is None:
            return []
        if isinstance(self._value, tuple):
            return list(self._value)
        return [self._value]
