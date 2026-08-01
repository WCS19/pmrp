"""Tests for health and audit SQLAlchemy row models."""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from pmrp.storage.models import (
    AdapterHealthSnapshotRow,
    OperatorAuditRecordRow,
    StorageBase,
)


@pytest.mark.unit
def test_adapter_health_snapshot_row_mapping_matches_database_spec() -> None:
    table = AdapterHealthSnapshotRow.__table__

    assert table.schema == "pmrp_ops"
    assert table.name == "adapter_health_snapshots"
    assert [column.name for column in table.primary_key.columns] == [
        "captured_at",
        "exchange",
        "environment",
    ]
    assert set(table.columns.keys()) == {
        "captured_at",
        "exchange",
        "environment",
        "status",
        "connected",
        "authenticated",
        "subscriptions_active",
        "last_message_at",
        "last_heartbeat_at",
        "last_reconciliation_at",
        "market_data_fresh",
        "trading_gate_open",
        "reconnect_attempts",
        "message",
    }


@pytest.mark.unit
def test_adapter_health_partitioning_and_indexes_match_database_spec() -> None:
    table = AdapterHealthSnapshotRow.__table__
    exchange_time_index = next(
        index for index in table.indexes if index.name == "ix_adapter_health__exchange_time"
    )

    assert table.dialect_options["postgresql"]["partition_by"] == "RANGE (captured_at)"
    assert [exchange_time_index.expressions[0].name] == ["exchange"]
    assert str(exchange_time_index.expressions[1].compile(dialect=postgresql.dialect())) == (
        "captured_at DESC"
    )


@pytest.mark.unit
def test_operator_audit_record_row_mapping_matches_database_spec() -> None:
    table = OperatorAuditRecordRow.__table__

    assert table.schema == "pmrp_audit"
    assert table.name == "operator_audit_records"
    assert [column.name for column in table.primary_key.columns] == [
        "requested_at",
        "audit_id",
    ]
    assert set(table.columns.keys()) == {
        "requested_at",
        "audit_id",
        "actor",
        "action",
        "scope",
        "scope_id",
        "completed_at",
        "result",
        "reason",
        "correlation_id",
        "request_id",
        "idempotency_key",
        "source_ip_hash",
        "request_hash",
    }


@pytest.mark.unit
def test_operator_audit_partitioning_and_indexes_match_database_spec() -> None:
    table = OperatorAuditRecordRow.__table__
    actor_time_index = next(
        index for index in table.indexes if index.name == "ix_operator_audit__actor_time"
    )
    scope_time_index = next(
        index for index in table.indexes if index.name == "ix_operator_audit__scope_time"
    )

    assert table.dialect_options["postgresql"]["partition_by"] == "RANGE (requested_at)"
    assert [actor_time_index.expressions[0].name] == ["actor"]
    assert str(actor_time_index.expressions[1].compile(dialect=postgresql.dialect())) == (
        "requested_at DESC"
    )
    assert [expression.name for expression in scope_time_index.expressions[:2]] == [
        "scope",
        "scope_id",
    ]
    assert str(scope_time_index.expressions[2].compile(dialect=postgresql.dialect())) == (
        "requested_at DESC"
    )


@pytest.mark.unit
def test_health_audit_rows_are_registered_in_storage_metadata() -> None:
    assert (
        StorageBase.metadata.tables["pmrp_ops.adapter_health_snapshots"]
        is AdapterHealthSnapshotRow.__table__
    )
    assert (
        StorageBase.metadata.tables["pmrp_audit.operator_audit_records"]
        is OperatorAuditRecordRow.__table__
    )
