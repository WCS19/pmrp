"""Tests for canonical order execution SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy import Numeric, Table

from pmrp.storage.models import OrderIntentRow, OrderRow, OrderStateTransitionRow, StorageBase


@pytest.mark.unit
def test_order_intent_row_mapping_matches_database_spec() -> None:
    table = OrderIntentRow.__table__

    assert table.schema == "pmrp_execution"
    assert table.name == "order_intents"
    assert [column.name for column in table.primary_key.columns] == ["intent_id"]
    assert set(table.columns.keys()) == {
        "intent_id",
        "strategy_id",
        "market_id",
        "contract_id",
        "outcome_id",
        "side",
        "quantity",
        "limit_price",
        "order_type",
        "time_in_force",
        "post_only",
        "reduce_only",
        "urgency",
        "created_at",
        "expires_at",
        "signal_ids",
        "correlation_id",
        "idempotency_key",
        "payload_hash",
    }


@pytest.mark.unit
def test_order_intent_constraints_and_indexes_match_database_spec() -> None:
    table = OrderIntentRow.__table__

    assert {
        "ck_order_intents__limit_price",
        "ck_order_intents__quantity",
        "uq_order_intents__strategy_id_idempotency_key",
    } <= {constraint.name for constraint in table.constraints}
    assert {"ix_order_intents__strategy_time"} <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_order_row_mapping_matches_database_spec() -> None:
    table = OrderRow.__table__

    assert table.schema == "pmrp_execution"
    assert table.name == "orders"
    assert [column.name for column in table.primary_key.columns] == ["order_id"]
    assert set(table.columns.keys()) == {
        "order_id",
        "intent_id",
        "strategy_id",
        "risk_decision_id",
        "exchange",
        "account_id",
        "market_id",
        "contract_id",
        "outcome_id",
        "side",
        "quantity",
        "filled_quantity",
        "remaining_quantity",
        "limit_price",
        "average_fill_price",
        "order_type",
        "time_in_force",
        "post_only",
        "reduce_only",
        "status",
        "client_order_id",
        "exchange_order_id",
        "created_at",
        "submitted_at",
        "accepted_at",
        "last_updated_at",
        "expires_at",
        "aggregate_version",
    }


@pytest.mark.unit
def test_order_constraints_and_indexes_match_database_spec() -> None:
    table = OrderRow.__table__

    assert {
        "ck_orders__filled_quantity",
        "ck_orders__fill_balance",
        "ck_orders__quantity",
        "ck_orders__remaining_quantity",
        "uq_orders__exchange_account_client_order_id",
        "uq_orders__exchange_account_exchange_order_id",
    } <= {constraint.name for constraint in table.constraints}
    assert {
        "ix_orders__account_status",
        "ix_orders__active",
        "ix_orders__strategy_created",
    } <= {index.name for index in table.indexes}


@pytest.mark.unit
def test_order_state_transition_row_mapping_matches_database_spec() -> None:
    table = OrderStateTransitionRow.__table__

    assert table.schema == "pmrp_execution"
    assert table.name == "order_state_transitions"
    assert [column.name for column in table.primary_key.columns] == ["transition_id"]
    assert set(table.columns.keys()) == {
        "transition_id",
        "order_id",
        "previous_status",
        "current_status",
        "occurred_at",
        "source_event_id",
        "reason_code",
        "reason_text",
        "aggregate_version_before",
        "aggregate_version_after",
        "created_at",
    }


@pytest.mark.unit
def test_order_state_transition_constraints_and_indexes_match_database_spec() -> None:
    table = OrderStateTransitionRow.__table__

    assert {
        "fk_order_transitions__order_id__orders",
        "uq_order_transitions__order_version",
    } <= {constraint.name for constraint in table.constraints}
    assert {"ix_order_transitions__order_time"} <= {index.name for index in table.indexes}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("table", "column_name"),
    [
        (OrderIntentRow.__table__, "quantity"),
        (OrderIntentRow.__table__, "limit_price"),
        (OrderIntentRow.__table__, "urgency"),
        (OrderRow.__table__, "quantity"),
        (OrderRow.__table__, "filled_quantity"),
        (OrderRow.__table__, "remaining_quantity"),
        (OrderRow.__table__, "limit_price"),
        (OrderRow.__table__, "average_fill_price"),
    ],
)
def test_order_numeric_columns_use_exact_database_scale(table: Table, column_name: str) -> None:
    column = table.columns[column_name]

    assert isinstance(column.type, Numeric)
    assert column.type.precision == 38
    assert column.type.scale == 18


@pytest.mark.unit
def test_order_rows_are_registered_in_storage_metadata() -> None:
    assert StorageBase.metadata.tables["pmrp_execution.order_intents"] is OrderIntentRow.__table__
    assert StorageBase.metadata.tables["pmrp_execution.orders"] is OrderRow.__table__
    assert (
        StorageBase.metadata.tables["pmrp_execution.order_state_transitions"]
        is OrderStateTransitionRow.__table__
    )
