"""Tests for storage database configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pmrp.storage import DatabaseConfig


@pytest.mark.unit
def test_database_config_accepts_asyncpg_url() -> None:
    config = DatabaseConfig(url="postgresql+asyncpg://user:password@localhost/pmrp")

    assert config.sqlalchemy_url == "postgresql+asyncpg://user:password@localhost/pmrp"
    assert config.max_overflow == 4


@pytest.mark.unit
def test_database_config_redacts_url_in_repr() -> None:
    config = DatabaseConfig(url="postgresql+asyncpg://user:password@localhost/pmrp")

    representation = repr(config)

    assert "password" not in representation
    assert "**********" in representation


@pytest.mark.unit
def test_database_config_rejects_non_asyncpg_url() -> None:
    with pytest.raises(ValidationError, match="postgresql\\+asyncpg"):
        DatabaseConfig(url="postgresql://user:password@localhost/pmrp")


@pytest.mark.unit
def test_database_config_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DatabaseConfig(
            url="postgresql+asyncpg://user:password@localhost/pmrp",
            unexpected_field="not allowed",
        )


@pytest.mark.unit
def test_database_config_rejects_implicit_integer_coercion() -> None:
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        DatabaseConfig(
            url="postgresql+asyncpg://user:password@localhost/pmrp",
            pool_max_size="5",
        )


@pytest.mark.unit
def test_database_config_rejects_pool_min_above_max() -> None:
    with pytest.raises(ValidationError, match="pool_min_size"):
        DatabaseConfig(
            url="postgresql+asyncpg://user:password@localhost/pmrp",
            pool_min_size=6,
            pool_max_size=5,
        )


@pytest.mark.unit
def test_database_config_rejects_unsafe_application_name() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        DatabaseConfig(
            url="postgresql+asyncpg://user:password@localhost/pmrp",
            application_name="pmrp app",
        )


@pytest.mark.unit
def test_database_config_connect_args_include_timeouts_and_tls() -> None:
    config = DatabaseConfig(
        url="postgresql+asyncpg://user:password@localhost/pmrp",
        application_name="pmrp-test",
        connect_timeout_seconds=3,
        statement_timeout_milliseconds=200,
        lock_timeout_milliseconds=100,
        idle_in_transaction_session_timeout_milliseconds=500,
        require_tls=True,
    )

    args = config.connect_args

    assert args["timeout"] == 3
    assert args["ssl"] is True
    assert args["server_settings"] == {
        "application_name": "pmrp-test",
        "timezone": "UTC",
        "statement_timeout": "200ms",
        "lock_timeout": "100ms",
        "idle_in_transaction_session_timeout": "500ms",
    }


@pytest.mark.unit
def test_database_config_can_disable_tls_for_isolated_local_infrastructure() -> None:
    config = DatabaseConfig(
        url="postgresql+asyncpg://user:password@localhost/pmrp",
        require_tls=False,
    )

    assert "ssl" not in config.connect_args
