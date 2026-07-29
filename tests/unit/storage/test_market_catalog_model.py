"""Tests for canonical market catalog SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import Numeric, Table

from pmrp.storage.models import ContractRow, MarketRow, OutcomeRow, StorageBase


@pytest.mark.unit
def test_market_row_mapping_matches_database_spec() -> None:
    table = MarketRow.__table__

    assert table.schema == "pmrp_market"
    assert table.name == "markets"
    assert [column.name for column in table.primary_key.columns] == ["market_id"]
    assert set(table.columns.keys()) == {
        "market_id",
        "exchange",
        "exchange_market_id",
        "exchange_event_id",
        "title",
        "subtitle",
        "description",
        "category",
        "tags",
        "outcome_type",
        "status",
        "opens_at",
        "closes_at",
        "resolves_at",
        "finalized_at",
        "currency",
        "payout_per_unit",
        "tick_size",
        "quantity_increment",
        "rules_text",
        "rules_url",
        "created_at",
        "updated_at",
        "aggregate_version",
    }


@pytest.mark.unit
def test_market_constraints_and_indexes_match_database_spec() -> None:
    table = MarketRow.__table__

    assert {
        "uq_markets__exchange_exchange_market_id",
        "ck_markets__payout_per_unit",
        "ck_markets__tick_size",
        "ck_markets__quantity_increment",
    } <= {constraint.name for constraint in table.constraints}
    assert {
        "ix_markets__exchange_status",
        "ix_markets__status_closes",
        "ix_markets__updated",
    } <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_outcome_row_mapping_matches_database_spec() -> None:
    table = OutcomeRow.__table__

    assert table.schema == "pmrp_market"
    assert table.name == "outcomes"
    assert [column.name for column in table.primary_key.columns] == ["outcome_id"]
    assert set(table.columns.keys()) == {
        "outcome_id",
        "market_id",
        "exchange_outcome_id",
        "name",
        "normalized_name",
        "outcome_index",
        "is_tradeable",
        "is_winning",
        "payout_per_unit",
        "metadata",
        "created_at",
        "updated_at",
    }
    assert OutcomeRow.metadata_.property.columns[0].name == "metadata"


@pytest.mark.unit
def test_outcome_constraints_and_indexes_match_database_spec() -> None:
    table = OutcomeRow.__table__

    assert {
        "fk_outcomes__market_id__markets",
        "uq_outcomes__market_id_outcome_index",
        "uq_outcomes__market_id_normalized_name",
    } <= {constraint.name for constraint in table.constraints}
    assert {"ix_outcomes__market"} <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_contract_row_mapping_matches_database_spec() -> None:
    table = ContractRow.__table__

    assert table.schema == "pmrp_market"
    assert table.name == "contracts"
    assert [column.name for column in table.primary_key.columns] == ["contract_id"]
    assert set(table.columns.keys()) == {
        "contract_id",
        "market_id",
        "outcome_id",
        "exchange_contract_id",
        "symbol",
        "display_name",
        "tick_size",
        "quantity_increment",
        "min_order_quantity",
        "max_order_quantity",
        "active",
        "created_at",
        "updated_at",
    }


@pytest.mark.unit
def test_contract_constraints_and_indexes_match_database_spec() -> None:
    table = ContractRow.__table__

    assert {
        "fk_contracts__market_id__markets",
        "fk_contracts__outcome_id__outcomes",
        "uq_contracts__market_id_outcome_id",
    } <= {constraint.name for constraint in table.constraints}
    assert {"ix_contracts__market_active"} <= {index.name for index in table.indexes}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (MarketRow.__table__, "payout_per_unit"),
        (MarketRow.__table__, "tick_size"),
        (MarketRow.__table__, "quantity_increment"),
        (OutcomeRow.__table__, "payout_per_unit"),
        (ContractRow.__table__, "tick_size"),
        (ContractRow.__table__, "quantity_increment"),
        (ContractRow.__table__, "min_order_quantity"),
        (ContractRow.__table__, "max_order_quantity"),
    ],
)
def test_market_catalog_numeric_columns_use_exact_database_scale(
    table: Table,
    column_name: str,
) -> None:
    column = table.columns[column_name]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_market_catalog_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_market.markets"] is MarketRow.__table__
    assert StorageBase.metadata.tables["pmrp_market.outcomes"] is OutcomeRow.__table__
    assert StorageBase.metadata.tables["pmrp_market.contracts"] is ContractRow.__table__
