"""Storage exception hierarchy and SQLAlchemy error classification."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError


class StorageError(Exception):
    """Base class for persistence failures with safe structured context."""

    def __init__(
        self,
        safe_message: str,
        *,
        retryable: bool = False,
        context: Mapping[str, str] | None = None,
    ) -> None:
        self.safe_message = safe_message
        self.retryable = retryable
        self.context = MappingProxyType(dict(context or {}))
        super().__init__(safe_message)


class DuplicateRecordError(StorageError):
    """Raised when a uniqueness claim finds an existing durable record."""


class StorageIntegrityError(StorageError):
    """Raised for database integrity failures that are not more specific."""


class InvariantViolationError(StorageError):
    """Raised when a database check constraint rejects invalid state."""


class ConcurrencyConflictError(StorageError):
    """Raised for optimistic-concurrency, serialization, or deadlock conflicts."""


class PersistenceUnavailableError(StorageError):
    """Raised when the database cannot be reached or the connection is broken."""


class PersistenceTimeoutError(StorageError):
    """Raised when the database or connection pool times out."""


class UnitOfWorkStateError(StorageError):
    """Raised when unit-of-work lifecycle methods are used incorrectly."""


_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"
_CHECK_VIOLATION = "23514"
_SERIALIZATION_FAILURE = "40001"
_DEADLOCK_DETECTED = "40P01"
_STATEMENT_TIMEOUT = "57014"


def classify_storage_error(error: BaseException) -> StorageError:
    """Map SQLAlchemy/database failures into PMRP storage errors."""

    if isinstance(error, StorageError):
        return error

    if isinstance(error, SQLAlchemyTimeoutError):
        return PersistenceTimeoutError("database operation timed out", retryable=True)

    sqlstate = _sqlstate(error)
    context = _sqlstate_context(sqlstate)

    if sqlstate == _UNIQUE_VIOLATION:
        return DuplicateRecordError(
            "database record already exists",
            retryable=False,
            context=context,
        )
    if sqlstate == _CHECK_VIOLATION:
        return InvariantViolationError(
            "database invariant violation",
            retryable=False,
            context=context,
        )
    if sqlstate == _FOREIGN_KEY_VIOLATION:
        return StorageIntegrityError(
            "database integrity violation",
            retryable=False,
            context=context,
        )
    if sqlstate in {_SERIALIZATION_FAILURE, _DEADLOCK_DETECTED}:
        return ConcurrencyConflictError(
            "database concurrency conflict",
            retryable=True,
            context=context,
        )
    if sqlstate == _STATEMENT_TIMEOUT:
        return PersistenceTimeoutError(
            "database statement timed out",
            retryable=True,
            context=context,
        )
    if sqlstate is not None and sqlstate.startswith("08"):
        return PersistenceUnavailableError(
            "database connection failure",
            retryable=True,
            context=context,
        )
    if isinstance(error, OperationalError):
        return PersistenceUnavailableError(
            "database is unavailable",
            retryable=True,
            context=context,
        )
    if isinstance(error, IntegrityError):
        return StorageIntegrityError(
            "database integrity violation",
            retryable=False,
            context=context,
        )
    if isinstance(error, DBAPIError):
        return StorageError(
            "database operation failed",
            retryable=False,
            context=context,
        )
    return StorageError("storage operation failed", retryable=False)


def _sqlstate(error: BaseException) -> str | None:
    if not isinstance(error, DBAPIError):
        return None

    original: object = error.orig
    sqlstate = getattr(original, "sqlstate", None)
    if sqlstate is None:
        sqlstate = getattr(original, "pgcode", None)
    if isinstance(sqlstate, str):
        return sqlstate
    return None


def _sqlstate_context(sqlstate: str | None) -> Mapping[str, str]:
    if sqlstate is None:
        return {}
    return {"sqlstate": sqlstate}
