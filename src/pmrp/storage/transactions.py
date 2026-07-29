"""Explicit unit-of-work transaction helper for SQLAlchemy storage sessions."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.storage.errors import UnitOfWorkStateError, classify_storage_error
from pmrp.storage.session import AsyncSessionFactory


class SqlAlchemyUnitOfWork:
    """Own an async session lifecycle and require explicit commits."""

    def __init__(self, *, session_factory: AsyncSessionFactory) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._finished = False

    async def __aenter__(self) -> Self:
        if self._session is not None:
            raise UnitOfWorkStateError("unit of work is already active")
        self._session = self._session_factory()
        self._finished = False
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc, traceback
        session = self._session
        if session is None:
            return False

        try:
            if exc_type is None and self._finished:
                return False
            await self._rollback_on_exit(preserve_existing_error=exc_type is not None)
            return False
        finally:
            await session.close()
            self._session = None
            self._finished = False

    @property
    def session(self) -> AsyncSession:
        """Return the active session for repository construction."""

        if self._session is None:
            raise UnitOfWorkStateError("unit of work is not active")
        return self._session

    async def commit(self) -> None:
        """Commit the active transaction exactly when the use case decides."""

        session = self.session
        try:
            await session.commit()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc
        self._finished = True

    async def rollback(self) -> None:
        """Roll back the active transaction explicitly."""

        session = self.session
        try:
            await session.rollback()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc
        self._finished = True

    async def _rollback_on_exit(self, *, preserve_existing_error: bool) -> None:
        session = self.session
        try:
            await session.rollback()
        except SQLAlchemyError as exc:
            if not preserve_existing_error:
                raise classify_storage_error(exc) from exc
