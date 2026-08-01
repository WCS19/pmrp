"""Tests for replay and simulation SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import ForeignKeyConstraint, Numeric, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

from pmrp.storage.models import (
    ReplayResultRow,
    ReplaySessionRow,
    SimulationSessionRow,
    StorageBase,
)


@pytest.mark.unit
def test_replay_session_row_mapping_matches_database_spec() -> None:
    table = ReplaySessionRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "replay_sessions"
    assert [column.name for column in table.primary_key.columns] == ["replay_session_id"]
    assert set(table.columns.keys()) == {
        "replay_session_id",
        "dataset_id",
        "dataset_checksum",
        "starts_at",
        "ends_at",
        "speed",
        "deterministic",
        "random_seed",
        "event_ordering_policy_version",
        "strategy_versions",
        "model_versions",
        "configuration_hash",
        "code_commit",
        "dependency_lock_hash",
        "state",
        "current_time",
        "processed_events",
        "rejected_events",
        "created_at",
        "started_at",
        "completed_at",
        "result_checksum",
        "failure_message",
    }


@pytest.mark.unit
def test_replay_session_defaults_and_indexes_match_database_spec() -> None:
    table = ReplaySessionRow.__table__
    state_created_index = next(
        index for index in table.indexes if index.name == "ix_replay_sessions__state_created"
    )

    assert [state_created_index.expressions[0].name] == ["state"]
    assert str(state_created_index.expressions[1].compile(dialect=postgresql.dialect())) == (
        "created_at DESC"
    )
    assert str(table.columns["processed_events"].server_default.arg) == "0"
    assert str(table.columns["rejected_events"].server_default.arg) == "0"


@pytest.mark.unit
def test_replay_result_row_mapping_matches_database_spec() -> None:
    table = ReplayResultRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "replay_results"
    assert [column.name for column in table.primary_key.columns] == ["replay_session_id"]
    assert set(table.columns.keys()) == {
        "replay_session_id",
        "processed_events",
        "generated_signals",
        "generated_intents",
        "simulated_orders",
        "simulated_fills",
        "final_portfolio",
        "metrics",
        "result_checksum",
        "completed_at",
    }


@pytest.mark.unit
def test_replay_result_foreign_key_matches_database_spec() -> None:
    foreign_key = next(
        constraint
        for constraint in ReplayResultRow.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    )

    assert foreign_key.name == "fk_replay_results__replay_sessions"
    assert [column.name for column in foreign_key.columns] == ["replay_session_id"]
    assert [element.target_fullname for element in foreign_key.elements] == [
        "pmrp_research.replay_sessions.replay_session_id"
    ]


@pytest.mark.unit
def test_simulation_session_row_mapping_matches_database_spec() -> None:
    table = SimulationSessionRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "simulation_sessions"
    assert [column.name for column in table.primary_key.columns] == ["simulation_session_id"]
    assert set(table.columns.keys()) == {
        "simulation_session_id",
        "replay_session_id",
        "configuration",
        "configuration_hash",
        "state",
        "created_at",
        "started_at",
        "completed_at",
        "result_checksum",
    }


@pytest.mark.unit
def test_simulation_session_constraints_and_indexes_match_database_spec() -> None:
    table = SimulationSessionRow.__table__
    state_created_index = next(
        index for index in table.indexes if index.name == "ix_simulation_sessions__state_created"
    )
    foreign_key = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    )

    assert foreign_key.name == "fk_simulation_sessions__replay_sessions"
    assert [column.name for column in foreign_key.columns] == ["replay_session_id"]
    assert [element.target_fullname for element in foreign_key.elements] == [
        "pmrp_research.replay_sessions.replay_session_id"
    ]
    assert [state_created_index.expressions[0].name] == ["state"]
    assert str(state_created_index.expressions[1].compile(dialect=postgresql.dialect())) == (
        "created_at DESC"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (ReplaySessionRow.__table__, "strategy_versions"),
        (ReplaySessionRow.__table__, "model_versions"),
        (ReplayResultRow.__table__, "final_portfolio"),
        (ReplayResultRow.__table__, "metrics"),
        (SimulationSessionRow.__table__, "configuration"),
    ],
)
def test_replay_simulation_json_columns_use_jsonb(table: Table, column_name: str) -> None:
    assert isinstance(table.columns[column_name].type, JSONB)


@pytest.mark.unit
def test_replay_speed_uses_exact_database_scale() -> None:
    column = ReplaySessionRow.__table__.columns["speed"]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_replay_simulation_rows_are_registered_in_storage_metadata() -> None:
    assert (
        StorageBase.metadata.tables["pmrp_research.replay_sessions"] is ReplaySessionRow.__table__
    )
    assert StorageBase.metadata.tables["pmrp_research.replay_results"] is ReplayResultRow.__table__
    assert (
        StorageBase.metadata.tables["pmrp_research.simulation_sessions"]
        is SimulationSessionRow.__table__
    )
