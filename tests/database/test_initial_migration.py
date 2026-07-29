"""Database integration tests for the initial Alembic migration."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from pmrp.storage import create_database_engine, database_config_from_environment

pytestmark = [pytest.mark.database, pytest.mark.integration]

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LOGICAL_SCHEMAS = (
    "pmrp_core",
    "pmrp_raw",
    "pmrp_event",
    "pmrp_market",
    "pmrp_execution",
    "pmrp_portfolio",
    "pmrp_risk",
    "pmrp_research",
    "pmrp_ops",
    "pmrp_audit",
)


def test_initial_migration_upgrades_downgrades_and_reupgrades_empty_database() -> None:
    _require_database_url()
    alembic_config = _alembic_config()

    command.upgrade(alembic_config, "head")
    assert asyncio.run(_migration_state()) == (
        "0001_create_logical_schemas",
        LOGICAL_SCHEMAS,
        True,
    )

    command.downgrade(alembic_config, "base")
    assert asyncio.run(_schemas()) == ()

    command.upgrade(alembic_config, "head")
    assert asyncio.run(_migration_state()) == (
        "0001_create_logical_schemas",
        LOGICAL_SCHEMAS,
        True,
    )


def _require_database_url() -> None:
    if not os.environ.get("PMRP_DATABASE_URL"):
        pytest.skip("PMRP_DATABASE_URL is required for database migration tests")


def _alembic_config() -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    return config


async def _migration_state() -> tuple[str, tuple[str, ...], bool]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            revision = str(
                (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
            )
            extension_exists = bool(
                (
                    await connection.execute(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto')"
                        )
                    )
                ).scalar_one()
            )
            return revision, await _schemas_for_connection(connection), extension_exists
    finally:
        await engine.dispose()


async def _schemas() -> tuple[str, ...]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            return await _schemas_for_connection(connection)
    finally:
        await engine.dispose()


async def _schemas_for_connection(connection: AsyncConnection) -> tuple[str, ...]:
    statement = text(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name IN :schema_names
        ORDER BY schema_name
        """
    ).bindparams(bindparam("schema_names", expanding=True))
    result = await connection.execute(statement, {"schema_names": LOGICAL_SCHEMAS})
    found = {str(row[0]) for row in result}
    return tuple(schema_name for schema_name in LOGICAL_SCHEMAS if schema_name in found)
