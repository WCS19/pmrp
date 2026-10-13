"""Tests for portfolio position projection persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.schemas.identifiers import AccountId, ContractId, MarketId, PositionId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import Position
from pmrp.storage import ConcurrencyConflictError, InvariantViolationError, PersistenceTimeoutError
from pmrp.storage.models import PositionRow
from pmrp.storage.repositories import (
    PositionRepository,
    position_from_row,
    position_to_row,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_position_to_row_preserves_exact_values() -> None:
    position = _position()

    row = position_to_row(position)

    assert row.position_id == "pos_01k00000000000000000000000"
    assert row.exchange == "kalshi"
    assert row.account_id == "acct_01k00000000000000000000000"
    assert row.market_id == "mkt_position_repository"
    assert row.contract_id == "ctr_position_repository"
    assert row.outcome_id == "out_yes"
    assert row.quantity == Decimal("12.50")
    assert row.average_entry_price == Decimal("0.42")
    assert row.realized_pnl_amount == Decimal("1.25")
    assert row.unrealized_pnl_amount == Decimal("-0.50")
    assert row.currency == "USD"
    assert row.fees_paid_amount == Decimal("0.10")
    assert row.rebates_received_amount == Decimal("0.02")
    assert row.opened_at == NOW - timedelta(minutes=10)
    assert row.last_updated_at == NOW
    assert row.aggregate_version == 3


def test_position_from_row_round_trips_position() -> None:
    position = _position()
    row = position_to_row(position)

    assert position_from_row(row) == position


def test_position_to_row_rejects_mixed_money_currencies() -> None:
    position = _position(unrealized_pnl=Money(amount=Decimal("0"), currency="EUR"))

    with pytest.raises(InvariantViolationError, match="share one currency") as exc_info:
        position_to_row(position)

    assert exc_info.value.context == {"position_id": "pos_01k00000000000000000000000"}


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = PositionRepository(session)  # type: ignore[arg-type]

    await repository.add(_position())

    assert len(session.added) == 1
    assert isinstance(session.added[0], PositionRow)
    assert session.added[0].quantity == Decimal("12.50")
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_get_accepts_typed_position_id() -> None:
    row = position_to_row(_position())
    session = _FakeSession(results=(row,))
    repository = PositionRepository(session)  # type: ignore[arg-type]

    result = await repository.get(PositionId("pos_01k00000000000000000000000"))

    assert result == _position()
    assert "positions.position_id = 'pos_01k00000000000000000000000'" in _compile(
        session.statements[0]
    )


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = PositionRepository(session)  # type: ignore[arg-type]

    result = await repository.get("pos_01k00000000000000000000000")

    assert result is None


@pytest.mark.asyncio
async def test_repository_get_by_contract_uses_unique_contract_query() -> None:
    row = position_to_row(_position())
    session = _FakeSession(results=(row,))
    repository = PositionRepository(session)  # type: ignore[arg-type]

    result = await repository.get_by_contract(
        exchange="kalshi",
        account_id=AccountId("acct_01k00000000000000000000000"),
        contract_id=ContractId("ctr_position_repository"),
    )

    assert result == _position()
    sql = _compile(session.statements[0])
    assert "positions.exchange = 'kalshi'" in sql
    assert "positions.account_id = 'acct_01k00000000000000000000000'" in sql
    assert "positions.contract_id = 'ctr_position_repository'" in sql


@pytest.mark.asyncio
async def test_repository_list_for_account_market_uses_documented_query_path() -> None:
    row = position_to_row(_position())
    session = _FakeSession(results=((row,),))
    repository = PositionRepository(session)  # type: ignore[arg-type]

    result = await repository.list_for_account_market(
        exchange="kalshi",
        account_id=AccountId("acct_01k00000000000000000000000"),
        market_id=MarketId("mkt_position_repository"),
        limit=25,
    )

    assert result == (_position(),)
    sql = _compile(session.statements[0])
    assert "positions.exchange = 'kalshi'" in sql
    assert "positions.account_id = 'acct_01k00000000000000000000000'" in sql
    assert "positions.market_id = 'mkt_position_repository'" in sql
    assert "ORDER BY pmrp_portfolio.positions.market_id" in sql
    assert "pmrp_portfolio.positions.contract_id" in sql
    assert "pmrp_portfolio.positions.position_id" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_list_for_account_market_rejects_invalid_limit_before_querying() -> None:
    session = _FakeSession()
    repository = PositionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be positive"):
        await repository.list_for_account_market(
            exchange="kalshi",
            account_id="acct_01k00000000000000000000000",
            limit=0,
        )

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_save_updates_expected_version_and_flushes_without_commit() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=1),))
    repository = PositionRepository(session)  # type: ignore[arg-type]

    await repository.save(_position(aggregate_version=4), expected_version=3)

    assert session.flushed == 1
    assert session.committed == 0
    sql = _compile(session.statements[0])
    assert "UPDATE pmrp_portfolio.positions" in sql
    assert "quantity=12.50" in sql
    assert "average_entry_price=0.42" in sql
    assert "realized_pnl_amount=1.25" in sql
    assert "unrealized_pnl_amount=-0.50" in sql
    assert "currency='USD'" in sql
    assert "aggregate_version=4" in sql
    assert "positions.position_id = 'pos_01k00000000000000000000000'" in sql
    assert "positions.aggregate_version = 3" in sql


@pytest.mark.asyncio
async def test_repository_save_rejects_non_incrementing_aggregate_version() -> None:
    session = _FakeSession()
    repository = PositionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(InvariantViolationError, match="aggregate_version"):
        await repository.save(_position(aggregate_version=3), expected_version=3)

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_save_raises_concurrency_conflict_when_no_row_matches() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=0),))
    repository = PositionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ConcurrencyConflictError, match="version conflict") as exc_info:
        await repository.save(_position(aggregate_version=4), expected_version=3)

    assert exc_info.value.retryable is True
    assert exc_info.value.context == {"position_id": "pos_01k00000000000000000000000"}


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = PositionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.list_for_account_market(
            exchange="kalshi",
            account_id=AccountId("acct_01k00000000000000000000000"),
        )


@pytest.mark.asyncio
async def test_repository_classifies_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = PositionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_position())


def _position(**overrides: object) -> Position:
    payload: dict[str, object] = {
        "position_id": "pos_01k00000000000000000000000",
        "exchange": "kalshi",
        "account_id": "acct_01k00000000000000000000000",
        "market_id": "mkt_position_repository",
        "contract_id": "ctr_position_repository",
        "outcome_id": "out_yes",
        "quantity": "12.50",
        "average_entry_price": "0.42",
        "realized_pnl": {"amount": "1.25", "currency": "USD"},
        "unrealized_pnl": {"amount": "-0.50", "currency": "USD"},
        "fees_paid": {"amount": "0.10", "currency": "USD"},
        "rebates_received": {"amount": "0.02", "currency": "USD"},
        "opened_at": NOW - timedelta(minutes=10),
        "last_updated_at": NOW,
        "aggregate_version": 3,
    }
    payload.update(overrides)
    return Position.model_validate(payload)


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
        self.added: list[PositionRow] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: PositionRow) -> None:
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

    def scalar_one_or_none(self) -> PositionRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[PositionRow]:
        if self._value is None:
            return []
        if isinstance(self._value, tuple):
            return list(self._value)  # type: ignore[return-value]
        return [self._value]  # type: ignore[list-item]


class _FakeUpdateResult:
    def __init__(self, *, rowcount: int | None) -> None:
        self.rowcount = rowcount
