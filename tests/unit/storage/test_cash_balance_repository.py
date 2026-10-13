"""Tests for portfolio cash balance projection persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.schemas.identifiers import AccountId
from pmrp.schemas.portfolio import CashBalance
from pmrp.storage import ConcurrencyConflictError, PersistenceTimeoutError
from pmrp.storage.models import CashBalanceRow
from pmrp.storage.repositories import (
    CashBalanceRepository,
    cash_balance_from_row,
    cash_balance_record_from_row,
    cash_balance_to_row,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_cash_balance_to_row_preserves_exact_values_and_version() -> None:
    balance = _balance()

    row = cash_balance_to_row(balance, aggregate_version=3)

    assert row.balance_id == "cash_01k0000000000000000000000"
    assert row.exchange == "kalshi"
    assert row.account_id == "acct_01k00000000000000000000000"
    assert row.currency == "USD"
    assert row.available == Decimal("90.00")
    assert row.reserved == Decimal("10.00")
    assert row.total == Decimal("100.00")
    assert row.captured_at == NOW
    assert row.aggregate_version == 3


def test_cash_balance_to_row_defaults_new_rows_to_version_zero() -> None:
    row = cash_balance_to_row(_balance())

    assert row.aggregate_version == 0


def test_cash_balance_from_row_round_trips_balance() -> None:
    balance = _balance()
    row = cash_balance_to_row(balance, aggregate_version=7)

    assert cash_balance_from_row(row) == balance


def test_cash_balance_record_from_row_preserves_storage_version() -> None:
    row = cash_balance_to_row(_balance(), aggregate_version=7)

    record = cash_balance_record_from_row(row)

    assert record.balance == _balance()
    assert record.aggregate_version == 7


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    await repository.add(_balance())

    assert len(session.added) == 1
    assert isinstance(session.added[0], CashBalanceRow)
    assert session.added[0].available == Decimal("90.00")
    assert session.added[0].aggregate_version == 0
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_get_queries_balance_id() -> None:
    row = cash_balance_to_row(_balance())
    session = _FakeSession(results=(row,))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    result = await repository.get("cash_01k0000000000000000000000")

    assert result == _balance()
    assert "cash_balances.balance_id = 'cash_01k0000000000000000000000'" in _compile(
        session.statements[0]
    )


@pytest.mark.asyncio
async def test_repository_get_record_returns_balance_with_version() -> None:
    row = cash_balance_to_row(_balance(), aggregate_version=5)
    session = _FakeSession(results=(row,))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    result = await repository.get_record("cash_01k0000000000000000000000")

    assert result == cash_balance_record_from_row(row)


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    result = await repository.get("cash_01k0000000000000000000000")

    assert result is None


@pytest.mark.asyncio
async def test_repository_get_by_account_currency_uses_unique_balance_query() -> None:
    row = cash_balance_to_row(_balance())
    session = _FakeSession(results=(row,))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    result = await repository.get_by_account_currency(
        exchange="kalshi",
        account_id=AccountId("acct_01k00000000000000000000000"),
        currency="USD",
    )

    assert result == _balance()
    sql = _compile(session.statements[0])
    assert "cash_balances.exchange = 'kalshi'" in sql
    assert "cash_balances.account_id = 'acct_01k00000000000000000000000'" in sql
    assert "cash_balances.currency = 'USD'" in sql


@pytest.mark.asyncio
async def test_repository_get_by_account_currency_record_returns_version() -> None:
    row = cash_balance_to_row(_balance(), aggregate_version=6)
    session = _FakeSession(results=(row,))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    result = await repository.get_by_account_currency_record(
        exchange="kalshi",
        account_id=AccountId("acct_01k00000000000000000000000"),
        currency="USD",
    )

    assert result == cash_balance_record_from_row(row)


@pytest.mark.asyncio
async def test_repository_list_for_account_uses_documented_query_path() -> None:
    row = cash_balance_to_row(_balance())
    session = _FakeSession(results=((row,),))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    result = await repository.list_for_account(
        exchange="kalshi",
        account_id=AccountId("acct_01k00000000000000000000000"),
        limit=25,
    )

    assert result == (_balance(),)
    sql = _compile(session.statements[0])
    assert "cash_balances.exchange = 'kalshi'" in sql
    assert "cash_balances.account_id = 'acct_01k00000000000000000000000'" in sql
    assert "ORDER BY pmrp_portfolio.cash_balances.currency" in sql
    assert "pmrp_portfolio.cash_balances.balance_id" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_rejects_invalid_filters_before_querying() -> None:
    session = _FakeSession()
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="currency must be"):
        await repository.get_by_account_currency(
            exchange="kalshi",
            account_id="acct_01k00000000000000000000000",
            currency="usd",
        )
    with pytest.raises(ValueError, match="limit must be positive"):
        await repository.list_for_account(
            exchange="kalshi",
            account_id="acct_01k00000000000000000000000",
            limit=0,
        )

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_save_updates_expected_version_and_flushes_without_commit() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=1),))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    await repository.save(_balance(available="85.00", reserved="15.00"), expected_version=3)

    assert session.flushed == 1
    assert session.committed == 0
    sql = _compile(session.statements[0])
    assert "UPDATE pmrp_portfolio.cash_balances" in sql
    assert "available=85.00" in sql
    assert "reserved=15.00" in sql
    assert "total=100.00" in sql
    assert "aggregate_version=4" in sql
    assert "cash_balances.balance_id = 'cash_01k0000000000000000000000'" in sql
    assert "cash_balances.aggregate_version = 3" in sql


@pytest.mark.asyncio
async def test_repository_save_rejects_invalid_expected_version_before_querying() -> None:
    session = _FakeSession()
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="expected_version"):
        await repository.save(_balance(), expected_version=-1)

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_save_raises_concurrency_conflict_when_no_row_matches() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=0),))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ConcurrencyConflictError, match="version conflict") as exc_info:
        await repository.save(_balance(), expected_version=3)

    assert exc_info.value.retryable is True
    assert exc_info.value.context == {"balance_id": "cash_01k0000000000000000000000"}


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.list_for_account(
            exchange="kalshi",
            account_id=AccountId("acct_01k00000000000000000000000"),
        )


@pytest.mark.asyncio
async def test_repository_classifies_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = CashBalanceRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_balance())


def _balance(**overrides: object) -> CashBalance:
    payload: dict[str, object] = {
        "balance_id": "cash_01k0000000000000000000000",
        "exchange": "kalshi",
        "account_id": "acct_01k00000000000000000000000",
        "currency": "USD",
        "available": "90.00",
        "reserved": "10.00",
        "total": "100.00",
        "captured_at": NOW,
    }
    payload.update(overrides)
    return CashBalance.model_validate(payload)


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
        self.added: list[CashBalanceRow] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: CashBalanceRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        if self._flush_error is not None:
            raise self._flush_error
        self.flushed += 1

    async def execute(self, statement: ClauseElement) -> _FakeResult | _FakeUpdateResult:
        if self._execute_error is not None:
            raise self._execute_error
        self.statements.append(statement)
        value = self._results.pop(0) if self._results else None
        if isinstance(value, _FakeUpdateResult):
            return value
        return _FakeResult(value)


class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> CashBalanceRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[CashBalanceRow]:
        if self._value is None:
            return []
        if isinstance(self._value, tuple):
            return list(self._value)  # type: ignore[return-value]
        return [self._value]  # type: ignore[list-item]


class _FakeUpdateResult:
    def __init__(self, *, rowcount: int | None) -> None:
        self.rowcount = rowcount
