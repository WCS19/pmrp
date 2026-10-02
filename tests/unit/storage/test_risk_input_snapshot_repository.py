"""Tests for canonical risk input snapshot persistence mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import Select

from pmrp.schemas.enums import ExchangeName
from pmrp.schemas.risk import RiskInputSnapshot
from pmrp.schemas.serialization import canonical_sha256
from pmrp.storage import DuplicateRecordError, InvariantViolationError, PersistenceTimeoutError
from pmrp.storage.models import RiskInputSnapshotRow
from pmrp.storage.repositories import (
    RiskInputSnapshotRepository,
    risk_input_snapshot_from_row,
    risk_input_snapshot_to_row,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


def test_risk_input_snapshot_to_row_serializes_canonical_payload() -> None:
    snapshot = _snapshot()

    row = risk_input_snapshot_to_row(snapshot)

    assert row.risk_input_snapshot_id == "risk_input_01k0000000000000000"
    assert row.captured_at == NOW - timedelta(seconds=1)
    assert row.strategy_id == "strat_01k00000000000000000000000"
    assert row.exchange == "kalshi"
    assert row.account_id == "acct_01k00000000000000000000000"
    assert row.market_id == "mkt_01k00000000000000000000000"
    assert row.current_position == Decimal("2.000000000000000000")
    assert row.open_order_quantity == Decimal("3.000000000000000000")
    assert row.available_balance == Decimal("100.000000000000000000")
    assert row.gross_exposure == Decimal("40.000000000000000000")
    assert row.net_exposure == Decimal("25.000000000000000000")
    assert row.daily_realized_pnl == Decimal("1.000000000000000000")
    assert row.daily_unrealized_pnl == Decimal("-0.250000000000000000")
    assert row.market_data_age_ms == 250
    assert row.reconciliation_healthy is True
    assert row.kill_switch_clear is True
    assert row.payload_hash == canonical_sha256(_database_scaled_snapshot())


def test_risk_input_snapshot_from_row_round_trips_canonical_snapshot() -> None:
    snapshot = _snapshot()
    row = risk_input_snapshot_to_row(snapshot)

    assert risk_input_snapshot_from_row(row) == snapshot


def test_risk_input_snapshot_from_row_accepts_database_scaled_decimals() -> None:
    row = risk_input_snapshot_to_row(_snapshot())
    row.current_position = Decimal("2.000000000000000000")
    row.open_order_quantity = Decimal("3.000000000000000000")
    row.available_balance = Decimal("100.000000000000000000")
    row.gross_exposure = Decimal("40.000000000000000000")
    row.net_exposure = Decimal("25.000000000000000000")
    row.daily_realized_pnl = Decimal("1.000000000000000000")
    row.daily_unrealized_pnl = Decimal("-0.250000000000000000")

    assert risk_input_snapshot_from_row(row) == _snapshot()


def test_risk_input_snapshot_from_row_accepts_database_normalized_signed_zero() -> None:
    snapshot = _snapshot().model_copy(update={"current_position": Decimal("-0")})
    row = risk_input_snapshot_to_row(snapshot)

    assert row.current_position == Decimal("0.000000000000000000")
    assert not row.current_position.is_signed()

    row.current_position = Decimal("0.000000000000000000")

    result = risk_input_snapshot_from_row(row)
    assert result.current_position == Decimal("0.000000000000000000")
    assert not result.current_position.is_signed()


def test_risk_input_snapshot_from_row_rejects_payload_hash_mismatch() -> None:
    row = risk_input_snapshot_to_row(_snapshot())
    row.payload_hash = "sha256:tampered"

    with pytest.raises(InvariantViolationError, match="payload hash mismatch") as exc_info:
        risk_input_snapshot_from_row(row)

    assert exc_info.value.context == {"risk_input_snapshot_id": "risk_input_01k0000000000000000"}


def test_risk_input_snapshot_to_row_rejects_decimal_values_beyond_database_scale() -> None:
    snapshot = _snapshot().model_copy(update={"current_position": Decimal("0.1234567890123456789")})

    with pytest.raises(InvariantViolationError, match="database scale") as exc_info:
        risk_input_snapshot_to_row(snapshot)

    assert exc_info.value.context == {"field_name": "current_position"}


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = RiskInputSnapshotRepository(session)  # type: ignore[arg-type]
    snapshot = _snapshot()

    await repository.add(snapshot)

    assert len(session.added) == 1
    assert isinstance(session.added[0], RiskInputSnapshotRow)
    assert session.added[0].payload_hash == canonical_sha256(_database_scaled_snapshot())
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_add_classifies_sqlalchemy_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = RiskInputSnapshotRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_snapshot())


@pytest.mark.asyncio
async def test_repository_add_classifies_duplicate_snapshot_id() -> None:
    session = _FakeSession(flush_error=_integrity_error(sqlstate="23505"))
    repository = RiskInputSnapshotRepository(session)  # type: ignore[arg-type]

    with pytest.raises(DuplicateRecordError, match="already exists") as exc_info:
        await repository.add(_snapshot())

    assert exc_info.value.context == {"sqlstate": "23505"}
    assert session.flushed == 0


@pytest.mark.asyncio
async def test_repository_get_queries_snapshot_id() -> None:
    row = risk_input_snapshot_to_row(_snapshot())
    session = _FakeSession(execute_rows=(row,))
    repository = RiskInputSnapshotRepository(session)  # type: ignore[arg-type]

    result = await repository.get("risk_input_01k0000000000000000")

    assert result == _snapshot()
    sql = _compile(session.statements[0])
    assert ("risk_input_snapshots.risk_input_snapshot_id = 'risk_input_01k0000000000000000'") in sql


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(execute_rows=(None,))
    repository = RiskInputSnapshotRepository(session)  # type: ignore[arg-type]

    result = await repository.get("risk_input_01k0000000000000000")

    assert result is None


@pytest.mark.asyncio
async def test_repository_get_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = RiskInputSnapshotRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.get("risk_input_01k0000000000000000")


def _snapshot() -> RiskInputSnapshot:
    return RiskInputSnapshot(
        risk_input_snapshot_id="risk_input_01k0000000000000000",
        captured_at=NOW - timedelta(seconds=1),
        strategy_id="strat_01k00000000000000000000000",
        exchange=ExchangeName.KALSHI.value,
        account_id="acct_01k00000000000000000000000",
        market_id="mkt_01k00000000000000000000000",
        current_position=Decimal("2"),
        open_order_quantity=Decimal("3"),
        available_balance=Decimal("100.00"),
        gross_exposure=Decimal("40.00"),
        net_exposure=Decimal("25.00"),
        daily_realized_pnl=Decimal("1.00"),
        daily_unrealized_pnl=Decimal("-0.25"),
        market_data_age_ms=250,
        reconciliation_healthy=True,
        kill_switch_clear=True,
    )


def _database_scaled_snapshot() -> RiskInputSnapshot:
    return _snapshot().model_copy(
        update={
            "current_position": Decimal("2.000000000000000000"),
            "open_order_quantity": Decimal("3.000000000000000000"),
            "available_balance": Decimal("100.000000000000000000"),
            "gross_exposure": Decimal("40.000000000000000000"),
            "net_exposure": Decimal("25.000000000000000000"),
            "daily_realized_pnl": Decimal("1.000000000000000000"),
            "daily_unrealized_pnl": Decimal("-0.250000000000000000"),
        }
    )


def _compile(statement: Select[Any]) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _integrity_error(*, sqlstate: str) -> IntegrityError:
    return IntegrityError(
        statement="INSERT INTO pmrp_ops.risk_input_snapshots (...)",
        params={},
        orig=_DatabaseError(sqlstate=sqlstate),
    )


class _DatabaseError(Exception):
    def __init__(self, *, sqlstate: str) -> None:
        super().__init__("database error")
        self.sqlstate = sqlstate


class _FakeSession:
    def __init__(
        self,
        *,
        execute_rows: tuple[RiskInputSnapshotRow | None, ...] = (),
        flush_error: Exception | None = None,
        execute_error: Exception | None = None,
    ) -> None:
        self.added: list[RiskInputSnapshotRow] = []
        self.statements: list[Select[Any]] = []
        self.flushed = 0
        self.committed = 0
        self._execute_rows = list(execute_rows)
        self._flush_error = flush_error
        self._execute_error = execute_error

    def add(self, row: RiskInputSnapshotRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        if self._flush_error is not None:
            raise self._flush_error
        self.flushed += 1

    async def execute(self, statement: Select[Any]) -> _FakeResult:
        if self._execute_error is not None:
            raise self._execute_error
        self.statements.append(statement)
        row = self._execute_rows.pop(0) if self._execute_rows else None
        return _FakeResult(row)


class _FakeResult:
    def __init__(self, row: RiskInputSnapshotRow | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> RiskInputSnapshotRow | None:
        return self._row
