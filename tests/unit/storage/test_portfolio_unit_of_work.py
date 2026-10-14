"""Tests for the SQLAlchemy portfolio unit-of-work adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.portfolio import PortfolioEventUnitOfWork
from pmrp.schemas.identifiers import AccountId, ContractId, EventId, MarketId, OutcomeId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import (
    AccountingJournalEntry,
    CashBalance,
    JournalLine,
    Position,
)
from pmrp.storage import SqlAlchemyPortfolioUnitOfWork, UnitOfWorkStateError
from pmrp.storage.models import (
    CashBalanceRow,
    JournalEntryRow,
    JournalLineRow,
    PositionRow,
)
from pmrp.storage.repositories import (
    CanonicalEventRepository,
    CashBalanceRepository,
    JournalEntryRepository,
    OutboxMessageRepository,
    PnlAttributionRepository,
    PositionRepository,
    ReconciliationResultRepository,
    SettlementRepository,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
ACCOUNT_ID = AccountId("acct_portfolio_uow")
MARKET_ID = MarketId("mkt_portfolio_uow")
CONTRACT_ID = ContractId("ctr_portfolio_uow")
OUTCOME_ID = OutcomeId("out_yes")
SOURCE_EVENT_ID = EventId("evt_portfolio_uow")


@pytest.mark.parametrize(
    "repository_attribute",
    [
        "canonical_events",
        "cash_balances",
        "journal_entries",
        "outbox_messages",
        "pnl_attributions",
        "positions",
        "reconciliation_results",
        "settlements",
    ],
)
def test_portfolio_unit_of_work_rejects_inactive_repository_access(
    repository_attribute: str,
) -> None:
    unit_of_work = SqlAlchemyPortfolioUnitOfWork(session_factory=_SessionFactory(_FakeSession()))

    with pytest.raises(UnitOfWorkStateError, match="not active"):
        _ = getattr(unit_of_work, repository_attribute)


@pytest.mark.asyncio
async def test_portfolio_unit_of_work_exposes_repositories_during_active_transaction() -> None:
    async with SqlAlchemyPortfolioUnitOfWork(
        session_factory=_SessionFactory(_FakeSession()),
    ) as unit_of_work:
        assert isinstance(unit_of_work.canonical_events, CanonicalEventRepository)
        assert isinstance(unit_of_work.cash_balances, CashBalanceRepository)
        assert isinstance(unit_of_work.journal_entries, JournalEntryRepository)
        assert isinstance(unit_of_work.outbox_messages, OutboxMessageRepository)
        assert isinstance(unit_of_work.pnl_attributions, PnlAttributionRepository)
        assert isinstance(unit_of_work.positions, PositionRepository)
        assert isinstance(unit_of_work.reconciliation_results, ReconciliationResultRepository)
        assert isinstance(unit_of_work.settlements, SettlementRepository)


@pytest.mark.asyncio
async def test_portfolio_unit_of_work_persists_accounting_records_and_commits() -> None:
    session = _FakeSession()

    async with SqlAlchemyPortfolioUnitOfWork(
        session_factory=_SessionFactory(session),
    ) as unit_of_work:
        await unit_of_work.positions.add(_position())
        await unit_of_work.cash_balances.add(_cash_balance())
        await unit_of_work.journal_entries.add(_journal_entry())
        await unit_of_work.commit()
        _assert_repositories_reject_after_finished(unit_of_work)

    assert [type(row) for row in session.added] == [
        PositionRow,
        CashBalanceRow,
        JournalEntryRow,
        JournalLineRow,
        JournalLineRow,
    ]
    assert session.flushed == 3
    assert session.committed == 1
    assert session.rolled_back == 0
    assert session.closed == 1


@pytest.mark.asyncio
async def test_portfolio_unit_of_work_rolls_back_clean_exit_without_commit() -> None:
    session = _FakeSession()

    async with SqlAlchemyPortfolioUnitOfWork(
        session_factory=_SessionFactory(session),
    ) as unit_of_work:
        await unit_of_work.positions.add(_position())

    assert session.flushed == 1
    assert session.committed == 0
    assert session.rolled_back == 1
    assert session.closed == 1


@pytest.mark.asyncio
async def test_portfolio_unit_of_work_explicit_rollback_finishes_transaction() -> None:
    session = _FakeSession()

    async with SqlAlchemyPortfolioUnitOfWork(
        session_factory=_SessionFactory(session),
    ) as unit_of_work:
        await unit_of_work.rollback()
        _assert_repositories_reject_after_finished(unit_of_work)

    assert session.committed == 0
    assert session.rolled_back == 1
    assert session.closed == 1


@pytest.mark.asyncio
async def test_portfolio_unit_of_work_conforms_to_event_workflow_protocol() -> None:
    async with SqlAlchemyPortfolioUnitOfWork(
        session_factory=_SessionFactory(_FakeSession()),
    ) as unit_of_work:
        assert isinstance(unit_of_work, PortfolioEventUnitOfWork)


def _position() -> Position:
    return Position(
        position_id="pos_portfolio_uow",
        exchange="kalshi",
        account_id=ACCOUNT_ID,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id=OUTCOME_ID,
        quantity=Decimal("10"),
        average_entry_price=Decimal("0.42"),
        realized_pnl=Money(amount=Decimal("0"), currency="USD"),
        unrealized_pnl=Money(amount=Decimal("0"), currency="USD"),
        fees_paid=Money(amount=Decimal("0.10"), currency="USD"),
        rebates_received=Money(amount=Decimal("0"), currency="USD"),
        opened_at=NOW - timedelta(minutes=5),
        last_updated_at=NOW,
        aggregate_version=1,
    )


def _cash_balance() -> CashBalance:
    return CashBalance(
        balance_id="cash_portfolio_uow",
        exchange="kalshi",
        account_id=ACCOUNT_ID,
        currency="USD",
        available=Decimal("89.90"),
        reserved=Decimal("10.00"),
        total=Decimal("99.90"),
        captured_at=NOW,
    )


def _journal_entry() -> AccountingJournalEntry:
    return AccountingJournalEntry(
        journal_entry_id="journal_portfolio_uow",
        occurred_at=NOW,
        source_event_id=SOURCE_EVENT_ID,
        reference_type="fill",
        reference_id="fill_portfolio_uow",
        lines=(
            JournalLine(
                account_code="cash",
                amount=Decimal("-10.00"),
                currency="USD",
                description="Cash outflow.",
            ),
            JournalLine(
                account_code="position_cost",
                amount=Decimal("10.00"),
                currency="USD",
                description="Position cost basis.",
            ),
        ),
        description="Portfolio unit-of-work journal.",
        created_at=NOW,
    )


def _assert_repositories_reject_after_finished(
    unit_of_work: SqlAlchemyPortfolioUnitOfWork,
) -> None:
    for repository_attribute in (
        "canonical_events",
        "cash_balances",
        "journal_entries",
        "outbox_messages",
        "pnl_attributions",
        "positions",
        "reconciliation_results",
        "settlements",
    ):
        with pytest.raises(UnitOfWorkStateError, match="already finished"):
            _ = getattr(unit_of_work, repository_attribute)


class _SessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self) -> _FakeSession:
        return self._session


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[CashBalanceRow | JournalEntryRow | JournalLineRow | PositionRow] = []
        self.flushed = 0
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def add(self, row: CashBalanceRow | JournalEntryRow | JournalLineRow | PositionRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1

    async def close(self) -> None:
        self.closed += 1
