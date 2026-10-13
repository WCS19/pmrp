"""Tests for reconciliation result persistence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.schemas.identifiers import AccountId
from pmrp.schemas.portfolio import (
    ReconciliationMismatch,
    ReconciliationResult,
    ReconciliationStatus,
)
from pmrp.storage import InvariantViolationError, PersistenceTimeoutError
from pmrp.storage.models import ReconciliationMismatchRow, ReconciliationRunRow
from pmrp.storage.repositories import (
    ReconciliationResultRepository,
    reconciliation_result_from_rows,
    reconciliation_result_to_rows,
)

pytestmark = pytest.mark.unit

STARTED_AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 9, 26, 14, 0, 1, tzinfo=UTC)


def test_reconciliation_result_to_rows_preserves_run_and_mismatches() -> None:
    result = _result()

    run_row, mismatch_rows = reconciliation_result_to_rows(
        result,
        initiated_by="operator",
        reason="startup gate",
    )

    assert run_row.reconciliation_id == "recon_repository_001"
    assert run_row.exchange == "kalshi"
    assert run_row.account_id == "acct_reconciliation_repository"
    assert run_row.started_at == STARTED_AT
    assert run_row.completed_at == COMPLETED_AT
    assert run_row.status == "mismatch"
    assert run_row.open_orders_checked == 2
    assert run_row.positions_checked == 3
    assert run_row.balances_checked == 4
    assert run_row.fills_checked == 5
    assert run_row.trading_gate_released is False
    assert run_row.initiated_by == "operator"
    assert run_row.reason == "startup gate"
    assert len(mismatch_rows) == 1
    assert mismatch_rows[0].mismatch_id == "mismatch_repository_001"
    assert mismatch_rows[0].reconciliation_id == "recon_repository_001"
    assert mismatch_rows[0].category == "position.quantity"
    assert mismatch_rows[0].local_value == "10"
    assert mismatch_rows[0].external_value == "11"
    assert mismatch_rows[0].severity == "mismatch"
    assert mismatch_rows[0].requires_manual_review is True
    assert mismatch_rows[0].resolved_at is None
    assert mismatch_rows[0].resolution_note is None


def test_reconciliation_result_from_rows_round_trips_result() -> None:
    result = _result()
    run_row, mismatch_rows = reconciliation_result_to_rows(result, initiated_by="operator")

    assert reconciliation_result_from_rows(run_row, mismatch_rows) == result


def test_reconciliation_result_from_rows_rejects_incomplete_run() -> None:
    run_row, mismatch_rows = reconciliation_result_to_rows(_result(), initiated_by="operator")
    run_row.completed_at = None

    with pytest.raises(InvariantViolationError, match="not complete") as exc_info:
        reconciliation_result_from_rows(run_row, mismatch_rows)

    assert exc_info.value.context == {"reconciliation_id": "recon_repository_001"}


def test_reconciliation_result_from_rows_rejects_mismatch_from_other_run() -> None:
    run_row, mismatch_rows = reconciliation_result_to_rows(_result(), initiated_by="operator")
    mismatch_rows[0].reconciliation_id = "recon_other"

    with pytest.raises(InvariantViolationError, match="different run") as exc_info:
        reconciliation_result_from_rows(run_row, mismatch_rows)

    assert exc_info.value.context == {"reconciliation_id": "recon_repository_001"}


@pytest.mark.asyncio
async def test_repository_add_inserts_rows_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = ReconciliationResultRepository(session)  # type: ignore[arg-type]

    await repository.add(_result(), initiated_by="operator", reason="scheduled check")

    assert len(session.added) == 2
    assert isinstance(session.added[0], ReconciliationRunRow)
    assert isinstance(session.added[1], ReconciliationMismatchRow)
    assert session.added[0].reason == "scheduled check"
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_get_loads_result_and_mismatches() -> None:
    run_row, mismatch_rows = reconciliation_result_to_rows(_result(), initiated_by="operator")
    session = _FakeSession(results=(run_row, mismatch_rows))
    repository = ReconciliationResultRepository(session)  # type: ignore[arg-type]

    result = await repository.get("recon_repository_001")

    assert result == _result()
    assert len(session.statements) == 2
    assert "reconciliation_runs.reconciliation_id = 'recon_repository_001'" in _compile(
        session.statements[0]
    )
    mismatch_sql = _compile(session.statements[1])
    assert "reconciliation_mismatches.reconciliation_id IN ('recon_repository_001')" in mismatch_sql
    assert "ORDER BY pmrp_ops.reconciliation_mismatches.reconciliation_id" in mismatch_sql


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = ReconciliationResultRepository(session)  # type: ignore[arg-type]

    result = await repository.get("recon_repository_001")

    assert result is None
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_repository_latest_for_account_uses_account_time_query() -> None:
    run_row, mismatch_rows = reconciliation_result_to_rows(_result(), initiated_by="operator")
    session = _FakeSession(results=(run_row, mismatch_rows))
    repository = ReconciliationResultRepository(session)  # type: ignore[arg-type]

    result = await repository.latest_for_account(
        exchange="kalshi",
        account_id=AccountId("acct_reconciliation_repository"),
    )

    assert result == _result()
    sql = _compile(session.statements[0])
    assert "reconciliation_runs.exchange = 'kalshi'" in sql
    assert "reconciliation_runs.account_id = 'acct_reconciliation_repository'" in sql
    assert "reconciliation_runs.completed_at IS NOT NULL" in sql
    assert "ORDER BY pmrp_ops.reconciliation_runs.started_at DESC" in sql
    assert "pmrp_ops.reconciliation_runs.reconciliation_id DESC" in sql
    assert "LIMIT 1" in sql


@pytest.mark.asyncio
async def test_repository_list_by_status_uses_bounded_status_query() -> None:
    run_row, mismatch_rows = reconciliation_result_to_rows(_result(), initiated_by="operator")
    session = _FakeSession(results=((run_row,), mismatch_rows))
    repository = ReconciliationResultRepository(session)  # type: ignore[arg-type]

    result = await repository.list_by_status(ReconciliationStatus.MISMATCH, limit=25)

    assert result == (_result(),)
    sql = _compile(session.statements[0])
    assert "reconciliation_runs.status = 'mismatch'" in sql
    assert "reconciliation_runs.completed_at IS NOT NULL" in sql
    assert "ORDER BY pmrp_ops.reconciliation_runs.started_at DESC" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_rejects_invalid_filters_before_querying() -> None:
    session = _FakeSession()
    repository = ReconciliationResultRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="exchange must not be empty"):
        await repository.latest_for_account(
            exchange="",
            account_id="acct_reconciliation_repository",
        )
    with pytest.raises(ValueError, match="not a valid"):
        await repository.list_by_status("not-a-status")
    with pytest.raises(ValueError, match="limit must be positive"):
        await repository.list_by_status(ReconciliationStatus.FAILED, limit=0)

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = ReconciliationResultRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.latest_for_account(
            exchange="kalshi",
            account_id=AccountId("acct_reconciliation_repository"),
        )


@pytest.mark.asyncio
async def test_repository_classifies_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = ReconciliationResultRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_result(), initiated_by="operator")


def _result(**overrides: object) -> ReconciliationResult:
    payload: dict[str, object] = {
        "reconciliation_id": "recon_repository_001",
        "exchange": "kalshi",
        "account_id": "acct_reconciliation_repository",
        "started_at": STARTED_AT,
        "completed_at": COMPLETED_AT,
        "status": ReconciliationStatus.MISMATCH,
        "mismatches": (_mismatch(),),
        "open_orders_checked": 2,
        "positions_checked": 3,
        "balances_checked": 4,
        "fills_checked": 5,
        "trading_gate_released": False,
    }
    payload.update(overrides)
    return ReconciliationResult.model_validate(payload)


def _mismatch(**overrides: object) -> ReconciliationMismatch:
    payload: dict[str, object] = {
        "mismatch_id": "mismatch_repository_001",
        "category": "position.quantity",
        "local_value": "10",
        "external_value": "11",
        "severity": "mismatch",
        "explanation": "Position quantity differs.",
        "requires_manual_review": True,
    }
    payload.update(overrides)
    return ReconciliationMismatch.model_validate(payload)


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
        self.added: list[object] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: object) -> None:
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

    def scalar_one_or_none(self) -> ReconciliationRunRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[ReconciliationRunRow | ReconciliationMismatchRow]:
        if self._value is None:
            return []
        if isinstance(self._value, tuple):
            return list(self._value)  # type: ignore[return-value]
        return [self._value]  # type: ignore[list-item]
