"""Async SQLAlchemy engine construction and health checks."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from pmrp.storage.config import DatabaseConfig
from pmrp.storage.errors import classify_storage_error


@dataclass(frozen=True, slots=True)
class DatabaseHealth:
    """Result of a minimal database readiness probe."""

    reachable: bool
    server_version: str
    session_timezone: str
    is_utc: bool


def create_database_engine(config: DatabaseConfig) -> AsyncEngine:
    """Create one async SQLAlchemy engine for a process."""

    return create_async_engine(
        config.sqlalchemy_url,
        echo=config.echo_sql,
        pool_size=config.pool_min_size,
        max_overflow=config.max_overflow,
        pool_timeout=config.pool_timeout_seconds,
        pool_recycle=config.pool_recycle_seconds,
        pool_pre_ping=True,
        connect_args=config.connect_args,
    )


async def check_database_health(engine: AsyncEngine) -> DatabaseHealth:
    """Verify database reachability and UTC session timezone."""

    try:
        async with engine.connect() as connection:
            version_result = await connection.execute(text("SHOW server_version"))
            timezone_result = await connection.execute(text("SHOW TimeZone"))
            server_version = str(version_result.scalar_one())
            session_timezone = str(timezone_result.scalar_one())
    except SQLAlchemyError as exc:
        raise classify_storage_error(exc) from exc

    return DatabaseHealth(
        reachable=True,
        server_version=server_version,
        session_timezone=session_timezone,
        is_utc=session_timezone.upper() == "UTC",
    )
