"""Tests for explicit SQLAlchemy unit-of-work behavior."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from pmrp.storage import PersistenceTimeoutError, SqlAlchemyUnitOfWork, UnitOfWorkStateError


@pytest.mark.unit
def test_unit_of_work_session_property_rejects_inactive_access() -> None:
    unit_of_work = SqlAlchemyUnitOfWork(session_factory=_SessionFactory(_FakeSession()))

    with pytest.raises(UnitOfWorkStateError, match="not active"):
        _ = unit_of_work.session


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unit_of_work_commit_does_not_rollback_on_exit() -> None:
    session = _FakeSession()

    async with SqlAlchemyUnitOfWork(session_factory=_SessionFactory(session)) as unit_of_work:
        assert unit_of_work.session is session
        await unit_of_work.commit()
        with pytest.raises(UnitOfWorkStateError, match="already finished"):
            _ = unit_of_work.session

    assert session.committed == 1
    assert session.rolled_back == 0
    assert session.closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_clean_exit_without_commit() -> None:
    session = _FakeSession()

    async with SqlAlchemyUnitOfWork(session_factory=_SessionFactory(session)) as unit_of_work:
        assert unit_of_work.session is session

    assert session.committed == 0
    assert session.rolled_back == 1
    assert session.closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unit_of_work_rolls_back_exception_and_preserves_error() -> None:
    session = _FakeSession()

    with pytest.raises(RuntimeError, match="boom"):
        async with SqlAlchemyUnitOfWork(session_factory=_SessionFactory(session)):
            raise RuntimeError("boom")

    assert session.rolled_back == 1
    assert session.closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unit_of_work_explicit_rollback_prevents_exit_rollback() -> None:
    session = _FakeSession()

    async with SqlAlchemyUnitOfWork(session_factory=_SessionFactory(session)) as unit_of_work:
        await unit_of_work.rollback()
        with pytest.raises(UnitOfWorkStateError, match="already finished"):
            _ = unit_of_work.session

    assert session.rolled_back == 1
    assert session.closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unit_of_work_rejects_repeated_terminal_operations() -> None:
    session = _FakeSession()

    async with SqlAlchemyUnitOfWork(session_factory=_SessionFactory(session)) as unit_of_work:
        await unit_of_work.commit()
        with pytest.raises(UnitOfWorkStateError, match="already finished"):
            await unit_of_work.commit()
        with pytest.raises(UnitOfWorkStateError, match="already finished"):
            await unit_of_work.rollback()

    assert session.committed == 1
    assert session.rolled_back == 0
    assert session.closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unit_of_work_does_not_rollback_after_terminal_operation_then_error() -> None:
    session = _FakeSession()

    with pytest.raises(RuntimeError, match="post-commit failure"):
        await _commit_then_raise(session)

    assert session.committed == 1
    assert session.rolled_back == 0
    assert session.closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unit_of_work_rejects_nested_entry() -> None:
    session = _FakeSession()
    unit_of_work = SqlAlchemyUnitOfWork(session_factory=_SessionFactory(session))

    async with unit_of_work:
        with pytest.raises(UnitOfWorkStateError, match="already active"):
            await unit_of_work.__aenter__()

    assert session.rolled_back == 1
    assert session.closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unit_of_work_classifies_commit_failure() -> None:
    session = _FakeSession(commit_error=SQLAlchemyTimeoutError("pool exhausted"))

    with pytest.raises(PersistenceTimeoutError):
        async with SqlAlchemyUnitOfWork(session_factory=_SessionFactory(session)) as unit_of_work:
            await unit_of_work.commit()

    assert session.closed == 1


class _SessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self) -> _FakeSession:
        return self._session


async def _commit_then_raise(session: _FakeSession) -> None:
    async with SqlAlchemyUnitOfWork(session_factory=_SessionFactory(session)) as unit_of_work:
        await unit_of_work.commit()
        raise RuntimeError("post-commit failure")


class _FakeSession:
    def __init__(self, *, commit_error: Exception | None = None) -> None:
        self._commit_error = commit_error
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    async def commit(self) -> None:
        if self._commit_error is not None:
            raise self._commit_error
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1

    async def close(self) -> None:
        self.closed += 1
