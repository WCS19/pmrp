"""Tests for committed Alembic migration scripts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.schema import CreateSchema, DropSchema

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INITIAL_MIGRATION_PATH = REPOSITORY_ROOT / "migrations/versions/0001_create_logical_schemas.py"
SCHEMA_REGISTRY_MIGRATION_PATH = (
    REPOSITORY_ROOT / "migrations/versions/0002_create_schema_registry.py"
)
EXPECTED_LOGICAL_SCHEMAS = (
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


@pytest.mark.unit
def test_initial_migration_revision_metadata_is_stable() -> None:
    migration = _load_initial_migration()

    assert migration.revision == "0001_create_logical_schemas"
    assert migration.down_revision is None
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_schema_registry_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(SCHEMA_REGISTRY_MIGRATION_PATH)

    assert migration.revision == "0002_create_schema_registry"
    assert migration.down_revision == "0001_create_logical_schemas"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_initial_migration_declares_expected_logical_schemas() -> None:
    migration = _load_initial_migration()

    assert migration.LOGICAL_SCHEMAS == EXPECTED_LOGICAL_SCHEMAS


@pytest.mark.unit
def test_initial_migration_upgrade_creates_extension_before_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_initial_migration()
    executed: list[object] = []

    monkeypatch.setattr(migration.op, "execute", executed.append)

    migration.upgrade()

    assert executed[0] == "CREATE EXTENSION IF NOT EXISTS pgcrypto"
    assert all(isinstance(statement, CreateSchema) for statement in executed[1:])
    create_schema_statements = [cast(CreateSchema, statement) for statement in executed[1:]]
    assert [
        (statement.element, statement.if_not_exists) for statement in create_schema_statements
    ] == [(schema_name, True) for schema_name in EXPECTED_LOGICAL_SCHEMAS]


@pytest.mark.unit
def test_initial_migration_downgrade_drops_schemas_in_reverse_without_cascade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_initial_migration()
    executed: list[object] = []

    monkeypatch.setattr(migration.op, "execute", executed.append)

    migration.downgrade()

    assert all(isinstance(statement, DropSchema) for statement in executed)
    drop_schema_statements = [cast(DropSchema, statement) for statement in executed]
    assert [(statement.element, statement.if_exists) for statement in drop_schema_statements] == [
        (schema_name, True) for schema_name in reversed(EXPECTED_LOGICAL_SCHEMAS)
    ]
    assert "DROP EXTENSION IF EXISTS pgcrypto" not in executed


@pytest.mark.unit
def test_schema_registry_migration_uses_expected_names() -> None:
    migration = _load_migration(SCHEMA_REGISTRY_MIGRATION_PATH)

    assert migration.SCHEMA_NAME == "pmrp_core"
    assert migration.TABLE_NAME == "schema_registry"
    assert migration.CATEGORY_INDEX_NAME == "ix_schema_registry__category"


@pytest.mark.unit
def test_schema_registry_migration_marks_check_constraint_name_as_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(SCHEMA_REGISTRY_MIGRATION_PATH)
    formatted_names: list[str] = []
    created_table_arguments: list[object] = []

    def fake_format_name(name: str) -> str:
        formatted_names.append(name)
        return f"final:{name}"

    def fake_create_table(*arguments: object, **_kwargs: object) -> None:
        created_table_arguments.extend(arguments)

    monkeypatch.setattr(migration.op, "f", fake_format_name)
    monkeypatch.setattr(migration.op, "create_table", fake_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)

    migration.upgrade()

    check_constraints = [
        argument for argument in created_table_arguments if isinstance(argument, CheckConstraint)
    ]
    assert formatted_names == ["ck_schema_registry__schema_version"]
    assert [constraint.name for constraint in check_constraints] == [
        "final:ck_schema_registry__schema_version"
    ]


def _load_initial_migration() -> ModuleType:
    return _load_migration(INITIAL_MIGRATION_PATH)


def _load_migration(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        path.stem,
        path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        msg = f"could not load Alembic migration: {path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
