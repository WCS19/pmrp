"""Tests for matching SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint, Numeric
from sqlalchemy.dialects.postgresql import JSONB

from pmrp.storage.models import MarketRelationshipRow, StorageBase


@pytest.mark.unit
def test_market_relationship_row_mapping_matches_database_spec() -> None:
    table = MarketRelationshipRow.__table__

    assert table.schema == "pmrp_research"
    assert table.name == "market_relationships"
    assert [column.name for column in table.primary_key.columns] == ["relationship_id"]
    assert set(table.columns.keys()) == {
        "relationship_id",
        "source_market_id",
        "target_market_id",
        "relationship_type",
        "confidence",
        "valid_from",
        "valid_until",
        "evidence",
        "validator_version",
        "settlement_rule_match",
        "human_review_status",
        "created_at",
        "updated_at",
        "aggregate_version",
    }


@pytest.mark.unit
def test_market_relationship_constraints_and_indexes_match_database_spec() -> None:
    table = MarketRelationshipRow.__table__
    source_target_index = next(
        index for index in table.indexes if index.name == "ix_market_relationships__source_target"
    )
    confidence_check = next(
        constraint for constraint in table.constraints if isinstance(constraint, CheckConstraint)
    )

    assert {"uq_market_relationships__source_target_type"} <= {
        constraint.name for constraint in table.constraints
    }
    assert confidence_check.name == "ck_market_relationships__confidence"
    assert str(confidence_check.sqltext) == "confidence >= 0 AND confidence <= 1"
    assert [column.name for column in source_target_index.columns] == [
        "source_market_id",
        "target_market_id",
    ]


@pytest.mark.unit
def test_market_relationship_evidence_uses_jsonb() -> None:
    assert isinstance(MarketRelationshipRow.__table__.columns["evidence"].type, JSONB)


@pytest.mark.unit
def test_market_relationship_confidence_uses_exact_database_scale() -> None:
    column = MarketRelationshipRow.__table__.columns["confidence"]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_market_relationship_default_version_matches_database_spec() -> None:
    column = MarketRelationshipRow.__table__.columns["aggregate_version"]

    assert str(column.server_default.arg) == "0"


@pytest.mark.unit
def test_market_relationship_row_is_registered_in_storage_metadata() -> None:
    assert (
        StorageBase.metadata.tables["pmrp_research.market_relationships"]
        is MarketRelationshipRow.__table__
    )
