"""Tests for exchange registry SQLAlchemy row models."""

from __future__ import annotations

import pytest

from pmrp.storage.models import ExchangeAccountRow, ExchangeRow, StorageBase


@pytest.mark.unit
def test_exchange_row_mapping_matches_database_spec() -> None:
    table = ExchangeRow.__table__

    assert table.schema == "pmrp_core"
    assert table.name == "exchanges"
    assert [column.name for column in table.primary_key.columns] == ["exchange"]
    assert set(table.columns.keys()) == {
        "exchange",
        "display_name",
        "enabled",
        "capabilities",
        "created_at",
        "updated_at",
    }


@pytest.mark.unit
def test_exchange_account_row_mapping_matches_database_spec() -> None:
    table = ExchangeAccountRow.__table__

    assert table.schema == "pmrp_core"
    assert table.name == "exchange_accounts"
    assert [column.name for column in table.primary_key.columns] == ["account_id"]
    assert set(table.columns.keys()) == {
        "account_id",
        "exchange",
        "environment",
        "external_account_id",
        "enabled",
        "metadata",
        "created_at",
        "updated_at",
    }
    assert ExchangeAccountRow.metadata_.name == "metadata"


@pytest.mark.unit
def test_exchange_account_constraints_and_indexes_match_database_spec() -> None:
    table = ExchangeAccountRow.__table__

    assert "ix_exchange_accounts__exchange_environment" in {index.name for index in table.indexes}
    assert "fk_exchange_accounts__exchange__exchanges" in {
        constraint.name for constraint in table.foreign_key_constraints
    }


@pytest.mark.unit
def test_exchange_registry_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_core.exchanges"] is ExchangeRow.__table__
    assert (
        StorageBase.metadata.tables["pmrp_core.exchange_accounts"] is ExchangeAccountRow.__table__
    )
