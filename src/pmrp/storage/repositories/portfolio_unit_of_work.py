"""SQLAlchemy unit-of-work adapter for portfolio persistence repositories."""

from __future__ import annotations

from types import TracebackType
from typing import Literal, Self

from pmrp.storage.errors import UnitOfWorkStateError
from pmrp.storage.repositories.canonical_events import CanonicalEventRepository
from pmrp.storage.repositories.cash_balances import CashBalanceRepository
from pmrp.storage.repositories.journal_entries import JournalEntryRepository
from pmrp.storage.repositories.outbox import OutboxMessageRepository
from pmrp.storage.repositories.pnl_attributions import PnlAttributionRepository
from pmrp.storage.repositories.positions import PositionRepository
from pmrp.storage.repositories.reconciliation_results import ReconciliationResultRepository
from pmrp.storage.repositories.settlements import SettlementRepository
from pmrp.storage.session import AsyncSessionFactory
from pmrp.storage.transactions import SqlAlchemyUnitOfWork


class SqlAlchemyPortfolioUnitOfWork:
    """Wire portfolio repositories into one explicit SQLAlchemy transaction."""

    def __init__(self, *, session_factory: AsyncSessionFactory) -> None:
        self._unit_of_work = SqlAlchemyUnitOfWork(session_factory=session_factory)
        self._canonical_events: CanonicalEventRepository | None = None
        self._cash_balances: CashBalanceRepository | None = None
        self._journal_entries: JournalEntryRepository | None = None
        self._outbox_messages: OutboxMessageRepository | None = None
        self._pnl_attributions: PnlAttributionRepository | None = None
        self._positions: PositionRepository | None = None
        self._reconciliation_results: ReconciliationResultRepository | None = None
        self._settlements: SettlementRepository | None = None

    async def __aenter__(self) -> Self:
        await self._unit_of_work.__aenter__()
        session = self._unit_of_work.session
        self._canonical_events = CanonicalEventRepository(session)
        self._cash_balances = CashBalanceRepository(session)
        self._journal_entries = JournalEntryRepository(session)
        self._outbox_messages = OutboxMessageRepository(session)
        self._pnl_attributions = PnlAttributionRepository(session)
        self._positions = PositionRepository(session)
        self._reconciliation_results = ReconciliationResultRepository(session)
        self._settlements = SettlementRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            await self._unit_of_work.__aexit__(exc_type, exc, traceback)
            return False
        finally:
            self._canonical_events = None
            self._cash_balances = None
            self._journal_entries = None
            self._outbox_messages = None
            self._pnl_attributions = None
            self._positions = None
            self._reconciliation_results = None
            self._settlements = None

    @property
    def canonical_events(self) -> CanonicalEventRepository:
        """Return the active canonical event repository."""

        if self._canonical_events is None:
            raise UnitOfWorkStateError("portfolio unit of work is not active")
        _ = self._unit_of_work.session
        return self._canonical_events

    @property
    def cash_balances(self) -> CashBalanceRepository:
        """Return the active cash balance repository."""

        if self._cash_balances is None:
            raise UnitOfWorkStateError("portfolio unit of work is not active")
        _ = self._unit_of_work.session
        return self._cash_balances

    @property
    def journal_entries(self) -> JournalEntryRepository:
        """Return the active accounting journal repository."""

        if self._journal_entries is None:
            raise UnitOfWorkStateError("portfolio unit of work is not active")
        _ = self._unit_of_work.session
        return self._journal_entries

    @property
    def outbox_messages(self) -> OutboxMessageRepository:
        """Return the active transactional outbox repository."""

        if self._outbox_messages is None:
            raise UnitOfWorkStateError("portfolio unit of work is not active")
        _ = self._unit_of_work.session
        return self._outbox_messages

    @property
    def pnl_attributions(self) -> PnlAttributionRepository:
        """Return the active PnL attribution repository."""

        if self._pnl_attributions is None:
            raise UnitOfWorkStateError("portfolio unit of work is not active")
        _ = self._unit_of_work.session
        return self._pnl_attributions

    @property
    def positions(self) -> PositionRepository:
        """Return the active position repository."""

        if self._positions is None:
            raise UnitOfWorkStateError("portfolio unit of work is not active")
        _ = self._unit_of_work.session
        return self._positions

    @property
    def reconciliation_results(self) -> ReconciliationResultRepository:
        """Return the active reconciliation result repository."""

        if self._reconciliation_results is None:
            raise UnitOfWorkStateError("portfolio unit of work is not active")
        _ = self._unit_of_work.session
        return self._reconciliation_results

    @property
    def settlements(self) -> SettlementRepository:
        """Return the active settlement repository."""

        if self._settlements is None:
            raise UnitOfWorkStateError("portfolio unit of work is not active")
        _ = self._unit_of_work.session
        return self._settlements

    async def commit(self) -> None:
        """Commit the active portfolio transaction."""

        await self._unit_of_work.commit()

    async def rollback(self) -> None:
        """Roll back the active portfolio transaction."""

        await self._unit_of_work.rollback()
