"""Database configuration used by storage infrastructure."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class DatabaseConfig(BaseModel):
    """Strict database connection and timeout configuration.

    The database URL is secret-bearing configuration. It is accepted explicitly,
    stored as ``SecretStr``, and exposed only through ``sqlalchemy_url`` for the
    narrow engine-construction boundary.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
        strict=True,
        validate_default=True,
    )

    url: SecretStr
    application_name: str = Field(
        default="pmrp-app",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    pool_min_size: int = Field(default=1, ge=1)
    pool_max_size: int = Field(default=5, ge=1)
    pool_timeout_seconds: int = Field(default=5, ge=1)
    pool_recycle_seconds: int = Field(default=1800, ge=1)
    connect_timeout_seconds: int = Field(default=10, ge=1)
    statement_timeout_milliseconds: int = Field(default=5000, ge=1)
    lock_timeout_milliseconds: int = Field(default=1000, ge=1)
    idle_in_transaction_session_timeout_milliseconds: int = Field(default=30000, ge=1)
    echo_sql: bool = False
    require_tls: bool = True

    @field_validator("url")
    @classmethod
    def _validate_url_scheme(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value()
        if not url.startswith("postgresql+asyncpg://"):
            msg = "database URL must use the postgresql+asyncpg scheme"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_pool_bounds(self) -> Self:
        if self.pool_min_size > self.pool_max_size:
            msg = "pool_min_size must not exceed pool_max_size"
            raise ValueError(msg)
        return self

    @property
    def sqlalchemy_url(self) -> str:
        """Return the secret URL only for the SQLAlchemy engine boundary."""

        return self.url.get_secret_value()

    @property
    def max_overflow(self) -> int:
        """Return SQLAlchemy ``max_overflow`` derived from configured bounds."""

        return self.pool_max_size - self.pool_min_size

    @property
    def connect_args(self) -> dict[str, object]:
        """Return asyncpg connection arguments with explicit timeouts."""

        args: dict[str, object] = {
            "timeout": self.connect_timeout_seconds,
            "server_settings": {
                "application_name": self.application_name,
                "statement_timeout": f"{self.statement_timeout_milliseconds}ms",
                "lock_timeout": f"{self.lock_timeout_milliseconds}ms",
                "idle_in_transaction_session_timeout": (
                    f"{self.idle_in_transaction_session_timeout_milliseconds}ms"
                ),
            },
        }
        if self.require_tls:
            args["ssl"] = True
        return args
