"""Tests for capital reservation persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.risk import CapitalReservation, CapitalReservationStatus
from pmrp.schemas.enums import ExchangeName
from pmrp.storage import PersistenceTimeoutError
from pmrp.storage.models import CapitalReservationRow
from pmrp.storage.repositories import (
    CapitalReservationRepository,
    capital_reservation_from_row,
    capital_reservation_to_row,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_capital_reservation_to_row_preserves_exact_values() -> None:
    reservation = _reservation()

    row = capital_reservation_to_row(reservation)

    assert row.reservation_id == "reserve_01k00000000000000000000000"
    assert row.intent_id == "intent_01k00000000000000000000000"
    assert row.strategy_id == "strat_risk_reservation"
    assert row.exchange == "kalshi"
    assert row.account_id == "acct_01k00000000000000000000000"
    assert row.market_id == "mkt_risk_reservation"
    assert row.quantity == Decimal("10")
    assert row.notional == Decimal("4.20")
    assert row.currency == "USD"
    assert row.status == "active"
    assert row.created_at == NOW
    assert row.expires_at == NOW + timedelta(minutes=5)
    assert row.released_at is None


def test_capital_reservation_from_row_round_trips_reservation() -> None:
    reservation = _reservation()
    row = capital_reservation_to_row(reservation)

    assert capital_reservation_from_row(row) == reservation


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = CapitalReservationRepository(session)  # type: ignore[arg-type]

    await repository.add(_reservation())

    assert len(session.added) == 1
    assert isinstance(session.added[0], CapitalReservationRow)
    assert session.added[0].notional == Decimal("4.20")
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_get_by_intent_uses_unique_intent_query() -> None:
    row = capital_reservation_to_row(_reservation())
    session = _FakeSession(results=(row,))
    repository = CapitalReservationRepository(session)  # type: ignore[arg-type]

    result = await repository.get_by_intent("intent_01k00000000000000000000000")  # type: ignore[arg-type]

    assert result == _reservation()
    sql = _compile(session.statements[0])
    assert "capital_reservations.intent_id = 'intent_01k00000000000000000000000'" in sql


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = CapitalReservationRepository(session)  # type: ignore[arg-type]

    result = await repository.get("reserve_01k00000000000000000000000")

    assert result is None


@pytest.mark.asyncio
async def test_repository_active_notional_sum_uses_active_scope_filters() -> None:
    session = _FakeSession(results=(Decimal("14.20"),))
    repository = CapitalReservationRepository(session)  # type: ignore[arg-type]

    result = await repository.active_notional_sum(
        as_of=NOW,
        exchange=ExchangeName.KALSHI,
        account_id="acct_01k00000000000000000000000",  # type: ignore[arg-type]
        strategy_id="strat_risk_reservation",  # type: ignore[arg-type]
        market_id="mkt_risk_reservation",  # type: ignore[arg-type]
        currency="USD",
    )

    assert result == Decimal("14.20")
    sql = _compile(session.statements[0])
    assert "sum(pmrp_risk.capital_reservations.notional)" in sql
    assert "capital_reservations.status = 'active'" in sql
    assert "capital_reservations.released_at IS NULL" in sql
    assert "capital_reservations.expires_at > '2026-09-22 12:00:00+00:00'" in sql
    assert "capital_reservations.exchange = 'kalshi'" in sql
    assert "capital_reservations.account_id = 'acct_01k00000000000000000000000'" in sql
    assert "capital_reservations.strategy_id = 'strat_risk_reservation'" in sql
    assert "capital_reservations.market_id = 'mkt_risk_reservation'" in sql
    assert "capital_reservations.currency = 'USD'" in sql


@pytest.mark.asyncio
async def test_repository_active_notional_sum_rejects_invalid_currency_filter() -> None:
    session = _FakeSession()
    repository = CapitalReservationRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="currency must be"):
        await repository.active_notional_sum(as_of=NOW, currency="usd")

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_release_updates_only_active_unreleased_reservation() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=1),))
    repository = CapitalReservationRepository(session)  # type: ignore[arg-type]

    row_count = await repository.release(
        "reserve_01k00000000000000000000000",
        released_at=NOW + timedelta(minutes=1),
    )

    assert row_count == 1
    assert session.flushed == 1
    assert session.committed == 0
    sql = _compile(session.statements[0])
    assert "UPDATE pmrp_risk.capital_reservations" in sql
    assert "status='released'" in sql
    assert "released_at='2026-09-22 12:01:00+00:00'" in sql
    assert "capital_reservations.reservation_id = 'reserve_01k00000000000000000000000'" in sql
    assert "capital_reservations.status = 'active'" in sql
    assert "capital_reservations.released_at IS NULL" in sql


@pytest.mark.asyncio
async def test_repository_release_expired_updates_closed_windows() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=3),))
    repository = CapitalReservationRepository(session)  # type: ignore[arg-type]

    row_count = await repository.release_expired(as_of=NOW)

    assert row_count == 3
    sql = _compile(session.statements[0])
    assert "status='expired'" in sql
    assert "released_at='2026-09-22 12:00:00+00:00'" in sql
    assert "capital_reservations.status = 'active'" in sql
    assert "capital_reservations.released_at IS NULL" in sql
    assert "capital_reservations.expires_at <= '2026-09-22 12:00:00+00:00'" in sql


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = CapitalReservationRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.active_notional_sum(as_of=NOW)


@pytest.mark.asyncio
async def test_repository_classifies_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = CapitalReservationRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_reservation())


def _reservation(**overrides: object) -> CapitalReservation:
    payload: dict[str, object] = {
        "reservation_id": "reserve_01k00000000000000000000000",
        "intent_id": "intent_01k00000000000000000000000",
        "strategy_id": "strat_risk_reservation",
        "exchange": ExchangeName.KALSHI,
        "account_id": "acct_01k00000000000000000000000",
        "market_id": "mkt_risk_reservation",
        "quantity": "10",
        "notional": "4.20",
        "currency": "USD",
        "status": CapitalReservationStatus.ACTIVE,
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "released_at": None,
    }
    payload.update(overrides)
    return CapitalReservation(**payload)  # type: ignore[arg-type]


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
        self.added: list[CapitalReservationRow] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: CapitalReservationRow) -> None:
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

    def scalar_one_or_none(self) -> CapitalReservationRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalar_one(self) -> Decimal:
        return self._value  # type: ignore[return-value]


class _FakeUpdateResult:
    def __init__(self, *, rowcount: int) -> None:
        self.rowcount = rowcount
