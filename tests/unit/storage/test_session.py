"""Tests for async session helpers."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from pmrp.storage import PersistenceTimeoutError, session_scope
from pmrp.storage.session import create_session_factory


@pytest.mark.unit
def test_create_session_factory_disables_expiration_and_autoflush() -> None:
    factory = create_session_factory(_FakeEngine())

    assert factory.kw["expire_on_commit"] is False
    assert factory.kw["autoflush"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_scope_closes_session_after_success() -> None:
    session = _FakeSession()

    async with session_scope(lambda: session):
        assert session.closed == 0

    assert session.closed == 1
    assert session.rolled_back == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_scope_rolls_back_and_closes_after_base_exception() -> None:
    session = _FakeSession()

    with pytest.raises(RuntimeError, match="boom"):
        async with session_scope(lambda: session):
            raise RuntimeError("boom")

    assert session.rolled_back == 1
    assert session.closed == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_session_scope_classifies_sqlalchemy_errors_after_rollback() -> None:
    session = _FakeSession()

    with pytest.raises(PersistenceTimeoutError):
        async with session_scope(lambda: session):
            raise SQLAlchemyTimeoutError("pool exhausted")

    assert session.rolled_back == 1
    assert session.closed == 1


class _FakeEngine:
    pass


class _FakeSession:
    def __init__(self) -> None:
        self.rolled_back = 0
        self.closed = 0

    async def rollback(self) -> None:
        self.rolled_back += 1

    async def close(self) -> None:
        self.closed += 1
