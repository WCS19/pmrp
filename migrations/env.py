"""Alembic environment for PMRP PostgreSQL migrations."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from pmrp.storage.config import DatabaseConfig
from pmrp.storage.migrations import (
    alembic_engine_configuration,
    alembic_engine_options,
    database_config_from_environment,
)
from pmrp.storage.models import StorageBase

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = StorageBase.metadata


def _database_config() -> DatabaseConfig:
    return database_config_from_environment(
        os.environ,
        fallback_url=config.get_main_option("sqlalchemy.url"),
    )


def run_migrations_offline() -> None:
    """Run migrations without creating an Engine."""

    database_config = _database_config()
    context.configure(
        url=database_config.sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations for an existing connection."""

    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine only for the migration invocation."""

    database_config = _database_config()
    configuration = alembic_engine_configuration(
        config.get_section(config.config_ini_section, {}),
        database_config,
    )
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        **alembic_engine_options(database_config),
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in online mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
