"""Tests for Alembic migration bootstrap helpers."""

from __future__ import annotations

import pytest

from pmrp.storage import (
    alembic_engine_configuration,
    alembic_engine_options,
    database_config_from_environment,
)


@pytest.mark.unit
def test_database_config_from_environment_uses_hardened_migration_defaults() -> None:
    config = database_config_from_environment(
        {},
        fallback_url="postgresql+asyncpg://user:password@localhost/pmrp",
    )

    assert config.application_name == "pmrp-migrator"
    assert config.connect_args == {
        "timeout": 10,
        "server_settings": {
            "application_name": "pmrp-migrator",
            "timezone": "UTC",
            "statement_timeout": "5000ms",
            "lock_timeout": "1000ms",
            "idle_in_transaction_session_timeout": "30000ms",
        },
        "ssl": True,
    }


@pytest.mark.unit
def test_database_config_from_environment_prefers_environment_url() -> None:
    config = database_config_from_environment(
        {
            "PMRP_DATABASE_URL": "postgresql+asyncpg://env-user:env-pass@localhost/env",
        },
        fallback_url="postgresql+asyncpg://fallback-user:fallback-pass@localhost/fallback",
    )

    assert config.sqlalchemy_url == "postgresql+asyncpg://env-user:env-pass@localhost/env"


@pytest.mark.unit
def test_database_config_from_environment_applies_timeout_overrides() -> None:
    config = database_config_from_environment(
        {
            "PMRP_DATABASE_APPLICATION_NAME": "pmrp-test-migrator",
            "PMRP_DATABASE_CONNECT_TIMEOUT_SECONDS": "4",
            "PMRP_DATABASE_STATEMENT_TIMEOUT_MILLISECONDS": "800",
            "PMRP_DATABASE_LOCK_TIMEOUT_MILLISECONDS": "200",
            "PMRP_DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MILLISECONDS": "1200",
            "PMRP_DATABASE_REQUIRE_TLS": "false",
        },
        fallback_url="postgresql+asyncpg://user:password@localhost/pmrp",
    )

    assert config.connect_args == {
        "timeout": 4,
        "server_settings": {
            "application_name": "pmrp-test-migrator",
            "timezone": "UTC",
            "statement_timeout": "800ms",
            "lock_timeout": "200ms",
            "idle_in_transaction_session_timeout": "1200ms",
        },
    }


@pytest.mark.unit
def test_database_config_from_environment_rejects_missing_url() -> None:
    with pytest.raises(RuntimeError, match="PMRP_DATABASE_URL"):
        database_config_from_environment({}, fallback_url=None)


@pytest.mark.unit
def test_database_config_from_environment_rejects_invalid_integer_override() -> None:
    with pytest.raises(ValueError, match="PMRP_DATABASE_CONNECT_TIMEOUT_SECONDS"):
        database_config_from_environment(
            {"PMRP_DATABASE_CONNECT_TIMEOUT_SECONDS": "0"},
            fallback_url="postgresql+asyncpg://user:password@localhost/pmrp",
        )


@pytest.mark.unit
def test_database_config_from_environment_rejects_invalid_bool_override() -> None:
    with pytest.raises(ValueError, match="PMRP_DATABASE_REQUIRE_TLS"):
        database_config_from_environment(
            {"PMRP_DATABASE_REQUIRE_TLS": "maybe"},
            fallback_url="postgresql+asyncpg://user:password@localhost/pmrp",
        )


@pytest.mark.unit
def test_alembic_engine_configuration_preserves_existing_configuration() -> None:
    config = database_config_from_environment(
        {},
        fallback_url="postgresql+asyncpg://user:password@localhost/pmrp",
    )

    engine_config = alembic_engine_configuration(
        {"script_location": "migrations", "sqlalchemy.echo": "false"},
        config,
    )

    assert engine_config == {
        "script_location": "migrations",
        "sqlalchemy.echo": "false",
        "sqlalchemy.url": "postgresql+asyncpg://user:password@localhost/pmrp",
    }


@pytest.mark.unit
def test_alembic_engine_options_hide_parameters_and_reuse_hardened_connect_args() -> None:
    config = database_config_from_environment(
        {},
        fallback_url="postgresql+asyncpg://user:password@localhost/pmrp",
    )

    options = alembic_engine_options(config)

    assert options == {
        "connect_args": config.connect_args,
        "hide_parameters": True,
    }
