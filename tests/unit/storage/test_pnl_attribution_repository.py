"""Tests for portfolio PnL attribution persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.sql import ClauseElement

from pmrp.schemas.identifiers import MarketId, StrategyId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import PnlAttribution
from pmrp.storage import ConcurrencyConflictError, PersistenceTimeoutError
from pmrp.storage.models import PnlAttributionRow
from pmrp.storage.repositories import (
    PnlAttributionRepository,
    pnl_attribution_from_row,
    pnl_attribution_to_row,
)

pytestmark = pytest.mark.unit

STARTS_AT = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
ENDS_AT = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)


def test_pnl_attribution_to_row_preserves_exact_values() -> None:
    attribution = _attribution()

    row = pnl_attribution_to_row(attribution)

    assert row.attribution_id == "pnl_01k0000000000000000000000"
    assert row.strategy_id == "strat_pnl_repository"
    assert row.market_id == "mkt_pnl_repository"
    assert row.exchange == "kalshi"
    assert row.starts_at == STARTS_AT
    assert row.ends_at == ENDS_AT
    assert row.currency == "USD"
    assert row.realized_trading_pnl == Decimal("12.50")
    assert row.unrealized_pnl_change == Decimal("-0.50")
    assert row.fees == Decimal("0.25")
    assert row.rebates == Decimal("0.05")
    assert row.slippage == Decimal("-0.10")
    assert row.settlement_pnl == Decimal("2.00")
    assert row.total_pnl == Decimal("13.70")
    assert row.calculation_version == "journal_pnl_attribution_v1"


def test_pnl_attribution_to_row_preserves_optional_nulls() -> None:
    row = pnl_attribution_to_row(
        _attribution(
            strategy_id=None,
            market_id=None,
            exchange=None,
            slippage=None,
            settlement_pnl=None,
            total_pnl=_money("11.80"),
        )
    )

    assert row.strategy_id is None
    assert row.market_id is None
    assert row.exchange is None
    assert row.slippage is None
    assert row.settlement_pnl is None


def test_pnl_attribution_from_row_round_trips_attribution() -> None:
    attribution = _attribution()
    row = pnl_attribution_to_row(attribution)

    assert pnl_attribution_from_row(row) == attribution


@pytest.mark.asyncio
async def test_repository_add_inserts_row_and_flushes_without_commit() -> None:
    session = _FakeSession()
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    await repository.add(_attribution())

    assert len(session.added) == 1
    assert isinstance(session.added[0], PnlAttributionRow)
    assert session.added[0].total_pnl == Decimal("13.70")
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_get_queries_attribution_id() -> None:
    row = pnl_attribution_to_row(_attribution())
    session = _FakeSession(results=(row,))
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    result = await repository.get("pnl_01k0000000000000000000000")

    assert result == _attribution()
    assert "pnl_attributions.attribution_id = 'pnl_01k0000000000000000000000'" in _compile(
        session.statements[0]
    )


@pytest.mark.asyncio
async def test_repository_get_returns_none_when_missing() -> None:
    session = _FakeSession(results=(None,))
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    result = await repository.get("pnl_01k0000000000000000000000")

    assert result is None


@pytest.mark.asyncio
async def test_repository_list_by_strategy_period_uses_documented_query_path() -> None:
    row = pnl_attribution_to_row(_attribution())
    session = _FakeSession(results=((row,),))
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    result = await repository.list_by_strategy_period(
        strategy_id=StrategyId("strat_pnl_repository"),
        starts_at=STARTS_AT - timedelta(minutes=1),
        ends_at=ENDS_AT + timedelta(minutes=1),
        limit=25,
    )

    assert result == (_attribution(),)
    sql = _compile(session.statements[0])
    assert "pnl_attributions.strategy_id = 'strat_pnl_repository'" in sql
    assert "pnl_attributions.starts_at >=" in sql
    assert "pnl_attributions.ends_at <=" in sql
    assert "ORDER BY pmrp_portfolio.pnl_attributions.starts_at" in sql
    assert "pmrp_portfolio.pnl_attributions.ends_at" in sql
    assert "pmrp_portfolio.pnl_attributions.attribution_id" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_list_by_market_uses_deterministic_market_query() -> None:
    row = pnl_attribution_to_row(_attribution())
    session = _FakeSession(results=((row,),))
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    result = await repository.list_by_market(
        MarketId("mkt_pnl_repository"),
        exchange="kalshi",
        limit=25,
    )

    assert result == (_attribution(),)
    sql = _compile(session.statements[0])
    assert "pnl_attributions.market_id = 'mkt_pnl_repository'" in sql
    assert "pnl_attributions.exchange = 'kalshi'" in sql
    assert "ORDER BY pmrp_portfolio.pnl_attributions.starts_at" in sql
    assert "pmrp_portfolio.pnl_attributions.ends_at" in sql
    assert "pmrp_portfolio.pnl_attributions.attribution_id" in sql
    assert "LIMIT 25" in sql


@pytest.mark.asyncio
async def test_repository_rejects_invalid_filters_before_querying() -> None:
    session = _FakeSession()
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="ends_at must be after starts_at"):
        await repository.list_by_strategy_period(
            strategy_id="strat_pnl_repository",
            starts_at=STARTS_AT,
            ends_at=STARTS_AT,
        )
    with pytest.raises(ValueError, match="exchange must not be empty"):
        await repository.list_by_market("mkt_pnl_repository", exchange="")
    with pytest.raises(ValueError, match="limit must be positive"):
        await repository.list_by_market("mkt_pnl_repository", limit=0)

    assert session.statements == []


@pytest.mark.asyncio
async def test_repository_save_updates_existing_row_and_flushes_without_commit() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=1),))
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    await repository.save(
        _attribution(
            realized_trading_pnl=_money("13.00"),
            total_pnl=_money("14.20"),
        )
    )

    assert session.flushed == 1
    assert session.committed == 0
    sql = _compile(session.statements[0])
    assert "UPDATE pmrp_portfolio.pnl_attributions" in sql
    assert "realized_trading_pnl=13.00" in sql
    assert "total_pnl=14.20" in sql
    assert "pnl_attributions.attribution_id = 'pnl_01k0000000000000000000000'" in sql


@pytest.mark.asyncio
async def test_repository_save_raises_concurrency_conflict_when_no_row_matches() -> None:
    session = _FakeSession(results=(_FakeUpdateResult(rowcount=0),))
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ConcurrencyConflictError, match="update conflict") as exc_info:
        await repository.save(_attribution())

    assert exc_info.value.retryable is True
    assert exc_info.value.context == {"attribution_id": "pnl_01k0000000000000000000000"}


@pytest.mark.asyncio
async def test_repository_classifies_sqlalchemy_execute_errors() -> None:
    session = _FakeSession(execute_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.list_by_market("mkt_pnl_repository")


@pytest.mark.asyncio
async def test_repository_classifies_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = PnlAttributionRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add(_attribution())


def _attribution(**overrides: object) -> PnlAttribution:
    payload: dict[str, object] = {
        "attribution_id": "pnl_01k0000000000000000000000",
        "strategy_id": "strat_pnl_repository",
        "market_id": "mkt_pnl_repository",
        "exchange": "kalshi",
        "starts_at": STARTS_AT,
        "ends_at": ENDS_AT,
        "realized_trading_pnl": _money("12.50"),
        "unrealized_pnl_change": _money("-0.50"),
        "fees": _money("0.25"),
        "rebates": _money("0.05"),
        "slippage": _money("-0.10"),
        "settlement_pnl": _money("2.00"),
        "total_pnl": _money("13.70"),
        "calculation_version": "journal_pnl_attribution_v1",
    }
    payload.update(overrides)
    return PnlAttribution.model_validate(payload)


def _money(amount: str, *, currency: str = "USD") -> Money:
    return Money(amount=Decimal(amount), currency=currency)


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
        self.added: list[PnlAttributionRow] = []
        self.statements: list[ClauseElement] = []
        self.flushed = 0
        self.committed = 0
        self._results = list(results)
        self._execute_error = execute_error
        self._flush_error = flush_error

    def add(self, row: PnlAttributionRow) -> None:
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

    def scalar_one_or_none(self) -> PnlAttributionRow | None:
        if self._value is None:
            return None
        return self._value  # type: ignore[return-value]

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[PnlAttributionRow]:
        if self._value is None:
            return []
        if isinstance(self._value, tuple):
            return list(self._value)  # type: ignore[return-value]
        return [self._value]  # type: ignore[list-item]


class _FakeUpdateResult:
    def __init__(self, *, rowcount: int | None) -> None:
        self.rowcount = rowcount
