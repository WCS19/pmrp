"""Tests for research strategy and model metadata SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import Numeric

from pmrp.storage.models import (
    ModelArtifactRow,
    StorageBase,
    StrategyConfigurationRow,
    StrategyDefinitionRow,
    StrategyInstanceRow,
)


@pytest.mark.unit
def test_strategy_definition_row_mapping_matches_database_spec() -> None:
    table = StrategyDefinitionRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "strategy_definitions"
    assert [column.name for column in table.primary_key.columns] == [
        "strategy_type",
        "strategy_version",
    ]
    assert set(table.columns.keys()) == {
        "strategy_type",
        "strategy_version",
        "implementation_path",
        "description",
        "configuration_schema_version",
        "subscribed_event_types",
        "supports_replay",
        "supports_simulation",
        "supports_paper",
        "supports_shadow",
        "supports_live",
        "created_at",
    }


@pytest.mark.unit
def test_strategy_instance_row_mapping_matches_database_spec() -> None:
    table = StrategyInstanceRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "strategy_instances"
    assert [column.name for column in table.primary_key.columns] == ["strategy_id"]
    assert set(table.columns.keys()) == {
        "strategy_id",
        "strategy_type",
        "strategy_version",
        "name",
        "environment",
        "state",
        "configuration_version",
        "configuration_hash",
        "capital_allocation_amount",
        "capital_allocation_currency",
        "health_status",
        "health_message",
        "created_at",
        "started_at",
        "stopped_at",
        "updated_at",
        "aggregate_version",
    }


@pytest.mark.unit
def test_strategy_instance_constraints_and_indexes_match_database_spec() -> None:
    table = StrategyInstanceRow.__table__

    assert {"fk_strategy_instances__strategy_type_strategy_version__strategy_definitions"} <= {
        constraint.name for constraint in table.constraints
    }
    assert {"ix_strategy_instances__state_health"} <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_strategy_configuration_row_mapping_matches_database_spec() -> None:
    table = StrategyConfigurationRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "strategy_configurations"
    assert [column.name for column in table.primary_key.columns] == [
        "strategy_id",
        "configuration_version",
    ]
    assert set(table.columns.keys()) == {
        "strategy_id",
        "configuration_version",
        "effective_at",
        "configuration",
        "configuration_hash",
        "created_by",
        "approved_by",
        "approval_required",
        "created_at",
    }


@pytest.mark.unit
def test_strategy_configuration_constraints_match_database_spec() -> None:
    table = StrategyConfigurationRow.__table__

    assert {
        "fk_strategy_configurations__strategy_id__strategy_instances",
        "uq_strategy_configurations__strategy_id_configuration_hash",
    } <= {constraint.name for constraint in table.constraints}


@pytest.mark.unit
def test_model_artifact_row_mapping_matches_database_spec() -> None:
    table = ModelArtifactRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "model_artifacts"
    assert [column.name for column in table.primary_key.columns] == [
        "model_id",
        "model_version",
    ]
    assert set(table.columns.keys()) == {
        "model_id",
        "model_version",
        "model_name",
        "artifact_uri",
        "artifact_checksum",
        "training_dataset_id",
        "training_dataset_checksum",
        "training_code_commit",
        "dependency_lock_hash",
        "feature_schema_version",
        "target_definition",
        "trained_at",
        "random_seed",
        "evaluation_metrics",
        "calibration_method",
        "approval_status",
        "approved_by",
        "approved_at",
        "created_at",
    }


@pytest.mark.unit
def test_model_artifact_indexes_match_database_spec() -> None:
    assert {"ix_model_artifacts__approval"} <= {
        index.name for index in ModelArtifactRow.__table__.indexes
    }


@pytest.mark.unit
def test_strategy_instance_capital_allocation_uses_exact_database_scale() -> None:
    column = StrategyInstanceRow.__table__.columns["capital_allocation_amount"]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_research_metadata_rows_are_registered_in_storage_metadata() -> None:
    assert (
        StorageBase.metadata.tables["pmrp_research.strategy_definitions"]
        is StrategyDefinitionRow.__table__
    )
    assert (
        StorageBase.metadata.tables["pmrp_research.strategy_instances"]
        is StrategyInstanceRow.__table__
    )
    assert (
        StorageBase.metadata.tables["pmrp_research.strategy_configurations"]
        is StrategyConfigurationRow.__table__
    )
    assert (
        StorageBase.metadata.tables["pmrp_research.model_artifacts"] is ModelArtifactRow.__table__
    )
