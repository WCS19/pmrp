"""SQLAlchemy unit-of-work adapter for risk persistence repositories."""

from __future__ import annotations

from types import TracebackType
from typing import Literal, Self

from pmrp.storage.errors import UnitOfWorkStateError
from pmrp.storage.repositories.risk_decisions import RiskDecisionRepository
from pmrp.storage.session import AsyncSessionFactory
from pmrp.storage.transactions import SqlAlchemyUnitOfWork


class SqlAlchemyRiskUnitOfWork:
    """Wire risk repositories into the explicit SQLAlchemy unit of work."""

    def __init__(self, *, session_factory: AsyncSessionFactory) -> None:
        self._unit_of_work = SqlAlchemyUnitOfWork(session_factory=session_factory)
        self._risk_decisions: RiskDecisionRepository | None = None

    async def __aenter__(self) -> Self:
        await self._unit_of_work.__aenter__()
        self._risk_decisions = RiskDecisionRepository(self._unit_of_work.session)
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
            self._risk_decisions = None

    @property
    def risk_decisions(self) -> RiskDecisionRepository:
        """Return the active risk decision repository."""

        if self._risk_decisions is None:
            raise UnitOfWorkStateError("risk unit of work is not active")
        _ = self._unit_of_work.session
        return self._risk_decisions

    async def commit(self) -> None:
        """Commit the active risk transaction."""

        await self._unit_of_work.commit()

    async def rollback(self) -> None:
        """Roll back the active risk transaction."""

        await self._unit_of_work.rollback()
