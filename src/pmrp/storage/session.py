"""Async session factory helpers for storage code."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from pmrp.storage.errors import classify_storage_error

AsyncSessionFactory = Callable[[], AsyncSession]


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a process-level async session factory without hidden commits."""

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def session_scope(session_factory: AsyncSessionFactory) -> AsyncIterator[AsyncSession]:
    """Yield a session and roll back unhandled failures before closing it."""

    session = session_factory()
    try:
        yield session
    except SQLAlchemyError as exc:
        await session.rollback()
        raise classify_storage_error(exc) from exc
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()
