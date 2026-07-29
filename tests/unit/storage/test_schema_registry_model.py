"""Tests for the schema registry SQLAlchemy row model."""

from __future__ import annotations

import pytest

from pmrp.storage.models import SchemaRegistryRow, StorageBase


@pytest.mark.unit
def test_schema_registry_row_mapping_matches_database_spec() -> None:
    table = SchemaRegistryRow.__table__

    assert table.schema == "pmrp_core"
    assert table.name == "schema_registry"
    assert [column.name for column in table.primary_key.columns] == [
        "schema_name",
        "schema_version",
    ]
    assert set(table.columns.keys()) == {
        "schema_name",
        "schema_version",
        "schema_category",
        "python_model_path",
        "json_schema_uri",
        "introduced_in_platform_version",
        "deprecated_in_platform_version",
        "backward_compatible_with",
        "upcaster_paths",
        "created_at",
    }


@pytest.mark.unit
def test_schema_registry_row_constraints_and_indexes_match_database_spec() -> None:
    table = SchemaRegistryRow.__table__

    assert "ck_schema_registry__schema_version" in {
        constraint.name for constraint in table.constraints
    }
    assert "ix_schema_registry__category" in {index.name for index in table.indexes}


@pytest.mark.unit
def test_schema_registry_row_is_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_core.schema_registry"] is SchemaRegistryRow.__table__
