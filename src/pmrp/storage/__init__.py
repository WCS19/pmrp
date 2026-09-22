"""Storage infrastructure for PostgreSQL-backed PMRP persistence."""

from pmrp.storage.config import DatabaseConfig
from pmrp.storage.database import DatabaseHealth, check_database_health, create_database_engine
from pmrp.storage.errors import (
    ConcurrencyConflictError,
    DuplicateRecordError,
    InvariantViolationError,
    PersistenceTimeoutError,
    PersistenceUnavailableError,
    StorageError,
    StorageIntegrityError,
    UnitOfWorkStateError,
    classify_storage_error,
)
from pmrp.storage.migrations import (
    alembic_engine_configuration,
    alembic_engine_options,
    database_config_from_environment,
)
from pmrp.storage.repositories import SqlAlchemyRiskUnitOfWork
from pmrp.storage.session import AsyncSessionFactory, create_session_factory, session_scope
from pmrp.storage.transactions import SqlAlchemyUnitOfWork

__all__ = [
    "AsyncSessionFactory",
    "ConcurrencyConflictError",
    "DatabaseConfig",
    "DatabaseHealth",
    "DuplicateRecordError",
    "InvariantViolationError",
    "PersistenceTimeoutError",
    "PersistenceUnavailableError",
    "SqlAlchemyRiskUnitOfWork",
    "SqlAlchemyUnitOfWork",
    "StorageError",
    "StorageIntegrityError",
    "UnitOfWorkStateError",
    "alembic_engine_configuration",
    "alembic_engine_options",
    "check_database_health",
    "classify_storage_error",
    "create_database_engine",
    "create_session_factory",
    "database_config_from_environment",
    "session_scope",
]
