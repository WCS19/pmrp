"""Tests for storage error classification."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from pmrp.storage import (
    ConcurrencyConflictError,
    DuplicateRecordError,
    InvariantViolationError,
    PersistenceTimeoutError,
    PersistenceUnavailableError,
    StorageError,
    StorageIntegrityError,
    classify_storage_error,
)


@pytest.mark.unit
def test_classify_storage_error_returns_existing_storage_error() -> None:
    error = StorageError("classified", retryable=True, context={"component": "test"})

    assert classify_storage_error(error) is error


@pytest.mark.unit
@pytest.mark.parametrize(
    ("sqlstate", "expected_type", "retryable"),
    [
        ("23505", DuplicateRecordError, False),
        ("23514", InvariantViolationError, False),
        ("40001", ConcurrencyConflictError, True),
        ("40P01", ConcurrencyConflictError, True),
        ("57014", PersistenceTimeoutError, True),
        ("55P03", PersistenceTimeoutError, True),
        ("08006", PersistenceUnavailableError, True),
    ],
)
def test_classify_storage_error_maps_sqlstate(
    sqlstate: str,
    expected_type: type[StorageError],
    retryable: bool,
) -> None:
    error = IntegrityError("statement", {}, _SqlState(sqlstate))

    classified = classify_storage_error(error)

    assert isinstance(classified, expected_type)
    assert classified.retryable is retryable
    assert classified.context == {"sqlstate": sqlstate}


@pytest.mark.unit
def test_classify_storage_error_maps_unknown_integrity_error() -> None:
    error = IntegrityError("statement", {}, _SqlState("23503"))

    classified = classify_storage_error(error)

    assert isinstance(classified, StorageIntegrityError)
    assert classified.retryable is False
    assert classified.context == {"sqlstate": "23503"}


@pytest.mark.unit
def test_classify_storage_error_maps_operational_without_sqlstate_to_unavailable() -> None:
    error = OperationalError("statement", {}, Exception("connection refused"))

    classified = classify_storage_error(error)

    assert isinstance(classified, PersistenceUnavailableError)
    assert classified.retryable is True
    assert classified.context == {}


@pytest.mark.unit
def test_classify_storage_error_maps_pool_timeout_to_timeout() -> None:
    error = SQLAlchemyTimeoutError("pool exhausted")

    classified = classify_storage_error(error)

    assert isinstance(classified, PersistenceTimeoutError)
    assert classified.retryable is True


@pytest.mark.unit
def test_classify_storage_error_maps_generic_dbapi_error() -> None:
    error = DBAPIError("statement", {}, _SqlState("99999"))

    classified = classify_storage_error(error)

    assert type(classified) is StorageError
    assert classified.context == {"sqlstate": "99999"}


@pytest.mark.unit
def test_classify_storage_error_maps_non_database_error_to_safe_storage_error() -> None:
    error = RuntimeError("password=should-not-leak")

    classified = classify_storage_error(error)

    assert type(classified) is StorageError
    assert classified.safe_message == "storage operation failed"
    assert "password" not in str(classified)


class _SqlState:
    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate
