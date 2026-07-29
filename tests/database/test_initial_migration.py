"""Database integration tests for the initial Alembic migration."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
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


def test_migrations_upgrade_downgrade_and_reupgrade_empty_database() -> None:
    _require_database_url()
    alembic_config = _alembic_config()

    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    assert asyncio.run(_migration_state()) == (
        "0002_create_schema_registry",
        LOGICAL_SCHEMAS,
        True,
    )
    assert asyncio.run(_schema_registry_state()) == (
        True,
        ("schema_name", "schema_version"),
        ("ix_schema_registry__category",),
        (),
        (),
    )
    asyncio.run(_assert_schema_registry_version_constraint())

    command.downgrade(alembic_config, "base")
    assert asyncio.run(_schemas()) == ()

    command.upgrade(alembic_config, "head")
    assert asyncio.run(_migration_state()) == (
        "0002_create_schema_registry",
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


async def _schema_registry_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[int, ...],
    tuple[str, ...],
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            table_exists = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM information_schema.tables
                                WHERE table_schema = 'pmrp_core'
                                  AND table_name = 'schema_registry'
                            )
                            """
                        )
                    )
                ).scalar_one()
            )
            primary_key_columns = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT a.attname
                        FROM pg_index i
                        JOIN pg_attribute a
                          ON a.attrelid = i.indrelid
                         AND a.attnum = ANY(i.indkey)
                        WHERE i.indrelid = 'pmrp_core.schema_registry'::regclass
                          AND i.indisprimary
                        ORDER BY array_position(i.indkey, a.attnum)
                        """
                    )
                )
            )
            index_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'pmrp_core'
                          AND tablename = 'schema_registry'
                          AND indexname = 'ix_schema_registry__category'
                        ORDER BY indexname
                        """
                    )
                )
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_core.schema_registry (
                        schema_name,
                        schema_version,
                        schema_category,
                        python_model_path,
                        introduced_in_platform_version
                    )
                    VALUES (
                        'money',
                        1,
                        'value_object',
                        'pmrp.schemas.numeric.Money',
                        '0.1.0'
                    )
                    """
                )
            )
            inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT backward_compatible_with, upcaster_paths
                        FROM pmrp_core.schema_registry
                        WHERE schema_name = 'money'
                          AND schema_version = 1
                        """
                    )
                )
            ).one()
            return (
                table_exists,
                primary_key_columns,
                index_names,
                tuple(inserted[0]),
                tuple(inserted[1]),
            )
    finally:
        await engine.dispose()


async def _assert_schema_registry_version_constraint() -> None:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO pmrp_core.schema_registry (
                                schema_name,
                                schema_version,
                                schema_category,
                                python_model_path,
                                introduced_in_platform_version
                            )
                            VALUES (
                                'invalid',
                                0,
                                'domain',
                                'pmrp.schemas.markets.Market',
                                '0.1.0'
                            )
                            """
                        )
                    )
            finally:
                await transaction.rollback()
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
