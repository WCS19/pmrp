"""Helpers shared by Alembic migration bootstrap code."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import SecretStr

from pmrp.storage.config import DatabaseConfig

DEFAULT_MIGRATION_APPLICATION_NAME = "pmrp-migrator"

_ENV_DATABASE_URL = "PMRP_DATABASE_URL"
_ENV_APPLICATION_NAME = "PMRP_DATABASE_APPLICATION_NAME"
_ENV_CONNECT_TIMEOUT_SECONDS = "PMRP_DATABASE_CONNECT_TIMEOUT_SECONDS"
_ENV_STATEMENT_TIMEOUT_MILLISECONDS = "PMRP_DATABASE_STATEMENT_TIMEOUT_MILLISECONDS"
_ENV_LOCK_TIMEOUT_MILLISECONDS = "PMRP_DATABASE_LOCK_TIMEOUT_MILLISECONDS"
_ENV_IDLE_IN_TRANSACTION_TIMEOUT_MILLISECONDS = (
    "PMRP_DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MILLISECONDS"
)
_ENV_REQUIRE_TLS = "PMRP_DATABASE_REQUIRE_TLS"


def database_config_from_environment(
    environment: Mapping[str, str],
    *,
    fallback_url: str | None,
) -> DatabaseConfig:
    """Build hardened migration database config from environment variables."""

    url = environment.get(_ENV_DATABASE_URL) or fallback_url
    if not url:
        msg = "PMRP_DATABASE_URL or alembic sqlalchemy.url is required"
        raise RuntimeError(msg)

    return DatabaseConfig(
        url=SecretStr(url),
        application_name=environment.get(
            _ENV_APPLICATION_NAME,
            DEFAULT_MIGRATION_APPLICATION_NAME,
        ),
        connect_timeout_seconds=_positive_int(
            environment,
            _ENV_CONNECT_TIMEOUT_SECONDS,
            default=10,
        ),
        statement_timeout_milliseconds=_positive_int(
            environment,
            _ENV_STATEMENT_TIMEOUT_MILLISECONDS,
            default=5000,
        ),
        lock_timeout_milliseconds=_positive_int(
            environment,
            _ENV_LOCK_TIMEOUT_MILLISECONDS,
            default=1000,
        ),
        idle_in_transaction_session_timeout_milliseconds=_positive_int(
            environment,
            _ENV_IDLE_IN_TRANSACTION_TIMEOUT_MILLISECONDS,
            default=30000,
        ),
        require_tls=_bool(environment, _ENV_REQUIRE_TLS, default=True),
    )


def alembic_engine_configuration(
    base_configuration: Mapping[str, str],
    database_config: DatabaseConfig,
) -> dict[str, str]:
    """Return Alembic engine configuration with a single explicit database URL."""

    configuration = dict(base_configuration)
    configuration["sqlalchemy.url"] = database_config.sqlalchemy_url
    return configuration


def _positive_int(environment: Mapping[str, str], name: str, *, default: int) -> int:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        msg = f"{name} must be a positive integer"
        raise ValueError(msg) from exc
    if value < 1:
        msg = f"{name} must be a positive integer"
        raise ValueError(msg)
    return value


def _bool(environment: Mapping[str, str], name: str, *, default: bool) -> bool:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    msg = f"{name} must be true or false"
    raise ValueError(msg)
