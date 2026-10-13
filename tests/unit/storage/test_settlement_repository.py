"""Tests for canonical settlement lifecycle persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.schemas.identifiers import MarketId, SettlementId
from pmrp.schemas.portfolio import Settlement, SettlementStatus
from pmrp.storage import ConcurrencyConflictError, PersistenceTimeoutError
from pmrp.storage.models import SettlementRow
from pmrp.storage.repositories import (
    SettlementRepository,
    settlement_from_row,
    settlement_to_row,
)

pytestmark = pytest.mark.unit

RESOLVED_AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)
FINALIZED_AT = datetime(2026, 9, 26, 14, 5, tzinfo=UTC)
SETTLED_AT = datetime(2026, 9, 26, 14, 10, tzinfo=UTC)


def test_settlement_to_row_preserves_exact_values() -> None:
    settlement = _settlement()

    row = settlement_to_row(settlement)

    assert row.settlement_id == "set_01k0000000000000000000000"
    assert row.market_id == "mkt_settlement_repository"
    assert row.exchange == "kalshi"
    assert row.status == "settled"
    assert row.winning_outcome_ids == ["out_yes"]
    assert row.resolved_at == RESOLVED_AT
    assert row.finalized_at == FINALIZED_AT
    assert row.settled_at == SETTLED_AT
    assert row.payout_per_unit == Decimal("1.00")
    assert row.source == "exchange_settlement"
    assert row.source_reference == "settlement-feed-001"
    assert row.correction_of_settlement_id is None


def test_settlement_to_row_preserves_unresolved_empty_resolution_fields() -> None:
    row = settlement_to_row(_unresolved_settlement())

    assert row.status == "unresolved"
    assert row.winning_outcome_ids == []
    assert row.resolved_at is None
    assert row.finalized_at is None
    assert row.settled_at is None
    assert row.payout_per_unit is None
    assert row.correction_of_settlement_id is None


def test_settlement_from_row_round_trips_settlement() -> None:
    settlement = _settlement()
    row = settlement_to_row(settlement)

    assert settlement_from_row(row) == settlement


def test_settlement_from_row_preserves_correction_lineage() -> None:
    settlement = _corrected_settlement()
    row = settlement_to_row(settlement)

    assert settlement_from_row(row) == settlement
    assert row.correction_of_settlement_id == "set_01k_previous_settlement"


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    await repository.add(_settlement())

    assert len(session.added) == 1
    assert isinstance(session.added[0], SettlementRow)
    assert session.added[0].settlement_id == "set_01k0000000000000000000000"
    assert session.added[0].payout_per_unit == Decimal("1.00")
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_get_accepts_typed_settlement_id() -> None:
    row = settlement_to_row(_settlement())
    session = _FakeSession(results=(row,))
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    result = await repository.get(SettlementId("set_01k0000000000000000000000"))

    assert result == _settlement()
    assert "settlements.settlement_id = 'set_01k0000000000000000000000'" in _compile(
        session.statements[0]
    )


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    result = await repository.get("set_01k0000000000000000000000")

    assert result is None


@pytest.mark.asyncio
async def test_repository_list_by_market_uses_documented_query_path() -> None:
    row = settlement_to_row(_settlement())
    session = _FakeSession(results=((row,),))
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    result = await repository.list_by_market(
        MarketId("mkt_settlement_repository"),
        exchange="kalshi",
        limit=25,
    )

    assert result == (_settlement(),)
    sql = _compile(session.statements[0])
    assert "settlements.market_id = 'mkt_settlement_repository'" in sql
    assert "settlements.exchange = 'kalshi'" in sql
    assert "ORDER BY pmrp_portfolio.settlements.created_at DESC" in sql
    assert "pmrp_portfolio.settlements.settlement_id DESC" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_list_corrections_uses_correction_lineage_query() -> None:
    row = settlement_to_row(_corrected_settlement())
    session = _FakeSession(results=((row,),))
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    result = await repository.list_corrections(
        SettlementId("set_01k_previous_settlement"),
        limit=25,
    )

    assert result == (_corrected_settlement(),)
    sql = _compile(session.statements[0])
    assert "settlements.correction_of_settlement_id = 'set_01k_previous_settlement'" in sql
    assert "ORDER BY pmrp_portfolio.settlements.created_at" in sql
    assert "pmrp_portfolio.settlements.settlement_id" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_rejects_invalid_filters_before_querying() -> None:
    session = _FakeSession()
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be positive"):
        await repository.list_by_market("mkt_settlement_repository", limit=0)
    with pytest.raises(ValueError, match="exchange must not be empty"):
        await repository.list_by_market("mkt_settlement_repository", exchange="")

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_save_updates_existing_row_and_flushes_without_commit() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=1),))
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    await repository.save(_settlement(status=SettlementStatus.FINALIZED, settled_at=None))

    assert session.flushed == 1
    assert session.committed == 0
    sql = _compile(session.statements[0])
    assert "UPDATE pmrp_portfolio.settlements" in sql
    assert "status='finalized'" in sql
    assert "payout_per_unit=1.00" in sql
    assert "settlements.settlement_id = 'set_01k0000000000000000000000'" in sql


@pytest.mark.asyncio
async def test_repository_save_raises_concurrency_conflict_when_no_row_matches() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=0),))
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ConcurrencyConflictError, match="update conflict") as exc_info:
        await repository.save(_settlement())

    assert exc_info.value.retryable is True
    assert exc_info.value.context == {"settlement_id": "set_01k0000000000000000000000"}


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.list_corrections("set_01k_previous_settlement")


@pytest.mark.asyncio
async def test_repository_classifies_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = SettlementRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_settlement())


def _settlement(**overrides: object) -> Settlement:
    payload: dict[str, object] = {
        "settlement_id": "set_01k0000000000000000000000",
        "market_id": "mkt_settlement_repository",
        "exchange": "kalshi",
        "status": SettlementStatus.SETTLED,
        "winning_outcome_ids": ("out_yes",),
        "resolved_at": RESOLVED_AT,
        "finalized_at": FINALIZED_AT,
        "settled_at": SETTLED_AT,
        "payout_per_unit": "1.00",
        "source": "exchange_settlement",
        "source_reference": "settlement-feed-001",
        "correction_of_settlement_id": None,
    }
    payload.update(overrides)
    return Settlement.model_validate(payload)


def _unresolved_settlement(**overrides: object) -> Settlement:
    payload: dict[str, object] = {
        "settlement_id": "set_01k0000000000000000000000",
        "market_id": "mkt_settlement_repository",
        "exchange": "kalshi",
        "status": SettlementStatus.UNRESOLVED,
        "winning_outcome_ids": (),
        "resolved_at": None,
        "finalized_at": None,
        "settled_at": None,
        "payout_per_unit": None,
        "source": "exchange_settlement",
        "source_reference": "settlement-feed-001",
        "correction_of_settlement_id": None,
    }
    payload.update(overrides)
    return Settlement.model_validate(payload)


def _corrected_settlement(**overrides: object) -> Settlement:
    payload: dict[str, object] = {
        "settlement_id": "set_01k_correction_settlement",
        "market_id": "mkt_settlement_repository",
        "exchange": "kalshi",
        "status": SettlementStatus.CORRECTED,
        "winning_outcome_ids": ("out_no",),
        "resolved_at": RESOLVED_AT,
        "finalized_at": FINALIZED_AT,
        "settled_at": SETTLED_AT,
        "payout_per_unit": "1.00",
        "source": "exchange_settlement",
        "source_reference": "settlement-feed-correction",
        "correction_of_settlement_id": "set_01k_previous_settlement",
    }
    payload.update(overrides)
    return Settlement.model_validate(payload)


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
        self.added: list[SettlementRow] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: SettlementRow) -> None:
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

    def scalar_one_or_none(self) -> SettlementRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[SettlementRow]:
        if self._value is None:
            return []
        if isinstance(self._value, tuple):
            return list(self._value)  # type: ignore[return-value]
        return [self._value]  # type: ignore[list-item]


class _FakeUpdateResult:
    def __init__(self, *, rowcount: int | None) -> None:
        self.rowcount = rowcount
