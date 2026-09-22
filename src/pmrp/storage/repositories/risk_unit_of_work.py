"""SQLAlchemy unit-of-work adapter for risk persistence repositories."""

from __future__ import annotations

from types import TracebackType
from typing import Literal, Self

from pmrp.storage.errors import UnitOfWorkStateError
from pmrp.storage.repositories.capital_reservations import CapitalReservationRepository
from pmrp.storage.repositories.kill_switches import KillSwitchRepository
from pmrp.storage.repositories.risk_breaches import RiskBreachRepository
from pmrp.storage.repositories.risk_decisions import RiskDecisionRepository
from pmrp.storage.repositories.risk_limits import RiskLimitRepository
from pmrp.storage.session import AsyncSessionFactory
from pmrp.storage.transactions import SqlAlchemyUnitOfWork


class SqlAlchemyRiskUnitOfWork:
    """Wire risk repositories into the explicit SQLAlchemy unit of work."""

    def __init__(self, *, session_factory: AsyncSessionFactory) -> None:
        self._unit_of_work = SqlAlchemyUnitOfWork(session_factory=session_factory)
        self._capital_reservations: CapitalReservationRepository | None = None
        self._kill_switches: KillSwitchRepository | None = None
        self._risk_breaches: RiskBreachRepository | None = None
        self._risk_decisions: RiskDecisionRepository | None = None
        self._risk_limits: RiskLimitRepository | None = None

    async def __aenter__(self) -> Self:
        await self._unit_of_work.__aenter__()
        session = self._unit_of_work.session
        self._capital_reservations = CapitalReservationRepository(session)
        self._kill_switches = KillSwitchRepository(session)
        self._risk_breaches = RiskBreachRepository(session)
        self._risk_decisions = RiskDecisionRepository(session)
        self._risk_limits = RiskLimitRepository(session)
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
            self._capital_reservations = None
            self._kill_switches = None
            self._risk_breaches = None
            self._risk_decisions = None
            self._risk_limits = None

    @property
    def capital_reservations(self) -> CapitalReservationRepository:
        """Return the active capital reservation repository."""

        if self._capital_reservations is None:
            raise UnitOfWorkStateError("risk unit of work is not active")
        _ = self._unit_of_work.session
        return self._capital_reservations

    @property
    def kill_switches(self) -> KillSwitchRepository:
        """Return the active kill switch repository."""

        if self._kill_switches is None:
            raise UnitOfWorkStateError("risk unit of work is not active")
        _ = self._unit_of_work.session
        return self._kill_switches

    @property
    def risk_breaches(self) -> RiskBreachRepository:
        """Return the active risk breach repository."""

        if self._risk_breaches is None:
            raise UnitOfWorkStateError("risk unit of work is not active")
        _ = self._unit_of_work.session
        return self._risk_breaches

    @property
    def risk_decisions(self) -> RiskDecisionRepository:
        """Return the active risk decision repository."""

        if self._risk_decisions is None:
            raise UnitOfWorkStateError("risk unit of work is not active")
        _ = self._unit_of_work.session
        return self._risk_decisions

    @property
    def risk_limits(self) -> RiskLimitRepository:
        """Return the active risk limit repository."""

        if self._risk_limits is None:
            raise UnitOfWorkStateError("risk unit of work is not active")
        _ = self._unit_of_work.session
        return self._risk_limits

    async def commit(self) -> None:
        """Commit the active risk transaction."""

        await self._unit_of_work.commit()

    async def rollback(self) -> None:
        """Roll back the active risk transaction."""

        await self._unit_of_work.rollback()
