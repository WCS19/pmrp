"""Database integration tests for the initial Alembic migration."""

from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from pmrp.storage import create_database_engine, database_config_from_environment

pytestmark = [pytest.mark.database, pytest.mark.integration]

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LOGICAL_SCHEMAS = (
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


def test_migrations_upgrade_downgrade_and_reupgrade_empty_database() -> None:
    _require_database_url()
    alembic_config = _alembic_config()

    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    assert asyncio.run(_migration_state()) == (
        "0016_risk_storage",
        LOGICAL_SCHEMAS,
        True,
    )
    assert asyncio.run(_schema_registry_state()) == (
        True,
        ("schema_name", "schema_version"),
        ("ix_schema_registry__category",),
        ("ck_schema_registry__schema_version",),
        (),
        (),
    )
    asyncio.run(_assert_schema_registry_version_constraint())
    assert asyncio.run(_exchange_registry_state()) == (
        True,
        ("exchange",),
        True,
        ("account_id",),
        ("fk_exchange_accounts__exchange__exchanges",),
        ("ix_exchange_accounts__exchange_environment",),
        False,
        "{}",
        False,
        "{}",
    )
    asyncio.run(_assert_exchange_account_foreign_key_constraint())
    assert asyncio.run(_raw_exchange_record_state()) == (
        True,
        ("received_at", "raw_record_id"),
        ("ck_exchange_records__payload_storage",),
        (
            "ix_exchange_records__channel_received",
            "ix_exchange_records__exchange_received",
            "ix_exchange_records__payload_hash",
        ),
        True,
        "application/json",
        "{}",
        b"\x01\x02",
    )
    asyncio.run(_assert_raw_exchange_record_payload_constraint())
    assert asyncio.run(_canonical_event_state()) == (
        True,
        ("event_id",),
        True,
        ("occurred_at", "event_id"),
        ("ck_canonical_events__schema_version",),
        (
            "ix_canonical_events__correlation",
            "ix_canonical_events__market_time",
            "ix_canonical_events__order_time",
            "ix_canonical_events__type_time",
        ),
        True,
        "{}",
        "{}",
        "sha256:event",
    )
    asyncio.run(_assert_event_id_unique_constraint())
    asyncio.run(_assert_canonical_event_schema_version_constraint())
    assert asyncio.run(_event_processing_state()) == (
        True,
        ("consumer_name", "event_id"),
        ("ix_processed_events__time",),
        True,
        ("outbox_id",),
        ("uq_outbox_messages__event_id_topic",),
        ("ix_outbox_messages__pending",),
        "(published_at IS NULL)",
        0,
        True,
        True,
    )
    asyncio.run(_assert_outbox_event_topic_unique_constraint())
    assert asyncio.run(_idempotency_dead_letter_state()) == (
        True,
        ("subject_id", "operation", "idempotency_key"),
        ("ix_idempotency_records__expires",),
        True,
        True,
        True,
        ("dead_letter_id",),
        ("ix_dead_letter_records__unresolved",),
        "(resolved_at IS NULL)",
        True,
        True,
    )
    asyncio.run(_assert_idempotency_primary_key_constraint())
    assert asyncio.run(_market_catalog_state()) == (
        True,
        ("market_id",),
        ("uq_markets__exchange_exchange_market_id",),
        (
            "ck_markets__payout_per_unit",
            "ck_markets__quantity_increment",
            "ck_markets__tick_size",
        ),
        (
            "ix_markets__exchange_status",
            "ix_markets__status_closes",
            "ix_markets__updated",
        ),
        True,
        "{}",
        0,
        True,
        ("outcome_id",),
        ("fk_outcomes__market_id__markets",),
        (
            "uq_outcomes__market_id_normalized_name",
            "uq_outcomes__market_id_outcome_index",
        ),
        ("ix_outcomes__market",),
        True,
        "{}",
        True,
        ("contract_id",),
        (
            "fk_contracts__market_id__markets",
            "fk_contracts__outcome_id__outcomes",
        ),
        ("uq_contracts__market_id_outcome_id",),
        ("ix_contracts__market_active",),
        "0.010000000000000000",
    )
    asyncio.run(_assert_market_catalog_constraints())
    assert asyncio.run(_order_books_trades_state()) == (
        True,
        ("market_id", "contract_id"),
        (
            "fk_order_book_snapshots__contract_id__contracts",
            "fk_order_book_snapshots__market_id__markets",
        ),
        ("ix_order_book_snapshots__exchange_updated",),
        0,
        True,
        True,
        ("exchange_occurred_at", "trade_id"),
        ("ck_trades__quantity",),
        True,
        (
            "ix_trades__contract_time",
            "ix_trades__market_time",
        ),
        True,
        "0.420000000000000000",
        "12.500000000000000000",
    )
    asyncio.run(_assert_order_books_trades_constraints())
    assert asyncio.run(_strategy_model_metadata_state()) == (
        True,
        ("strategy_type", "strategy_version"),
        True,
        True,
        ("strategy_id",),
        ("fk_strategy_instances__type_version__strategy_definitions",),
        ("ix_strategy_instances__state_health",),
        0,
        "1000.000000000000000000",
        True,
        ("strategy_id", "configuration_version"),
        ("fk_strategy_configurations__strategy_id__strategy_instances",),
        ("uq_strategy_configurations__strategy_id_configuration_hash",),
        False,
        True,
        ("model_id", "model_version"),
        ("ix_model_artifacts__approval",),
        True,
        True,
    )
    asyncio.run(_assert_strategy_model_metadata_constraints())
    assert asyncio.run(_signals_features_state()) == (
        True,
        ("generated_at", "signal_id"),
        ("ck_signals__fair_probability",),
        True,
        (
            "ix_signals__market_time",
            "ix_signals__strategy_time",
        ),
        True,
        "0.050000000000000000",
        "0.620000000000000000",
        "0.900000000000000000",
        True,
        ("observed_at", "feature_snapshot_id"),
        True,
        ("ix_feature_snapshots__market_time",),
        True,
        True,
    )
    asyncio.run(_assert_signals_features_constraints())
    assert asyncio.run(_order_storage_state()) == (
        True,
        ("intent_id",),
        (
            "ck_order_intents__limit_price",
            "ck_order_intents__quantity",
        ),
        ("uq_order_intents__strategy_id_idempotency_key",),
        ("ix_order_intents__strategy_time",),
        True,
        ("sig_01j00000000000000000000001",),
        "10.000000000000000000",
        True,
        ("order_id",),
        (
            "ck_orders__fill_balance",
            "ck_orders__filled_quantity",
            "ck_orders__quantity",
            "ck_orders__remaining_quantity",
        ),
        (
            "uq_orders__exchange_account_client_order_id",
            "uq_orders__exchange_account_exchange_order_id",
        ),
        (
            "ix_orders__account_status",
            "ix_orders__active",
            "ix_orders__strategy_created",
        ),
        True,
        True,
        0,
        "10.000000000000000000",
        "0.000000000000000000",
        "10.000000000000000000",
        True,
        ("transition_id",),
        ("fk_order_transitions__order_id__orders",),
        ("uq_order_transitions__order_version",),
        ("ix_order_transitions__order_time",),
        True,
        True,
    )
    asyncio.run(_assert_order_storage_constraints())
    assert asyncio.run(_fills_registry_state()) == (
        True,
        ("exchange_occurred_at", "fill_id"),
        ("ck_fills__quantity",),
        True,
        (
            "ix_fills__account_time",
            "ix_fills__order_time",
        ),
        True,
        "0.420000000000000000",
        "2.500000000000000000",
        "0.010000000000000000",
        "0.005000000000000000",
        True,
        ("exchange", "account_id", "exchange_fill_id"),
        ("uq_fill_ids__fill_id",),
        True,
    )
    asyncio.run(_assert_fills_registry_constraints())
    assert asyncio.run(_portfolio_storage_state()) == (
        True,
        ("position_id",),
        ("uq_positions__exchange_account_contract",),
        ("ix_positions__account_market",),
        0,
        "5.000000000000000000",
        "0.420000000000000000",
        "0.000000000000000000",
        "0.000000000000000000",
        "0.000000000000000000",
        "0.000000000000000000",
        True,
        ("balance_id",),
        ("uq_cash_balances__exchange_account_currency",),
        ("ck_cash_balances__balance_identity",),
        0,
        "990.000000000000000000",
        "10.000000000000000000",
        "1000.000000000000000000",
        True,
        ("journal_entry_id",),
        ("uq_journal_entries__source_event_id",),
        ("ix_journal_entries__reference",),
        True,
        True,
        ("journal_entry_id", "line_number"),
        ("fk_journal_lines__journal_entry_id__journal_entries",),
        ("ix_journal_lines__account_currency",),
        "2.100000000000000000",
        "-2.100000000000000000",
    )
    asyncio.run(_assert_portfolio_storage_constraints())
    assert asyncio.run(_pnl_settlements_state()) == (
        True,
        ("attribution_id",),
        ("ix_pnl_attributions__strategy_period",),
        "1.250000000000000000",
        "0.100000000000000000",
        "0.010000000000000000",
        "0.005000000000000000",
        "0.020000000000000000",
        "0.500000000000000000",
        "1.825000000000000000",
        True,
        True,
        ("settlement_id",),
        ("fk_settlements__correction_of_settlement_id__settlements",),
        ("ix_settlements__market_created",),
        True,
        ("out_01j00000000000000000000001",),
        True,
        "1.000000000000000000",
    )
    asyncio.run(_assert_pnl_settlements_constraints())
    assert asyncio.run(_risk_storage_state()) == (
        True,
        ("risk_limit_id",),
        ("ix_risk_limits__active_scope",),
        True,
        True,
        0,
        "100.000000000000000000",
        True,
        ("evaluated_at", "risk_decision_id"),
        True,
        (
            "ix_risk_decisions__intent",
            "ix_risk_decisions__status_time",
        ),
        True,
        "10.000000000000000000",
        "0.420000000000000000",
        True,
        True,
        ("breach_id",),
        ("ix_risk_breaches__open_severity",),
        True,
        True,
        "125.000000000000000000",
        "100.000000000000000000",
    )
    asyncio.run(_assert_risk_storage_constraints())

    command.downgrade(alembic_config, "base")
    assert asyncio.run(_schemas()) == ()

    command.upgrade(alembic_config, "head")
    assert asyncio.run(_migration_state()) == (
        "0016_risk_storage",
        LOGICAL_SCHEMAS,
        True,
    )


def _require_database_url() -> None:
    if not os.environ.get("PMRP_DATABASE_URL"):
        pytest.skip("PMRP_DATABASE_URL is required for database migration tests")


def _alembic_config() -> Config:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    return config


async def _migration_state() -> tuple[str, tuple[str, ...], bool]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            revision = str(
                (
                    await connection.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
            )
            extension_exists = bool(
                (
                    await connection.execute(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto')"
                        )
                    )
                ).scalar_one()
            )
            return revision, await _schemas_for_connection(connection), extension_exists
    finally:
        await engine.dispose()


async def _schemas() -> tuple[str, ...]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            return await _schemas_for_connection(connection)
    finally:
        await engine.dispose()


async def _schema_registry_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[int, ...],
    tuple[str, ...],
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            table_exists = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM information_schema.tables
                                WHERE table_schema = 'pmrp_core'
                                  AND table_name = 'schema_registry'
                            )
                            """
                        )
                    )
                ).scalar_one()
            )
            primary_key_columns = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT a.attname
                        FROM pg_index i
                        JOIN pg_attribute a
                          ON a.attrelid = i.indrelid
                         AND a.attnum = ANY(i.indkey)
                        WHERE i.indrelid = 'pmrp_core.schema_registry'::regclass
                          AND i.indisprimary
                        ORDER BY array_position(i.indkey, a.attnum)
                        """
                    )
                )
            )
            index_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'pmrp_core'
                          AND tablename = 'schema_registry'
                          AND indexname = 'ix_schema_registry__category'
                        ORDER BY indexname
                        """
                    )
                )
            )
            check_constraint_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT conname
                        FROM pg_constraint
                        WHERE conrelid = 'pmrp_core.schema_registry'::regclass
                          AND contype = 'c'
                        ORDER BY conname
                        """
                    )
                )
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_core.schema_registry (
                        schema_name,
                        schema_version,
                        schema_category,
                        python_model_path,
                        introduced_in_platform_version
                    )
                    VALUES (
                        'money',
                        1,
                        'value_object',
                        'pmrp.schemas.numeric.Money',
                        '0.1.0'
                    )
                    """
                )
            )
            inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT backward_compatible_with, upcaster_paths
                        FROM pmrp_core.schema_registry
                        WHERE schema_name = 'money'
                          AND schema_version = 1
                        """
                    )
                )
            ).one()
            return (
                table_exists,
                primary_key_columns,
                index_names,
                check_constraint_names,
                tuple(inserted[0]),
                tuple(inserted[1]),
            )
    finally:
        await engine.dispose()


async def _assert_schema_registry_version_constraint() -> None:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO pmrp_core.schema_registry (
                                schema_name,
                                schema_version,
                                schema_category,
                                python_model_path,
                                introduced_in_platform_version
                            )
                            VALUES (
                                'invalid',
                                0,
                                'domain',
                                'pmrp.schemas.markets.Market',
                                '0.1.0'
                            )
                            """
                        )
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _exchange_registry_state() -> tuple[
    bool,
    tuple[str, ...],
    bool,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    str,
    bool,
    str,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            exchange_table_exists = await _table_exists(connection, "exchanges")
            exchange_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_core.exchanges",
            )
            account_table_exists = await _table_exists(connection, "exchange_accounts")
            account_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_core.exchange_accounts",
            )
            account_foreign_key_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT conname
                        FROM pg_constraint
                        WHERE conrelid = 'pmrp_core.exchange_accounts'::regclass
                          AND contype = 'f'
                        ORDER BY conname
                        """
                    )
                )
            )
            account_index_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'pmrp_core'
                          AND tablename = 'exchange_accounts'
                          AND indexname = 'ix_exchange_accounts__exchange_environment'
                        ORDER BY indexname
                        """
                    )
                )
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_core.exchanges (exchange, display_name)
                    VALUES ('kalshi', 'Kalshi')
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_core.exchange_accounts (
                        account_id,
                        exchange,
                        environment
                    )
                    VALUES ('acct_shadow', 'kalshi', 'shadow')
                    """
                )
            )
            exchange_defaults = (
                await connection.execute(
                    text(
                        """
                        SELECT enabled, capabilities::text
                        FROM pmrp_core.exchanges
                        WHERE exchange = 'kalshi'
                        """
                    )
                )
            ).one()
            account_defaults = (
                await connection.execute(
                    text(
                        """
                        SELECT enabled, metadata::text
                        FROM pmrp_core.exchange_accounts
                        WHERE account_id = 'acct_shadow'
                        """
                    )
                )
            ).one()
            return (
                exchange_table_exists,
                exchange_primary_key_columns,
                account_table_exists,
                account_primary_key_columns,
                account_foreign_key_names,
                account_index_names,
                bool(exchange_defaults[0]),
                str(exchange_defaults[1]),
                bool(account_defaults[0]),
                str(account_defaults[1]),
            )
    finally:
        await engine.dispose()


async def _assert_exchange_account_foreign_key_constraint() -> None:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO pmrp_core.exchange_accounts (
                                account_id,
                                exchange,
                                environment
                            )
                            VALUES ('acct_invalid', 'missing', 'shadow')
                            """
                        )
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _raw_exchange_record_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    str,
    str,
    bytes,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            await _create_raw_exchange_record_test_partition(connection)
            table_exists = await _table_exists(
                connection,
                schema_name="pmrp_raw",
                table_name="exchange_records",
            )
            primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_raw.exchange_records",
            )
            check_constraint_names = await _check_constraint_names(
                connection,
                "pmrp_raw.exchange_records",
            )
            index_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'pmrp_raw'
                          AND tablename = 'exchange_records'
                          AND indexname IN (
                              'ix_exchange_records__exchange_received',
                              'ix_exchange_records__channel_received',
                              'ix_exchange_records__payload_hash'
                          )
                        ORDER BY indexname
                        """
                    )
                )
            )
            partitioned = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM pg_partitioned_table
                                WHERE partrelid = 'pmrp_raw.exchange_records'::regclass
                                  AND partstrat = 'r'
                            )
                            """
                        )
                    )
                ).scalar_one()
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_raw.exchange_records (
                        received_at,
                        raw_record_id,
                        exchange,
                        environment,
                        payload_text,
                        payload_hash
                    )
                    VALUES (
                        '2026-07-29T12:00:00Z',
                        'raw_text',
                        'kalshi',
                        'shadow',
                        '{"ok": true}',
                        'sha256:text'
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_raw.exchange_records (
                        received_at,
                        raw_record_id,
                        exchange,
                        environment,
                        payload_bytes,
                        payload_hash
                    )
                    VALUES (
                        '2026-07-29T12:00:01Z',
                        'raw_bytes',
                        'kalshi',
                        'shadow',
                        E'\\001\\002'::bytea,
                        'sha256:bytes'
                    )
                    """
                )
            )
            text_record = (
                await connection.execute(
                    text(
                        """
                        SELECT content_type, transport_metadata::text
                        FROM pmrp_raw.exchange_records
                        WHERE raw_record_id = 'raw_text'
                        """
                    )
                )
            ).one()
            binary_payload = (
                await connection.execute(
                    text(
                        """
                        SELECT payload_bytes
                        FROM pmrp_raw.exchange_records
                        WHERE raw_record_id = 'raw_bytes'
                        """
                    )
                )
            ).scalar_one()
            return (
                table_exists,
                primary_key_columns,
                check_constraint_names,
                index_names,
                partitioned,
                str(text_record[0]),
                str(text_record[1]),
                bytes(binary_payload),
            )
    finally:
        await engine.dispose()


async def _assert_raw_exchange_record_payload_constraint() -> None:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            await _create_raw_exchange_record_test_partition(connection)
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO pmrp_raw.exchange_records (
                                received_at,
                                raw_record_id,
                                exchange,
                                environment,
                                payload_text,
                                payload_bytes,
                                payload_hash
                            )
                            VALUES (
                                '2026-07-29T12:00:02Z',
                                'raw_invalid',
                                'kalshi',
                                'shadow',
                                '{}',
                                E'\\003'::bytea,
                                'sha256:invalid'
                            )
                            """
                        )
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _canonical_event_state() -> tuple[
    bool,
    tuple[str, ...],
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    str,
    str,
    str,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            await _create_canonical_event_test_partition(connection)
            event_id_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_event",
                table_name="event_ids",
            )
            event_id_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_event.event_ids",
            )
            canonical_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_event",
                table_name="canonical_events",
            )
            canonical_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_event.canonical_events",
            )
            canonical_check_constraint_names = await _check_constraint_names(
                connection,
                "pmrp_event.canonical_events",
            )
            canonical_index_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'pmrp_event'
                          AND tablename = 'canonical_events'
                          AND indexname IN (
                              'ix_canonical_events__type_time',
                              'ix_canonical_events__market_time',
                              'ix_canonical_events__order_time',
                              'ix_canonical_events__correlation'
                          )
                        ORDER BY indexname
                        """
                    )
                )
            )
            partitioned = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM pg_partitioned_table
                                WHERE partrelid = 'pmrp_event.canonical_events'::regclass
                                  AND partstrat = 'r'
                            )
                            """
                        )
                    )
                ).scalar_one()
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_event.event_ids (event_id, occurred_at)
                    VALUES ('evt_01j00000000000000000000001', '2026-07-29T12:00:00Z')
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_event.canonical_events (
                        occurred_at,
                        event_id,
                        event_type,
                        schema_version,
                        received_at,
                        published_at,
                        producer,
                        correlation_id,
                        payload,
                        payload_hash
                    )
                    VALUES (
                        '2026-07-29T12:00:00Z',
                        'evt_01j00000000000000000000001',
                        'market.discovered',
                        1,
                        '2026-07-29T12:00:00.100000Z',
                        '2026-07-29T12:00:00.200000Z',
                        'test-producer',
                        'corr_01j00000000000000000000001',
                        '{"event": "ok"}'::jsonb,
                        'sha256:event'
                    )
                    """
                )
            )
            inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT quality_flags::text, attributes::text, payload_hash
                        FROM pmrp_event.canonical_events
                        WHERE event_id = 'evt_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            return (
                event_id_table_exists,
                event_id_primary_key_columns,
                canonical_table_exists,
                canonical_primary_key_columns,
                canonical_check_constraint_names,
                canonical_index_names,
                partitioned,
                str(inserted[0]),
                str(inserted[1]),
                str(inserted[2]),
            )
    finally:
        await engine.dispose()


async def _assert_event_id_unique_constraint() -> None:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO pmrp_event.event_ids (event_id, occurred_at)
                            VALUES (
                                'evt_01j00000000000000000000001',
                                '2026-07-29T12:00:01Z'
                            )
                            """
                        )
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _assert_canonical_event_schema_version_constraint() -> None:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            await _create_canonical_event_test_partition(connection)
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO pmrp_event.canonical_events (
                                occurred_at,
                                event_id,
                                event_type,
                                schema_version,
                                received_at,
                                published_at,
                                producer,
                                correlation_id,
                                payload,
                                payload_hash
                            )
                            VALUES (
                                '2026-07-29T12:00:02Z',
                                'evt_01j00000000000000000000002',
                                'market.discovered',
                                0,
                                '2026-07-29T12:00:02.100000Z',
                                '2026-07-29T12:00:02.200000Z',
                                'test-producer',
                                'corr_01j00000000000000000000002',
                                '{}'::jsonb,
                                'sha256:invalid-event'
                            )
                            """
                        )
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _event_processing_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    str,
    int,
    bool,
    bool,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            processed_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_event",
                table_name="processed_events",
            )
            processed_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_event.processed_events",
            )
            processed_index_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'pmrp_event'
                          AND tablename = 'processed_events'
                          AND indexname = 'ix_processed_events__time'
                        ORDER BY indexname
                        """
                    )
                )
            )
            outbox_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_event",
                table_name="outbox_messages",
            )
            outbox_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_event.outbox_messages",
            )
            outbox_unique_constraint_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT conname
                        FROM pg_constraint
                        WHERE conrelid = 'pmrp_event.outbox_messages'::regclass
                          AND contype = 'u'
                        ORDER BY conname
                        """
                    )
                )
            )
            outbox_pending_index = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            idx.relname,
                            pg_get_expr(i.indpred, i.indrelid)
                        FROM pg_index i
                        JOIN pg_class idx ON idx.oid = i.indexrelid
                        WHERE i.indrelid = 'pmrp_event.outbox_messages'::regclass
                          AND idx.relname = 'ix_outbox_messages__pending'
                        """
                    )
                )
            ).one()

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_event.processed_events (
                        consumer_name,
                        event_id,
                        processing_version,
                        result_hash
                    )
                    VALUES (
                        'research-indexer',
                        'evt_01j00000000000000000000003',
                        'v1',
                        'sha256:result'
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_event.outbox_messages (
                        event_id,
                        topic,
                        partition_key,
                        payload
                    )
                    VALUES (
                        'evt_01j00000000000000000000003',
                        'canonical-events',
                        'mkt_01j00000000000000000000001',
                        '{"ok": true}'::jsonb
                    )
                    """
                )
            )
            inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            publish_attempts,
                            created_at IS NOT NULL,
                            available_at IS NOT NULL
                        FROM pmrp_event.outbox_messages
                        WHERE event_id = 'evt_01j00000000000000000000003'
                          AND topic = 'canonical-events'
                        """
                    )
                )
            ).one()
            return (
                processed_table_exists,
                processed_primary_key_columns,
                processed_index_names,
                outbox_table_exists,
                outbox_primary_key_columns,
                outbox_unique_constraint_names,
                (str(outbox_pending_index[0]),),
                str(outbox_pending_index[1]),
                int(inserted[0]),
                bool(inserted[1]),
                bool(inserted[2]),
            )
    finally:
        await engine.dispose()


async def _assert_outbox_event_topic_unique_constraint() -> None:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO pmrp_event.outbox_messages (
                                event_id,
                                topic,
                                payload
                            )
                            VALUES (
                                'evt_01j00000000000000000000003',
                                'canonical-events',
                                '{}'::jsonb
                            )
                            """
                        )
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _idempotency_dead_letter_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    bool,
    bool,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    str,
    bool,
    bool,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            idempotency_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_core",
                table_name="idempotency_records",
            )
            idempotency_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_core.idempotency_records",
            )
            idempotency_index_names = tuple(
                str(row[0])
                for row in await connection.execute(
                    text(
                        """
                        SELECT indexname
                        FROM pg_indexes
                        WHERE schemaname = 'pmrp_core'
                          AND tablename = 'idempotency_records'
                          AND indexname = 'ix_idempotency_records__expires'
                        ORDER BY indexname
                        """
                    )
                )
            )
            dead_letter_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_ops",
                table_name="dead_letter_records",
            )
            dead_letter_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_ops.dead_letter_records",
            )
            dead_letter_unresolved_index = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            idx.relname,
                            pg_get_expr(i.indpred, i.indrelid)
                        FROM pg_index i
                        JOIN pg_class idx ON idx.oid = i.indexrelid
                        WHERE i.indrelid = 'pmrp_ops.dead_letter_records'::regclass
                          AND idx.relname = 'ix_dead_letter_records__unresolved'
                        """
                    )
                )
            ).one()

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_core.idempotency_records (
                        subject_id,
                        operation,
                        idempotency_key,
                        request_hash,
                        status,
                        response_status,
                        response_headers,
                        response_body,
                        expires_at
                    )
                    VALUES (
                        'operator_01j00000000000000000000001',
                        'submit-order-intent',
                        'idem_01j00000000000000000000001',
                        'sha256:request',
                        'completed',
                        201,
                        '{"content-type": "application/json"}'::jsonb,
                        '{"ok": true}'::jsonb,
                        '2026-07-30T12:00:00Z'
                    )
                    """
                )
            )
            idempotency_inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            created_at IS NOT NULL,
                            response_headers::text,
                            response_body::text
                        FROM pmrp_core.idempotency_records
                        WHERE subject_id = 'operator_01j00000000000000000000001'
                          AND operation = 'submit-order-intent'
                          AND idempotency_key = 'idem_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_ops.dead_letter_records (
                        dead_letter_id,
                        source_event_id,
                        consumer_name,
                        failure_category,
                        exception_type,
                        exception_message,
                        first_failed_at,
                        last_failed_at,
                        retry_count,
                        payload_reference,
                        replayable
                    )
                    VALUES (
                        'dlq_01j00000000000000000000001',
                        'evt_01j00000000000000000000003',
                        'research-indexer',
                        'validation',
                        'ValueError',
                        'invalid payload',
                        '2026-07-29T12:01:00Z',
                        '2026-07-29T12:02:00Z',
                        2,
                        'pmrp_event.canonical_events/evt_01j00000000000000000000003',
                        true
                    )
                    """
                )
            )
            dead_letter_inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            created_at IS NOT NULL,
                            replayable
                        FROM pmrp_ops.dead_letter_records
                        WHERE dead_letter_id = 'dlq_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            return (
                idempotency_table_exists,
                idempotency_primary_key_columns,
                idempotency_index_names,
                bool(idempotency_inserted[0]),
                str(idempotency_inserted[1]) == '{"content-type": "application/json"}',
                str(idempotency_inserted[2]) == '{"ok": true}',
                dead_letter_primary_key_columns,
                (str(dead_letter_unresolved_index[0]),),
                str(dead_letter_unresolved_index[1]),
                dead_letter_table_exists,
                bool(dead_letter_inserted[0]) and bool(dead_letter_inserted[1]),
            )
    finally:
        await engine.dispose()


async def _assert_idempotency_primary_key_constraint() -> None:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(
                            """
                            INSERT INTO pmrp_core.idempotency_records (
                                subject_id,
                                operation,
                                idempotency_key,
                                request_hash,
                                status,
                                expires_at
                            )
                            VALUES (
                                'operator_01j00000000000000000000001',
                                'submit-order-intent',
                                'idem_01j00000000000000000000001',
                                'sha256:duplicate',
                                'completed',
                                '2026-07-30T12:00:00Z'
                            )
                            """
                        )
                    )
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


async def _market_catalog_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    str,
    int,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    str,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    str,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            market_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_market",
                table_name="markets",
            )
            market_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_market.markets",
            )
            market_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_market.markets",
                constraint_type="u",
            )
            market_check_constraint_names = await _check_constraint_names(
                connection,
                "pmrp_market.markets",
            )
            market_index_names = await _index_names(
                connection,
                schema_name="pmrp_market",
                table_name="markets",
                expected_names=(
                    "ix_markets__exchange_status",
                    "ix_markets__status_closes",
                    "ix_markets__updated",
                ),
            )
            market_updated_index_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%updated_at DESC%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_market'
                              AND tablename = 'markets'
                              AND indexname = 'ix_markets__updated'
                            """
                        )
                    )
                ).scalar_one()
            )
            outcome_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_market",
                table_name="outcomes",
            )
            outcome_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_market.outcomes",
            )
            outcome_foreign_key_names = await _constraint_names(
                connection,
                "pmrp_market.outcomes",
                constraint_type="f",
            )
            outcome_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_market.outcomes",
                constraint_type="u",
            )
            outcome_index_names = await _index_names(
                connection,
                schema_name="pmrp_market",
                table_name="outcomes",
                expected_names=("ix_outcomes__market",),
            )
            contract_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_market",
                table_name="contracts",
            )
            contract_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_market.contracts",
            )
            contract_foreign_key_names = await _constraint_names(
                connection,
                "pmrp_market.contracts",
                constraint_type="f",
            )
            contract_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_market.contracts",
                constraint_type="u",
            )
            contract_index_names = await _index_names(
                connection,
                schema_name="pmrp_market",
                table_name="contracts",
                expected_names=("ix_contracts__market_active",),
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_market.markets (
                        market_id,
                        exchange,
                        exchange_market_id,
                        title,
                        outcome_type,
                        status,
                        closes_at,
                        currency,
                        payout_per_unit,
                        tick_size,
                        quantity_increment,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'mkt_01j00000000000000000000001',
                        'kalshi',
                        'FED-26SEP-T4.50',
                        'Federal funds target rate above 4.50%',
                        'binary',
                        'open',
                        '2026-09-30T20:00:00Z',
                        'USD',
                        1.000000000000000000,
                        0.010000000000000000,
                        1.000000000000000000,
                        '2026-07-29T12:00:00Z',
                        '2026-07-29T12:00:00Z'
                    )
                    """
                )
            )
            market_inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT tags::text, aggregate_version
                        FROM pmrp_market.markets
                        WHERE market_id = 'mkt_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_market.outcomes (
                        outcome_id,
                        market_id,
                        name,
                        normalized_name,
                        outcome_index,
                        payout_per_unit
                    )
                    VALUES (
                        'out_01j00000000000000000000001',
                        'mkt_01j00000000000000000000001',
                        'Yes',
                        'yes',
                        0,
                        1.000000000000000000
                    )
                    """
                )
            )
            outcome_inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT is_tradeable, metadata::text
                        FROM pmrp_market.outcomes
                        WHERE outcome_id = 'out_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_market.contracts (
                        contract_id,
                        market_id,
                        outcome_id,
                        display_name,
                        tick_size,
                        quantity_increment,
                        min_order_quantity,
                        active,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'ctr_01j00000000000000000000001',
                        'mkt_01j00000000000000000000001',
                        'out_01j00000000000000000000001',
                        'Yes',
                        0.010000000000000000,
                        1.000000000000000000,
                        1.000000000000000000,
                        true,
                        '2026-07-29T12:00:00Z',
                        '2026-07-29T12:00:00Z'
                    )
                    """
                )
            )
            contract_tick_size = (
                await connection.execute(
                    text(
                        """
                        SELECT tick_size
                        FROM pmrp_market.contracts
                        WHERE contract_id = 'ctr_01j00000000000000000000001'
                        """
                    )
                )
            ).scalar_one()
            return (
                market_table_exists,
                market_primary_key_columns,
                market_unique_constraint_names,
                market_check_constraint_names,
                market_index_names,
                market_updated_index_descending,
                str(market_inserted[0]),
                int(market_inserted[1]),
                outcome_table_exists,
                outcome_primary_key_columns,
                outcome_foreign_key_names,
                outcome_unique_constraint_names,
                outcome_index_names,
                bool(outcome_inserted[0]),
                str(outcome_inserted[1]),
                contract_table_exists,
                contract_primary_key_columns,
                contract_foreign_key_names,
                contract_unique_constraint_names,
                contract_index_names,
                str(contract_tick_size),
            )
    finally:
        await engine.dispose()


async def _assert_market_catalog_constraints() -> None:
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_market.markets (
            market_id,
            exchange,
            exchange_market_id,
            title,
            outcome_type,
            status,
            currency,
            payout_per_unit,
            tick_size,
            quantity_increment,
            created_at,
            updated_at
        )
        VALUES (
            'mkt_01j00000000000000000000002',
            'kalshi',
            'NEGATIVE-PAYOUT',
            'Invalid market',
            'binary',
            'open',
            'USD',
            -1.000000000000000000,
            0.010000000000000000,
            1.000000000000000000,
            '2026-07-29T12:00:00Z',
            '2026-07-29T12:00:00Z'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_market.outcomes (
            outcome_id,
            market_id,
            name,
            normalized_name,
            outcome_index,
            payout_per_unit
        )
        VALUES (
            'out_01j00000000000000000000002',
            'mkt_missing',
            'No',
            'no',
            1,
            1.000000000000000000
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_market.contracts (
            contract_id,
            market_id,
            outcome_id,
            display_name,
            tick_size,
            quantity_increment,
            active,
            created_at,
            updated_at
        )
        VALUES (
            'ctr_01j00000000000000000000002',
            'mkt_01j00000000000000000000001',
            'out_01j00000000000000000000001',
            'Duplicate Yes',
            0.010000000000000000,
            1.000000000000000000,
            true,
            '2026-07-29T12:00:00Z',
            '2026-07-29T12:00:00Z'
        )
        """
    )


async def _order_books_trades_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    int,
    bool,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    bool,
    tuple[str, ...],
    bool,
    str,
    str,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            await _create_trade_test_partition(connection)
            order_book_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_market",
                table_name="order_book_snapshots",
            )
            order_book_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_market.order_book_snapshots",
            )
            order_book_foreign_key_names = await _constraint_names(
                connection,
                "pmrp_market.order_book_snapshots",
                constraint_type="f",
            )
            order_book_index_names = await _index_names(
                connection,
                schema_name="pmrp_market",
                table_name="order_book_snapshots",
                expected_names=("ix_order_book_snapshots__exchange_updated",),
            )
            trade_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_market.trades",
            )
            trade_check_constraint_names = await _check_constraint_names(
                connection,
                "pmrp_market.trades",
            )
            trade_partitioned = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT EXISTS (
                                SELECT 1
                                FROM pg_partitioned_table
                                WHERE partrelid = 'pmrp_market.trades'::regclass
                                  AND partstrat = 'r'
                            )
                            """
                        )
                    )
                ).scalar_one()
            )
            trade_index_names = await _index_names(
                connection,
                schema_name="pmrp_market",
                table_name="trades",
                expected_names=("ix_trades__contract_time", "ix_trades__market_time"),
            )
            trade_indexes_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT bool_and(indexdef LIKE '%exchange_occurred_at DESC%')
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_market'
                              AND tablename = 'trades'
                              AND indexname IN (
                                  'ix_trades__contract_time',
                                  'ix_trades__market_time'
                              )
                            """
                        )
                    )
                ).scalar_one()
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_market.order_book_snapshots (
                        market_id,
                        contract_id,
                        exchange,
                        exchange_occurred_at,
                        received_at,
                        bids,
                        asks,
                        is_valid,
                        snapshot_reason
                    )
                    VALUES (
                        'mkt_01j00000000000000000000001',
                        'ctr_01j00000000000000000000001',
                        'kalshi',
                        '2026-07-29T12:03:00Z',
                        '2026-07-29T12:03:00.100000Z',
                        '{"levels": [{"price": "0.41", "quantity": "10"}]}'::jsonb,
                        '{"levels": [{"price": "0.42", "quantity": "12.5"}]}'::jsonb,
                        true,
                        'exchange_snapshot'
                    )
                    """
                )
            )
            order_book_inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            aggregate_version,
                            updated_at IS NOT NULL,
                            bids ? 'levels'
                        FROM pmrp_market.order_book_snapshots
                        WHERE market_id = 'mkt_01j00000000000000000000001'
                          AND contract_id = 'ctr_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_market.trades (
                        exchange_occurred_at,
                        trade_id,
                        exchange,
                        exchange_trade_id,
                        market_id,
                        contract_id,
                        outcome_id,
                        price,
                        quantity,
                        liquidity_role,
                        received_at,
                        sequence,
                        source_event_id
                    )
                    VALUES (
                        '2026-07-29T12:04:00Z',
                        'trd_01j00000000000000000000001',
                        'kalshi',
                        'kalshi-trade-1',
                        'mkt_01j00000000000000000000001',
                        'ctr_01j00000000000000000000001',
                        'out_01j00000000000000000000001',
                        0.420000000000000000,
                        12.500000000000000000,
                        'taker',
                        '2026-07-29T12:04:00.100000Z',
                        1001,
                        'evt_01j00000000000000000000003'
                    )
                    """
                )
            )
            inserted_trade = (
                await connection.execute(
                    text(
                        """
                        SELECT price, quantity
                        FROM pmrp_market.trades
                        WHERE trade_id = 'trd_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            return (
                order_book_table_exists,
                order_book_primary_key_columns,
                order_book_foreign_key_names,
                order_book_index_names,
                int(order_book_inserted[0]),
                bool(order_book_inserted[1]),
                bool(order_book_inserted[2]),
                trade_primary_key_columns,
                trade_check_constraint_names,
                trade_partitioned,
                trade_index_names,
                trade_indexes_descending,
                str(inserted_trade[0]),
                str(inserted_trade[1]),
            )
    finally:
        await engine.dispose()


async def _assert_order_books_trades_constraints() -> None:
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_market.order_book_snapshots (
            market_id,
            contract_id,
            exchange,
            received_at,
            bids,
            asks,
            is_valid,
            snapshot_reason
        )
        VALUES (
            'mkt_missing',
            'ctr_01j00000000000000000000001',
            'kalshi',
            '2026-07-29T12:05:00Z',
            '{}'::jsonb,
            '{}'::jsonb,
            false,
            'missing_market'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_market.trades (
            exchange_occurred_at,
            trade_id,
            exchange,
            exchange_trade_id,
            market_id,
            contract_id,
            outcome_id,
            price,
            quantity,
            liquidity_role,
            received_at,
            source_event_id
        )
        VALUES (
            '2026-07-29T12:05:00Z',
            'trd_01j00000000000000000000002',
            'kalshi',
            'kalshi-trade-invalid',
            'mkt_01j00000000000000000000001',
            'ctr_01j00000000000000000000001',
            'out_01j00000000000000000000001',
            0.420000000000000000,
            0.000000000000000000,
            'taker',
            '2026-07-29T12:05:00.100000Z',
            'evt_01j00000000000000000000003'
        )
        """
    )


async def _strategy_model_metadata_state() -> tuple[
    bool,
    tuple[str, ...],
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    int,
    str,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    bool,
    bool,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            definition_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_research",
                table_name="strategy_definitions",
            )
            definition_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_research.strategy_definitions",
            )
            instance_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_research",
                table_name="strategy_instances",
            )
            instance_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_research.strategy_instances",
            )
            instance_foreign_key_names = await _constraint_names(
                connection,
                "pmrp_research.strategy_instances",
                constraint_type="f",
            )
            instance_index_names = await _index_names(
                connection,
                schema_name="pmrp_research",
                table_name="strategy_instances",
                expected_names=("ix_strategy_instances__state_health",),
            )
            configuration_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_research",
                table_name="strategy_configurations",
            )
            configuration_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_research.strategy_configurations",
            )
            configuration_foreign_key_names = await _constraint_names(
                connection,
                "pmrp_research.strategy_configurations",
                constraint_type="f",
            )
            configuration_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_research.strategy_configurations",
                constraint_type="u",
            )
            model_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_research",
                table_name="model_artifacts",
            )
            model_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_research.model_artifacts",
            )
            model_index_names = await _index_names(
                connection,
                schema_name="pmrp_research",
                table_name="model_artifacts",
                expected_names=("ix_model_artifacts__approval",),
            )
            model_approval_index_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%trained_at DESC%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_research'
                              AND tablename = 'model_artifacts'
                              AND indexname = 'ix_model_artifacts__approval'
                            """
                        )
                    )
                ).scalar_one()
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_research.strategy_definitions (
                        strategy_type,
                        strategy_version,
                        implementation_path,
                        configuration_schema_version,
                        subscribed_event_types,
                        supports_replay,
                        supports_simulation,
                        supports_paper,
                        supports_shadow,
                        supports_live
                    )
                    VALUES (
                        'fed_value',
                        '1.0.0',
                        'pmrp.strategies.fed_value:Strategy',
                        1,
                        ARRAY['market.discovered', 'book.updated']::text[],
                        true,
                        true,
                        true,
                        true,
                        false
                    )
                    """
                )
            )
            definition_inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT created_at IS NOT NULL
                        FROM pmrp_research.strategy_definitions
                        WHERE strategy_type = 'fed_value'
                          AND strategy_version = '1.0.0'
                        """
                    )
                )
            ).scalar_one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_research.strategy_instances (
                        strategy_id,
                        strategy_type,
                        strategy_version,
                        name,
                        environment,
                        state,
                        configuration_version,
                        configuration_hash,
                        capital_allocation_amount,
                        capital_allocation_currency,
                        health_status,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        'strat_fed_value_v1',
                        'fed_value',
                        '1.0.0',
                        'Fed value shadow',
                        'shadow',
                        'running',
                        1,
                        'sha256:strategy-config',
                        1000.000000000000000000,
                        'USD',
                        'healthy',
                        '2026-07-29T12:00:00Z',
                        '2026-07-29T12:00:00Z'
                    )
                    """
                )
            )
            strategy_instance = (
                await connection.execute(
                    text(
                        """
                        SELECT aggregate_version, capital_allocation_amount
                        FROM pmrp_research.strategy_instances
                        WHERE strategy_id = 'strat_fed_value_v1'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_research.strategy_configurations (
                        strategy_id,
                        configuration_version,
                        effective_at,
                        configuration,
                        configuration_hash,
                        created_by
                    )
                    VALUES (
                        'strat_fed_value_v1',
                        1,
                        '2026-07-29T12:00:00Z',
                        '{"threshold": "0.03"}'::jsonb,
                        'sha256:strategy-config',
                        'operator'
                    )
                    """
                )
            )
            strategy_configuration = (
                await connection.execute(
                    text(
                        """
                        SELECT approval_required, configuration ? 'threshold'
                        FROM pmrp_research.strategy_configurations
                        WHERE strategy_id = 'strat_fed_value_v1'
                          AND configuration_version = 1
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_research.model_artifacts (
                        model_id,
                        model_version,
                        model_name,
                        artifact_uri,
                        artifact_checksum,
                        training_dataset_id,
                        training_dataset_checksum,
                        training_code_commit,
                        dependency_lock_hash,
                        feature_schema_version,
                        target_definition,
                        trained_at,
                        random_seed,
                        evaluation_metrics,
                        approval_status
                    )
                    VALUES (
                        'mdl_fed_probability',
                        '1.0.0',
                        'Fed probability model',
                        'artifact://models/fed-probability/1.0.0',
                        'sha256:model-artifact',
                        'dataset_fed_2026_07',
                        'sha256:dataset',
                        '0123456789abcdef',
                        'sha256:uv-lock',
                        'features-v1',
                        'binary-resolution-probability',
                        '2026-07-29T12:00:00Z',
                        42,
                        '{"brier": "0.12"}'::jsonb,
                        'approved'
                    )
                    """
                )
            )
            model_inserted = (
                await connection.execute(
                    text(
                        """
                        SELECT created_at IS NOT NULL, evaluation_metrics ? 'brier'
                        FROM pmrp_research.model_artifacts
                        WHERE model_id = 'mdl_fed_probability'
                          AND model_version = '1.0.0'
                        """
                    )
                )
            ).one()
            return (
                definition_table_exists,
                definition_primary_key_columns,
                bool(definition_inserted),
                instance_table_exists,
                instance_primary_key_columns,
                instance_foreign_key_names,
                instance_index_names,
                int(strategy_instance[0]),
                str(strategy_instance[1]),
                configuration_table_exists,
                configuration_primary_key_columns,
                configuration_foreign_key_names,
                configuration_unique_constraint_names,
                bool(strategy_configuration[0]),
                bool(strategy_configuration[1]),
                model_primary_key_columns,
                model_index_names,
                model_approval_index_descending,
                model_table_exists and bool(model_inserted[0]) and bool(model_inserted[1]),
            )
    finally:
        await engine.dispose()


async def _assert_strategy_model_metadata_constraints() -> None:
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_research.strategy_instances (
            strategy_id,
            strategy_type,
            strategy_version,
            name,
            environment,
            state,
            configuration_version,
            configuration_hash,
            health_status,
            created_at,
            updated_at
        )
        VALUES (
            'strat_missing_definition',
            'missing',
            '1.0.0',
            'Missing definition',
            'shadow',
            'stopped',
            1,
            'sha256:missing-config',
            'unknown',
            '2026-07-29T12:00:00Z',
            '2026-07-29T12:00:00Z'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_research.strategy_configurations (
            strategy_id,
            configuration_version,
            effective_at,
            configuration,
            configuration_hash,
            created_by
        )
        VALUES (
            'strat_fed_value_v1',
            2,
            '2026-07-29T12:01:00Z',
            '{"threshold": "0.04"}'::jsonb,
            'sha256:strategy-config',
            'operator'
        )
        """
    )


async def _signals_features_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    bool,
    tuple[str, ...],
    bool,
    str,
    str,
    str,
    bool,
    tuple[str, ...],
    bool,
    tuple[str, ...],
    bool,
    bool,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            signal_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_research",
                table_name="signals",
            )
            signal_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_research.signals",
            )
            signal_check_constraint_names = await _check_constraint_names(
                connection,
                "pmrp_research.signals",
            )
            signal_partitioned = await _partitioned_table_exists(
                connection,
                "pmrp_research.signals",
            )
            signal_index_names = await _index_names(
                connection,
                schema_name="pmrp_research",
                table_name="signals",
                expected_names=("ix_signals__market_time", "ix_signals__strategy_time"),
            )
            signal_indexes_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT bool_and(indexdef LIKE '%generated_at DESC%')
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_research'
                              AND tablename = 'signals'
                              AND indexname IN (
                                  'ix_signals__market_time',
                                  'ix_signals__strategy_time'
                              )
                            """
                        )
                    )
                ).scalar_one()
            )
            feature_snapshot_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_research",
                table_name="feature_snapshots",
            )
            feature_snapshot_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_research.feature_snapshots",
            )
            feature_snapshot_partitioned = await _partitioned_table_exists(
                connection,
                "pmrp_research.feature_snapshots",
            )
            feature_snapshot_index_names = await _index_names(
                connection,
                schema_name="pmrp_research",
                table_name="feature_snapshots",
                expected_names=("ix_feature_snapshots__market_time",),
            )
            feature_snapshot_index_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%observed_at DESC%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_research'
                              AND tablename = 'feature_snapshots'
                              AND indexname = 'ix_feature_snapshots__market_time'
                            """
                        )
                    )
                ).scalar_one()
            )

            await _create_signal_test_partition(connection)
            await _create_feature_snapshot_test_partition(connection)
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_research.signals (
                        generated_at,
                        signal_id,
                        strategy_id,
                        market_id,
                        contract_id,
                        outcome_id,
                        signal_type,
                        direction,
                        strength,
                        fair_probability,
                        confidence,
                        valid_from,
                        valid_until,
                        model_id,
                        model_version,
                        feature_snapshot_id,
                        reason_code,
                        reason_text,
                        correlation_id,
                        source_event_id
                    )
                    VALUES (
                        '2026-07-29T12:06:00Z',
                        'sig_01j00000000000000000000001',
                        'strat_fed_value_v1',
                        'mkt_01j00000000000000000000001',
                        'ctr_01j00000000000000000000001',
                        'out_01j00000000000000000000001',
                        'fair_value',
                        'buy',
                        0.050000000000000000,
                        0.620000000000000000,
                        0.900000000000000000,
                        '2026-07-29T12:06:00Z',
                        '2026-07-29T12:16:00Z',
                        'mdl_fed_probability',
                        '1.0.0',
                        'feat_01j00000000000000000000001',
                        'edge_above_threshold',
                        'Fair probability exceeds market implied price.',
                        'corr_01j00000000000000000000001',
                        'evt_01j00000000000000000000004'
                    )
                    """
                )
            )
            inserted_signal = (
                await connection.execute(
                    text(
                        """
                        SELECT strength, fair_probability, confidence
                        FROM pmrp_research.signals
                        WHERE signal_id = 'sig_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_research.feature_snapshots (
                        observed_at,
                        feature_snapshot_id,
                        market_id,
                        strategy_id,
                        generated_at,
                        schema_version,
                        calculation_version,
                        features,
                        source_event_ids,
                        payload_hash
                    )
                    VALUES (
                        '2026-07-29T12:06:00Z',
                        'feat_01j00000000000000000000001',
                        'mkt_01j00000000000000000000001',
                        'strat_fed_value_v1',
                        '2026-07-29T12:06:00.050000Z',
                        1,
                        'calc-v1',
                        '{"values": [{"name": "best_bid", "value_decimal": "0.57"}]}'::jsonb,
                        ARRAY['evt_01j00000000000000000000004']::text[],
                        'sha256:feature-snapshot'
                    )
                    """
                )
            )
            inserted_feature_snapshot = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            features ? 'values',
                            source_event_ids = ARRAY['evt_01j00000000000000000000004']::text[],
                            payload_hash
                        FROM pmrp_research.feature_snapshots
                        WHERE feature_snapshot_id = 'feat_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            return (
                signal_table_exists,
                signal_primary_key_columns,
                signal_check_constraint_names,
                signal_partitioned,
                signal_index_names,
                signal_indexes_descending,
                str(inserted_signal[0]),
                str(inserted_signal[1]),
                str(inserted_signal[2]),
                feature_snapshot_table_exists,
                feature_snapshot_primary_key_columns,
                feature_snapshot_partitioned,
                feature_snapshot_index_names,
                feature_snapshot_index_descending,
                bool(inserted_feature_snapshot[0])
                and bool(inserted_feature_snapshot[1])
                and inserted_feature_snapshot[2] == "sha256:feature-snapshot",
            )
    finally:
        await engine.dispose()


async def _assert_signals_features_constraints() -> None:
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_research.signals (
            generated_at,
            signal_id,
            strategy_id,
            market_id,
            signal_type,
            direction,
            fair_probability,
            valid_from,
            reason_code,
            correlation_id
        )
        VALUES (
            '2026-07-29T12:07:00Z',
            'sig_01j00000000000000000000002',
            'strat_fed_value_v1',
            'mkt_01j00000000000000000000001',
            'fair_value',
            'buy',
            1.010000000000000000,
            '2026-07-29T12:07:00Z',
            'invalid_probability',
            'corr_01j00000000000000000000001'
        )
        """
    )


async def _order_storage_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    tuple[str, ...],
    str,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    bool,
    int,
    str,
    str,
    str,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    bool,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            intent_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_execution",
                table_name="order_intents",
            )
            intent_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_execution.order_intents",
            )
            intent_check_constraint_names = await _check_constraint_names(
                connection,
                "pmrp_execution.order_intents",
            )
            intent_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_execution.order_intents",
                constraint_type="u",
            )
            intent_index_names = await _index_names(
                connection,
                schema_name="pmrp_execution",
                table_name="order_intents",
                expected_names=("ix_order_intents__strategy_time",),
            )
            intent_index_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%created_at DESC%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_execution'
                              AND tablename = 'order_intents'
                              AND indexname = 'ix_order_intents__strategy_time'
                            """
                        )
                    )
                ).scalar_one()
            )
            order_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_execution",
                table_name="orders",
            )
            order_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_execution.orders",
            )
            order_check_constraint_names = await _check_constraint_names(
                connection,
                "pmrp_execution.orders",
            )
            order_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_execution.orders",
                constraint_type="u",
            )
            order_index_names = await _index_names(
                connection,
                schema_name="pmrp_execution",
                table_name="orders",
                expected_names=(
                    "ix_orders__account_status",
                    "ix_orders__active",
                    "ix_orders__strategy_created",
                ),
            )
            order_strategy_index_partial = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%WHERE (strategy_id IS NOT NULL)%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_execution'
                              AND tablename = 'orders'
                              AND indexname = 'ix_orders__strategy_created'
                            """
                        )
                    )
                ).scalar_one()
            )
            order_active_index_partial = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%WHERE (status = ANY%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_execution'
                              AND tablename = 'orders'
                              AND indexname = 'ix_orders__active'
                            """
                        )
                    )
                ).scalar_one()
            )
            transition_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_execution",
                table_name="order_state_transitions",
            )
            transition_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_execution.order_state_transitions",
            )
            transition_foreign_key_names = await _constraint_names(
                connection,
                "pmrp_execution.order_state_transitions",
                constraint_type="f",
            )
            transition_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_execution.order_state_transitions",
                constraint_type="u",
            )
            transition_index_names = await _index_names(
                connection,
                schema_name="pmrp_execution",
                table_name="order_state_transitions",
                expected_names=("ix_order_transitions__order_time",),
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_execution.order_intents (
                        intent_id,
                        strategy_id,
                        market_id,
                        contract_id,
                        outcome_id,
                        side,
                        quantity,
                        limit_price,
                        order_type,
                        time_in_force,
                        post_only,
                        reduce_only,
                        urgency,
                        created_at,
                        expires_at,
                        signal_ids,
                        correlation_id,
                        idempotency_key,
                        payload_hash
                    )
                    VALUES (
                        'intent_01j00000000000000000000001',
                        'strat_fed_value_v1',
                        'mkt_01j00000000000000000000001',
                        'ctr_01j00000000000000000000001',
                        'out_01j00000000000000000000001',
                        'buy',
                        10.000000000000000000,
                        0.420000000000000000,
                        'limit',
                        'gtc',
                        false,
                        false,
                        0.800000000000000000,
                        '2026-07-29T12:08:00Z',
                        '2026-07-29T12:18:00Z',
                        ARRAY['sig_01j00000000000000000000001']::text[],
                        'corr_01j00000000000000000000001',
                        'intent-key-1',
                        'sha256:order-intent'
                    )
                    """
                )
            )
            inserted_intent = (
                await connection.execute(
                    text(
                        """
                        SELECT signal_ids, quantity
                        FROM pmrp_execution.order_intents
                        WHERE intent_id = 'intent_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_execution.orders (
                        order_id,
                        intent_id,
                        strategy_id,
                        exchange,
                        account_id,
                        market_id,
                        contract_id,
                        outcome_id,
                        side,
                        quantity,
                        remaining_quantity,
                        limit_price,
                        order_type,
                        time_in_force,
                        post_only,
                        reduce_only,
                        status,
                        client_order_id,
                        exchange_order_id,
                        created_at,
                        last_updated_at
                    )
                    VALUES (
                        'ord_01j00000000000000000000001',
                        'intent_01j00000000000000000000001',
                        'strat_fed_value_v1',
                        'kalshi',
                        'acct_01j00000000000000000000001',
                        'mkt_01j00000000000000000000001',
                        'ctr_01j00000000000000000000001',
                        'out_01j00000000000000000000001',
                        'buy',
                        10.000000000000000000,
                        10.000000000000000000,
                        0.420000000000000000,
                        'limit',
                        'gtc',
                        false,
                        false,
                        'created',
                        'client-order-1',
                        'exchange-order-1',
                        '2026-07-29T12:08:00Z',
                        '2026-07-29T12:08:00Z'
                    )
                    """
                )
            )
            inserted_order = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            aggregate_version,
                            quantity,
                            filled_quantity,
                            remaining_quantity
                        FROM pmrp_execution.orders
                        WHERE order_id = 'ord_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_execution.order_state_transitions (
                        transition_id,
                        order_id,
                        previous_status,
                        current_status,
                        occurred_at,
                        source_event_id,
                        reason_code,
                        aggregate_version_before,
                        aggregate_version_after
                    )
                    VALUES (
                        'transition_01j00000000000000000000001',
                        'ord_01j00000000000000000000001',
                        NULL,
                        'created',
                        '2026-07-29T12:08:00Z',
                        'evt_01j00000000000000000000005',
                        'intent_created',
                        0,
                        1
                    )
                    """
                )
            )
            inserted_transition = (
                await connection.execute(
                    text(
                        """
                        SELECT created_at IS NOT NULL, current_status = 'created'
                        FROM pmrp_execution.order_state_transitions
                        WHERE transition_id = 'transition_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            return (
                intent_table_exists,
                intent_primary_key_columns,
                intent_check_constraint_names,
                intent_unique_constraint_names,
                intent_index_names,
                intent_index_descending,
                tuple(str(signal_id) for signal_id in inserted_intent[0]),
                _numeric_18_text(inserted_intent[1]),
                order_table_exists,
                order_primary_key_columns,
                order_check_constraint_names,
                order_unique_constraint_names,
                order_index_names,
                order_strategy_index_partial,
                order_active_index_partial,
                int(inserted_order[0]),
                _numeric_18_text(inserted_order[1]),
                _numeric_18_text(inserted_order[2]),
                _numeric_18_text(inserted_order[3]),
                transition_table_exists,
                transition_primary_key_columns,
                transition_foreign_key_names,
                transition_unique_constraint_names,
                transition_index_names,
                bool(inserted_transition[0]),
                bool(inserted_transition[1]),
            )
    finally:
        await engine.dispose()


async def _assert_order_storage_constraints() -> None:
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_execution.order_intents (
            intent_id,
            strategy_id,
            market_id,
            contract_id,
            outcome_id,
            side,
            quantity,
            order_type,
            time_in_force,
            post_only,
            reduce_only,
            created_at,
            correlation_id,
            idempotency_key,
            payload_hash
        )
        VALUES (
            'intent_01j00000000000000000000002',
            'strat_fed_value_v1',
            'mkt_01j00000000000000000000001',
            'ctr_01j00000000000000000000001',
            'out_01j00000000000000000000001',
            'buy',
            1.000000000000000000,
            'limit',
            'gtc',
            false,
            false,
            '2026-07-29T12:09:00Z',
            'corr_01j00000000000000000000001',
            'intent-key-2',
            'sha256:order-intent-invalid'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_execution.order_intents (
            intent_id,
            strategy_id,
            market_id,
            contract_id,
            outcome_id,
            side,
            quantity,
            limit_price,
            order_type,
            time_in_force,
            post_only,
            reduce_only,
            created_at,
            correlation_id,
            idempotency_key,
            payload_hash
        )
        VALUES (
            'intent_01j00000000000000000000003',
            'strat_fed_value_v1',
            'mkt_01j00000000000000000000001',
            'ctr_01j00000000000000000000001',
            'out_01j00000000000000000000001',
            'buy',
            1.000000000000000000,
            0.420000000000000000,
            'limit',
            'gtc',
            false,
            false,
            '2026-07-29T12:09:00Z',
            'corr_01j00000000000000000000001',
            'intent-key-1',
            'sha256:order-intent-duplicate'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_execution.orders (
            order_id,
            exchange,
            account_id,
            market_id,
            contract_id,
            outcome_id,
            side,
            quantity,
            filled_quantity,
            remaining_quantity,
            order_type,
            time_in_force,
            post_only,
            reduce_only,
            status,
            client_order_id,
            created_at,
            last_updated_at
        )
        VALUES (
            'ord_01j00000000000000000000002',
            'kalshi',
            'acct_01j00000000000000000000001',
            'mkt_01j00000000000000000000001',
            'ctr_01j00000000000000000000001',
            'out_01j00000000000000000000001',
            'buy',
            10.000000000000000000,
            2.000000000000000000,
            7.000000000000000000,
            'limit',
            'gtc',
            false,
            false,
            'created',
            'client-order-2',
            '2026-07-29T12:09:00Z',
            '2026-07-29T12:09:00Z'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_execution.order_state_transitions (
            transition_id,
            order_id,
            current_status,
            occurred_at,
            source_event_id,
            aggregate_version_before,
            aggregate_version_after
        )
        VALUES (
            'transition_01j00000000000000000000002',
            'ord_missing',
            'created',
            '2026-07-29T12:09:00Z',
            'evt_01j00000000000000000000005',
            0,
            1
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_execution.order_state_transitions (
            transition_id,
            order_id,
            current_status,
            occurred_at,
            source_event_id,
            aggregate_version_before,
            aggregate_version_after
        )
        VALUES (
            'transition_01j00000000000000000000003',
            'ord_01j00000000000000000000001',
            'accepted',
            '2026-07-29T12:10:00Z',
            'evt_01j00000000000000000000006',
            1,
            1
        )
        """
    )


async def _fills_registry_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    bool,
    tuple[str, ...],
    bool,
    str,
    str,
    str,
    str,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    bool,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            fill_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_execution",
                table_name="fills",
            )
            fill_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_execution.fills",
            )
            fill_check_constraint_names = await _check_constraint_names(
                connection,
                "pmrp_execution.fills",
            )
            fill_partitioned = await _partitioned_table_exists(
                connection,
                "pmrp_execution.fills",
            )
            fill_index_names = await _index_names(
                connection,
                schema_name="pmrp_execution",
                table_name="fills",
                expected_names=("ix_fills__account_time", "ix_fills__order_time"),
            )
            fill_account_index_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%exchange_occurred_at DESC%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_execution'
                              AND tablename = 'fills'
                              AND indexname = 'ix_fills__account_time'
                            """
                        )
                    )
                ).scalar_one()
            )
            fill_id_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_execution",
                table_name="fill_ids",
            )
            fill_id_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_execution.fill_ids",
            )
            fill_id_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_execution.fill_ids",
                constraint_type="u",
            )

            await _create_fill_test_partition(connection)
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_execution.fills (
                        exchange_occurred_at,
                        fill_id,
                        exchange_fill_id,
                        order_id,
                        exchange_order_id,
                        client_order_id,
                        exchange,
                        account_id,
                        market_id,
                        contract_id,
                        outcome_id,
                        side,
                        price,
                        quantity,
                        liquidity_role,
                        fee_amount,
                        fee_currency,
                        rebate_amount,
                        rebate_currency,
                        received_at,
                        trade_id,
                        source_event_id
                    )
                    VALUES (
                        '2026-07-29T12:11:00Z',
                        'fill_01j00000000000000000000001',
                        'exchange-fill-1',
                        'ord_01j00000000000000000000001',
                        'exchange-order-1',
                        'client-order-1',
                        'kalshi',
                        'acct_01j00000000000000000000001',
                        'mkt_01j00000000000000000000001',
                        'ctr_01j00000000000000000000001',
                        'out_01j00000000000000000000001',
                        'buy',
                        0.420000000000000000,
                        2.500000000000000000,
                        'taker',
                        0.010000000000000000,
                        'USD',
                        0.005000000000000000,
                        'USD',
                        '2026-07-29T12:11:00.100000Z',
                        'trd_01j00000000000000000000001',
                        'evt_01j00000000000000000000007'
                    )
                    """
                )
            )
            inserted_fill = (
                await connection.execute(
                    text(
                        """
                        SELECT price, quantity, fee_amount, rebate_amount
                        FROM pmrp_execution.fills
                        WHERE fill_id = 'fill_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_execution.fill_ids (
                        exchange,
                        account_id,
                        exchange_fill_id,
                        fill_id,
                        exchange_occurred_at
                    )
                    VALUES (
                        'kalshi',
                        'acct_01j00000000000000000000001',
                        'exchange-fill-1',
                        'fill_01j00000000000000000000001',
                        '2026-07-29T12:11:00Z'
                    )
                    """
                )
            )
            inserted_fill_id = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT created_at IS NOT NULL
                            FROM pmrp_execution.fill_ids
                            WHERE exchange = 'kalshi'
                              AND account_id = 'acct_01j00000000000000000000001'
                              AND exchange_fill_id = 'exchange-fill-1'
                            """
                        )
                    )
                ).scalar_one()
            )
            return (
                fill_table_exists,
                fill_primary_key_columns,
                fill_check_constraint_names,
                fill_partitioned,
                fill_index_names,
                fill_account_index_descending,
                _numeric_18_text(inserted_fill[0]),
                _numeric_18_text(inserted_fill[1]),
                _numeric_18_text(inserted_fill[2]),
                _numeric_18_text(inserted_fill[3]),
                fill_id_table_exists,
                fill_id_primary_key_columns,
                fill_id_unique_constraint_names,
                inserted_fill_id,
            )
    finally:
        await engine.dispose()


async def _assert_fills_registry_constraints() -> None:
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_execution.fills (
            exchange_occurred_at,
            fill_id,
            exchange_fill_id,
            order_id,
            client_order_id,
            exchange,
            account_id,
            market_id,
            contract_id,
            outcome_id,
            side,
            price,
            quantity,
            liquidity_role,
            received_at,
            source_event_id
        )
        VALUES (
            '2026-07-29T12:12:00Z',
            'fill_01j00000000000000000000002',
            'exchange-fill-invalid',
            'ord_01j00000000000000000000001',
            'client-order-1',
            'kalshi',
            'acct_01j00000000000000000000001',
            'mkt_01j00000000000000000000001',
            'ctr_01j00000000000000000000001',
            'out_01j00000000000000000000001',
            'buy',
            0.420000000000000000,
            0.000000000000000000,
            'taker',
            '2026-07-29T12:12:00.100000Z',
            'evt_01j00000000000000000000007'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_execution.fill_ids (
            exchange,
            account_id,
            exchange_fill_id,
            fill_id,
            exchange_occurred_at
        )
        VALUES (
            'kalshi',
            'acct_01j00000000000000000000001',
            'exchange-fill-duplicate',
            'fill_01j00000000000000000000001',
            '2026-07-29T12:12:00Z'
        )
        """
    )


async def _portfolio_storage_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    int,
    str,
    str,
    str,
    str,
    str,
    str,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    int,
    str,
    str,
    str,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    str,
    str,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            position_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_portfolio",
                table_name="positions",
            )
            position_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_portfolio.positions",
            )
            position_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_portfolio.positions",
                constraint_type="u",
            )
            position_index_names = await _index_names(
                connection,
                schema_name="pmrp_portfolio",
                table_name="positions",
                expected_names=("ix_positions__account_market",),
            )
            cash_balance_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_portfolio",
                table_name="cash_balances",
            )
            cash_balance_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_portfolio.cash_balances",
            )
            cash_balance_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_portfolio.cash_balances",
                constraint_type="u",
            )
            cash_balance_check_constraint_names = await _check_constraint_names(
                connection,
                "pmrp_portfolio.cash_balances",
            )
            journal_entry_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_portfolio",
                table_name="journal_entries",
            )
            journal_entry_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_portfolio.journal_entries",
            )
            journal_entry_unique_constraint_names = await _constraint_names(
                connection,
                "pmrp_portfolio.journal_entries",
                constraint_type="u",
            )
            journal_entry_index_names = await _index_names(
                connection,
                schema_name="pmrp_portfolio",
                table_name="journal_entries",
                expected_names=("ix_journal_entries__reference",),
            )
            journal_line_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_portfolio",
                table_name="journal_lines",
            )
            journal_line_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_portfolio.journal_lines",
            )
            journal_line_foreign_key_names = await _constraint_names(
                connection,
                "pmrp_portfolio.journal_lines",
                constraint_type="f",
            )
            journal_line_index_names = await _index_names(
                connection,
                schema_name="pmrp_portfolio",
                table_name="journal_lines",
                expected_names=("ix_journal_lines__account_currency",),
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_portfolio.positions (
                        position_id,
                        exchange,
                        account_id,
                        market_id,
                        contract_id,
                        outcome_id,
                        quantity,
                        average_entry_price,
                        currency,
                        opened_at,
                        last_updated_at
                    )
                    VALUES (
                        'pos_01j00000000000000000000001',
                        'kalshi',
                        'acct_01j00000000000000000000001',
                        'mkt_01j00000000000000000000001',
                        'ctr_01j00000000000000000000001',
                        'out_01j00000000000000000000001',
                        5.000000000000000000,
                        0.420000000000000000,
                        'USD',
                        '2026-07-29T12:13:00Z',
                        '2026-07-29T12:13:00Z'
                    )
                    """
                )
            )
            inserted_position = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            aggregate_version,
                            quantity,
                            average_entry_price,
                            realized_pnl_amount,
                            unrealized_pnl_amount,
                            fees_paid_amount,
                            rebates_received_amount
                        FROM pmrp_portfolio.positions
                        WHERE position_id = 'pos_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_portfolio.cash_balances (
                        balance_id,
                        exchange,
                        account_id,
                        currency,
                        available,
                        reserved,
                        total,
                        captured_at
                    )
                    VALUES (
                        'bal_01j00000000000000000000001',
                        'kalshi',
                        'acct_01j00000000000000000000001',
                        'USD',
                        990.000000000000000000,
                        10.000000000000000000,
                        1000.000000000000000000,
                        '2026-07-29T12:13:00Z'
                    )
                    """
                )
            )
            inserted_cash_balance = (
                await connection.execute(
                    text(
                        """
                        SELECT aggregate_version, available, reserved, total
                        FROM pmrp_portfolio.cash_balances
                        WHERE balance_id = 'bal_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_portfolio.journal_entries (
                        journal_entry_id,
                        occurred_at,
                        source_event_id,
                        reference_type,
                        reference_id,
                        description
                    )
                    VALUES (
                        'journal_01j00000000000000000000001',
                        '2026-07-29T12:13:00Z',
                        'evt_01j00000000000000000000008',
                        'fill',
                        'fill_01j00000000000000000000001',
                        'Record fill accounting lines'
                    )
                    """
                )
            )
            inserted_journal_entry_created_at = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT created_at IS NOT NULL
                            FROM pmrp_portfolio.journal_entries
                            WHERE journal_entry_id = 'journal_01j00000000000000000000001'
                            """
                        )
                    )
                ).scalar_one()
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_portfolio.journal_lines (
                        journal_entry_id,
                        line_number,
                        account_code,
                        amount,
                        currency,
                        description
                    )
                    VALUES
                    (
                        'journal_01j00000000000000000000001',
                        1,
                        'contracts',
                        2.100000000000000000,
                        'USD',
                        'Increase contract asset'
                    ),
                    (
                        'journal_01j00000000000000000000001',
                        2,
                        'cash',
                        -2.100000000000000000,
                        'USD',
                        'Decrease cash'
                    )
                    """
                )
            )
            inserted_journal_lines = (
                await connection.execute(
                    text(
                        """
                        SELECT amount
                        FROM pmrp_portfolio.journal_lines
                        WHERE journal_entry_id = 'journal_01j00000000000000000000001'
                        ORDER BY line_number
                        """
                    )
                )
            ).all()
            return (
                position_table_exists,
                position_primary_key_columns,
                position_unique_constraint_names,
                position_index_names,
                int(inserted_position[0]),
                _numeric_18_text(inserted_position[1]),
                _numeric_18_text(inserted_position[2]),
                _numeric_18_text(inserted_position[3]),
                _numeric_18_text(inserted_position[4]),
                _numeric_18_text(inserted_position[5]),
                _numeric_18_text(inserted_position[6]),
                cash_balance_table_exists,
                cash_balance_primary_key_columns,
                cash_balance_unique_constraint_names,
                cash_balance_check_constraint_names,
                int(inserted_cash_balance[0]),
                _numeric_18_text(inserted_cash_balance[1]),
                _numeric_18_text(inserted_cash_balance[2]),
                _numeric_18_text(inserted_cash_balance[3]),
                journal_entry_table_exists,
                journal_entry_primary_key_columns,
                journal_entry_unique_constraint_names,
                journal_entry_index_names,
                inserted_journal_entry_created_at,
                journal_line_table_exists,
                journal_line_primary_key_columns,
                journal_line_foreign_key_names,
                journal_line_index_names,
                _numeric_18_text(inserted_journal_lines[0][0]),
                _numeric_18_text(inserted_journal_lines[1][0]),
            )
    finally:
        await engine.dispose()


async def _assert_portfolio_storage_constraints() -> None:
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_portfolio.positions (
            position_id,
            exchange,
            account_id,
            market_id,
            contract_id,
            outcome_id,
            quantity,
            currency,
            last_updated_at
        )
        VALUES (
            'pos_01j00000000000000000000002',
            'kalshi',
            'acct_01j00000000000000000000001',
            'mkt_01j00000000000000000000001',
            'ctr_01j00000000000000000000001',
            'out_01j00000000000000000000001',
            1.000000000000000000,
            'USD',
            '2026-07-29T12:14:00Z'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_portfolio.cash_balances (
            balance_id,
            exchange,
            account_id,
            currency,
            available,
            reserved,
            total,
            captured_at
        )
        VALUES (
            'bal_01j00000000000000000000002',
            'kalshi',
            'acct_01j00000000000000000000002',
            'USD',
            5.000000000000000000,
            2.000000000000000000,
            10.000000000000000000,
            '2026-07-29T12:14:00Z'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_portfolio.journal_entries (
            journal_entry_id,
            occurred_at,
            source_event_id,
            reference_type,
            reference_id,
            description
        )
        VALUES (
            'journal_01j00000000000000000000002',
            '2026-07-29T12:14:00Z',
            'evt_01j00000000000000000000008',
            'fill',
            'fill_01j00000000000000000000001',
            'Duplicate event journal'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_portfolio.journal_lines (
            journal_entry_id,
            line_number,
            account_code,
            amount,
            currency
        )
        VALUES (
            'journal_missing',
            1,
            'cash',
            1.000000000000000000,
            'USD'
        )
        """
    )


async def _pnl_settlements_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    str,
    str,
    str,
    str,
    str,
    str,
    str,
    bool,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    bool,
    tuple[str, ...],
    bool,
    str,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            pnl_attribution_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_portfolio",
                table_name="pnl_attributions",
            )
            pnl_attribution_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_portfolio.pnl_attributions",
            )
            pnl_attribution_index_names = await _index_names(
                connection,
                schema_name="pmrp_portfolio",
                table_name="pnl_attributions",
                expected_names=("ix_pnl_attributions__strategy_period",),
            )
            settlement_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_portfolio",
                table_name="settlements",
            )
            settlement_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_portfolio.settlements",
            )
            settlement_foreign_key_names = await _constraint_names(
                connection,
                "pmrp_portfolio.settlements",
                constraint_type="f",
            )
            settlement_index_names = await _index_names(
                connection,
                schema_name="pmrp_portfolio",
                table_name="settlements",
                expected_names=("ix_settlements__market_created",),
            )
            settlement_market_index_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%created_at DESC%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_portfolio'
                              AND tablename = 'settlements'
                              AND indexname = 'ix_settlements__market_created'
                            """
                        )
                    )
                ).scalar_one()
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_portfolio.pnl_attributions (
                        attribution_id,
                        strategy_id,
                        market_id,
                        exchange,
                        starts_at,
                        ends_at,
                        currency,
                        realized_trading_pnl,
                        unrealized_pnl_change,
                        fees,
                        rebates,
                        slippage,
                        settlement_pnl,
                        total_pnl,
                        calculation_version
                    )
                    VALUES (
                        'pnl_01j00000000000000000000001',
                        'strat_fed_value_v1',
                        'mkt_01j00000000000000000000001',
                        'kalshi',
                        '2026-07-29T00:00:00Z',
                        '2026-07-30T00:00:00Z',
                        'USD',
                        1.250000000000000000,
                        0.100000000000000000,
                        0.010000000000000000,
                        0.005000000000000000,
                        0.020000000000000000,
                        0.500000000000000000,
                        1.825000000000000000,
                        'weighted-average-v1'
                    )
                    """
                )
            )
            inserted_pnl_attribution = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            realized_trading_pnl,
                            unrealized_pnl_change,
                            fees,
                            rebates,
                            slippage,
                            settlement_pnl,
                            total_pnl,
                            created_at IS NOT NULL
                        FROM pmrp_portfolio.pnl_attributions
                        WHERE attribution_id = 'pnl_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_portfolio.settlements (
                        settlement_id,
                        market_id,
                        exchange,
                        status,
                        source
                    )
                    VALUES (
                        'settle_01j00000000000000000000001',
                        'mkt_01j00000000000000000000001',
                        'kalshi',
                        'pending',
                        'exchange'
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_portfolio.settlements (
                        settlement_id,
                        market_id,
                        exchange,
                        status,
                        winning_outcome_ids,
                        resolved_at,
                        finalized_at,
                        settled_at,
                        payout_per_unit,
                        source,
                        source_reference,
                        correction_of_settlement_id
                    )
                    VALUES (
                        'settle_01j00000000000000000000002',
                        'mkt_01j00000000000000000000001',
                        'kalshi',
                        'finalized',
                        ARRAY['out_01j00000000000000000000001']::text[],
                        '2026-07-29T12:15:00Z',
                        '2026-07-29T12:16:00Z',
                        '2026-07-29T12:17:00Z',
                        1.000000000000000000,
                        'operator',
                        'manual-correction-1',
                        'settle_01j00000000000000000000001'
                    )
                    """
                )
            )
            inserted_settlement = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            winning_outcome_ids,
                            created_at IS NOT NULL,
                            payout_per_unit
                        FROM pmrp_portfolio.settlements
                        WHERE settlement_id = 'settle_01j00000000000000000000002'
                        """
                    )
                )
            ).one()
            return (
                pnl_attribution_table_exists,
                pnl_attribution_primary_key_columns,
                pnl_attribution_index_names,
                _numeric_18_text(inserted_pnl_attribution[0]),
                _numeric_18_text(inserted_pnl_attribution[1]),
                _numeric_18_text(inserted_pnl_attribution[2]),
                _numeric_18_text(inserted_pnl_attribution[3]),
                _numeric_18_text(inserted_pnl_attribution[4]),
                _numeric_18_text(inserted_pnl_attribution[5]),
                _numeric_18_text(inserted_pnl_attribution[6]),
                bool(inserted_pnl_attribution[7]),
                settlement_table_exists,
                settlement_primary_key_columns,
                settlement_foreign_key_names,
                settlement_index_names,
                settlement_market_index_descending,
                tuple(str(outcome_id) for outcome_id in inserted_settlement[0]),
                bool(inserted_settlement[1]),
                _numeric_18_text(inserted_settlement[2]),
            )
    finally:
        await engine.dispose()


async def _assert_pnl_settlements_constraints() -> None:
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_portfolio.settlements (
            settlement_id,
            market_id,
            exchange,
            status,
            source,
            correction_of_settlement_id
        )
        VALUES (
            'settle_01j00000000000000000000003',
            'mkt_01j00000000000000000000001',
            'kalshi',
            'corrected',
            'operator',
            'settle_missing'
        )
        """
    )


async def _risk_storage_state() -> tuple[
    bool,
    tuple[str, ...],
    tuple[str, ...],
    bool,
    bool,
    int,
    str,
    bool,
    tuple[str, ...],
    bool,
    tuple[str, ...],
    bool,
    str,
    str,
    bool,
    bool,
    tuple[str, ...],
    tuple[str, ...],
    bool,
    bool,
    str,
    str,
]:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.begin() as connection:
            risk_limit_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_risk",
                table_name="risk_limits",
            )
            risk_limit_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_risk.risk_limits",
            )
            risk_limit_index_names = await _index_names(
                connection,
                schema_name="pmrp_risk",
                table_name="risk_limits",
                expected_names=("ix_risk_limits__active_scope",),
            )
            risk_limit_active_index_partial = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%WHERE (enabled = true)%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_risk'
                              AND tablename = 'risk_limits'
                              AND indexname = 'ix_risk_limits__active_scope'
                            """
                        )
                    )
                ).scalar_one()
            )
            risk_decision_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_risk",
                table_name="risk_decisions",
            )
            risk_decision_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_risk.risk_decisions",
            )
            risk_decision_partitioned = await _partitioned_table_exists(
                connection,
                "pmrp_risk.risk_decisions",
            )
            risk_decision_index_names = await _index_names(
                connection,
                schema_name="pmrp_risk",
                table_name="risk_decisions",
                expected_names=(
                    "ix_risk_decisions__intent",
                    "ix_risk_decisions__status_time",
                ),
            )
            risk_decision_status_index_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%evaluated_at DESC%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_risk'
                              AND tablename = 'risk_decisions'
                              AND indexname = 'ix_risk_decisions__status_time'
                            """
                        )
                    )
                ).scalar_one()
            )
            risk_breach_table_exists = await _table_exists(
                connection,
                schema_name="pmrp_risk",
                table_name="risk_breaches",
            )
            risk_breach_primary_key_columns = await _primary_key_columns(
                connection,
                "pmrp_risk.risk_breaches",
            )
            risk_breach_index_names = await _index_names(
                connection,
                schema_name="pmrp_risk",
                table_name="risk_breaches",
                expected_names=("ix_risk_breaches__open_severity",),
            )
            risk_breach_open_index_partial = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%WHERE (resolved_at IS NULL)%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_risk'
                              AND tablename = 'risk_breaches'
                              AND indexname = 'ix_risk_breaches__open_severity'
                            """
                        )
                    )
                ).scalar_one()
            )
            risk_breach_open_index_descending = bool(
                (
                    await connection.execute(
                        text(
                            """
                            SELECT indexdef LIKE '%detected_at DESC%'
                            FROM pg_indexes
                            WHERE schemaname = 'pmrp_risk'
                              AND tablename = 'risk_breaches'
                              AND indexname = 'ix_risk_breaches__open_severity'
                            """
                        )
                    )
                ).scalar_one()
            )

            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_risk.risk_limits (
                        risk_limit_id,
                        rule_id,
                        rule_version,
                        scope,
                        scope_id,
                        limit_type,
                        limit_value,
                        unit,
                        effective_at,
                        enabled,
                        created_by
                    )
                    VALUES (
                        'risk_limit_01j00000000000000000000001',
                        'max_position',
                        'v1',
                        'account',
                        'acct_01j00000000000000000000001',
                        'quantity',
                        100.000000000000000000,
                        'contracts',
                        '2026-07-29T12:18:00Z',
                        true,
                        'operator'
                    )
                    """
                )
            )
            inserted_risk_limit = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            created_at IS NOT NULL,
                            aggregate_version,
                            limit_value
                        FROM pmrp_risk.risk_limits
                        WHERE risk_limit_id = 'risk_limit_01j00000000000000000000001'
                        """
                    )
                )
            ).one()

            await _create_risk_decision_test_partition(connection)
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_risk.risk_decisions (
                        evaluated_at,
                        risk_decision_id,
                        intent_id,
                        status,
                        input_snapshot_id,
                        approved_quantity,
                        approved_limit_price,
                        approval_expires_at,
                        configuration_hash,
                        correlation_id,
                        rule_results,
                        payload_hash
                    )
                    VALUES (
                        '2026-07-29T12:18:00Z',
                        'rdec_01j00000000000000000000001',
                        'intent_01j00000000000000000000001',
                        'approved',
                        'risk_input_01j00000000000000000000001',
                        10.000000000000000000,
                        0.420000000000000000,
                        '2026-07-29T12:19:00Z',
                        'sha256:risk-config',
                        'corr_01j00000000000000000000001',
                        '[{"rule_id": "max_position", "passed": true}]'::jsonb,
                        'sha256:risk-decision'
                    )
                    """
                )
            )
            inserted_risk_decision = (
                await connection.execute(
                    text(
                        """
                        SELECT
                            approved_quantity,
                            approved_limit_price,
                            rule_results @> '[{"rule_id": "max_position", "passed": true}]'::jsonb
                        FROM pmrp_risk.risk_decisions
                        WHERE risk_decision_id = 'rdec_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO pmrp_risk.risk_breaches (
                        breach_id,
                        rule_id,
                        rule_version,
                        scope,
                        scope_id,
                        severity,
                        detected_at,
                        observed_value,
                        limit_value,
                        unit,
                        action_taken,
                        correlation_id
                    )
                    VALUES (
                        'breach_01j00000000000000000000001',
                        'max_position',
                        'v1',
                        'account',
                        'acct_01j00000000000000000000001',
                        'high',
                        '2026-07-29T12:18:30Z',
                        125.000000000000000000,
                        100.000000000000000000,
                        'contracts',
                        'blocked',
                        'corr_01j00000000000000000000001'
                    )
                    """
                )
            )
            inserted_risk_breach = (
                await connection.execute(
                    text(
                        """
                        SELECT observed_value, limit_value
                        FROM pmrp_risk.risk_breaches
                        WHERE breach_id = 'breach_01j00000000000000000000001'
                        """
                    )
                )
            ).one()
            return (
                risk_limit_table_exists,
                risk_limit_primary_key_columns,
                risk_limit_index_names,
                risk_limit_active_index_partial,
                bool(inserted_risk_limit[0]),
                int(inserted_risk_limit[1]),
                _numeric_18_text(inserted_risk_limit[2]),
                risk_decision_table_exists,
                risk_decision_primary_key_columns,
                risk_decision_partitioned,
                risk_decision_index_names,
                risk_decision_status_index_descending,
                _numeric_18_text(inserted_risk_decision[0]),
                _numeric_18_text(inserted_risk_decision[1]),
                bool(inserted_risk_decision[2]),
                risk_breach_table_exists,
                risk_breach_primary_key_columns,
                risk_breach_index_names,
                risk_breach_open_index_partial,
                risk_breach_open_index_descending,
                _numeric_18_text(inserted_risk_breach[0]),
                _numeric_18_text(inserted_risk_breach[1]),
            )
    finally:
        await engine.dispose()


async def _assert_risk_storage_constraints() -> None:
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_risk.risk_limits (
            risk_limit_id,
            rule_id,
            rule_version,
            scope,
            limit_type,
            unit,
            effective_at,
            enabled,
            created_by
        )
        VALUES (
            'risk_limit_01j00000000000000000000002',
            'max_position',
            'v1',
            'account',
            'quantity',
            'contracts',
            '2026-07-29T12:18:00Z',
            true,
            'operator'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_risk.risk_decisions (
            evaluated_at,
            risk_decision_id,
            intent_id,
            status,
            input_snapshot_id,
            configuration_hash,
            correlation_id,
            rule_results,
            payload_hash
        )
        VALUES (
            '2026-07-29T12:18:00Z',
            'rdec_01j00000000000000000000001',
            'intent_01j00000000000000000000001',
            'rejected',
            'risk_input_01j00000000000000000000002',
            'sha256:risk-config',
            'corr_01j00000000000000000000001',
            '[{"rule_id": "max_position", "passed": false}]'::jsonb,
            'sha256:risk-decision-duplicate'
        )
        """
    )
    await _assert_integrity_error(
        """
        INSERT INTO pmrp_risk.risk_breaches (
            breach_id,
            rule_id,
            rule_version,
            scope,
            severity,
            detected_at,
            correlation_id
        )
        VALUES (
            'breach_01j00000000000000000000002',
            'max_position',
            'v1',
            'account',
            'high',
            '2026-07-29T12:18:30Z',
            'corr_01j00000000000000000000001'
        )
        """
    )


async def _create_raw_exchange_record_test_partition(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pmrp_raw.exchange_records_2026_07
            PARTITION OF pmrp_raw.exchange_records
            FOR VALUES FROM ('2026-07-01T00:00:00Z') TO ('2026-08-01T00:00:00Z')
            """
        )
    )


async def _create_canonical_event_test_partition(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pmrp_event.canonical_events_2026_07
            PARTITION OF pmrp_event.canonical_events
            FOR VALUES FROM ('2026-07-01T00:00:00Z') TO ('2026-08-01T00:00:00Z')
            """
        )
    )


async def _create_trade_test_partition(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pmrp_market.trades_2026_07
            PARTITION OF pmrp_market.trades
            FOR VALUES FROM ('2026-07-01T00:00:00Z') TO ('2026-08-01T00:00:00Z')
            """
        )
    )


async def _create_signal_test_partition(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pmrp_research.signals_2026_07
            PARTITION OF pmrp_research.signals
            FOR VALUES FROM ('2026-07-01T00:00:00Z') TO ('2026-08-01T00:00:00Z')
            """
        )
    )


async def _create_feature_snapshot_test_partition(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pmrp_research.feature_snapshots_2026_07
            PARTITION OF pmrp_research.feature_snapshots
            FOR VALUES FROM ('2026-07-01T00:00:00Z') TO ('2026-08-01T00:00:00Z')
            """
        )
    )


async def _create_fill_test_partition(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pmrp_execution.fills_2026_07
            PARTITION OF pmrp_execution.fills
            FOR VALUES FROM ('2026-07-01T00:00:00Z') TO ('2026-08-01T00:00:00Z')
            """
        )
    )


async def _create_risk_decision_test_partition(connection: AsyncConnection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS pmrp_risk.risk_decisions_2026_07
            PARTITION OF pmrp_risk.risk_decisions
            FOR VALUES FROM ('2026-07-01T00:00:00Z') TO ('2026-08-01T00:00:00Z')
            """
        )
    )


async def _table_exists(
    connection: AsyncConnection,
    table_name: str,
    *,
    schema_name: str = "pmrp_core",
) -> bool:
    return bool(
        (
            await connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = :schema_name
                          AND table_name = :table_name
                    )
                    """
                ),
                {"schema_name": schema_name, "table_name": table_name},
            )
        ).scalar_one()
    )


async def _partitioned_table_exists(connection: AsyncConnection, table_name: str) -> bool:
    return bool(
        (
            await connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_partitioned_table
                        WHERE partrelid = CAST(:table_name AS regclass)
                          AND partstrat = 'r'
                    )
                    """
                ),
                {"table_name": table_name},
            )
        ).scalar_one()
    )


async def _primary_key_columns(connection: AsyncConnection, table_name: str) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in await connection.execute(
            text(
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a
                  ON a.attrelid = i.indrelid
                 AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = CAST(:table_name AS regclass)
                  AND i.indisprimary
                ORDER BY array_position(i.indkey, a.attnum)
                """
            ),
            {"table_name": table_name},
        )
    )


async def _check_constraint_names(connection: AsyncConnection, table_name: str) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in await connection.execute(
            text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = CAST(:table_name AS regclass)
                  AND contype = 'c'
                ORDER BY conname
                """
            ),
            {"table_name": table_name},
        )
    )


async def _constraint_names(
    connection: AsyncConnection,
    table_name: str,
    *,
    constraint_type: str,
) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in await connection.execute(
            text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = CAST(:table_name AS regclass)
                  AND contype::text = :constraint_type
                ORDER BY conname
                """
            ),
            {"table_name": table_name, "constraint_type": constraint_type},
        )
    )


async def _index_names(
    connection: AsyncConnection,
    *,
    schema_name: str,
    table_name: str,
    expected_names: tuple[str, ...],
) -> tuple[str, ...]:
    statement = text(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = :schema_name
          AND tablename = :table_name
          AND indexname IN :expected_names
        ORDER BY indexname
        """
    ).bindparams(bindparam("expected_names", expanding=True))
    result = await connection.execute(
        statement,
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "expected_names": expected_names,
        },
    )
    return tuple(str(row[0]) for row in result)


async def _assert_integrity_error(statement: str) -> None:
    engine = create_database_engine(
        database_config_from_environment(os.environ, fallback_url=None),
    )
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                with pytest.raises(IntegrityError):
                    await connection.execute(text(statement))
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


def _numeric_18_text(value: object) -> str:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return format(value, ".18f")


async def _schemas_for_connection(connection: AsyncConnection) -> tuple[str, ...]:
    statement = text(
        """
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name IN :schema_names
        ORDER BY schema_name
        """
    ).bindparams(bindparam("schema_names", expanding=True))
    result = await connection.execute(statement, {"schema_names": LOGICAL_SCHEMAS})
    found = {str(row[0]) for row in result}
    return tuple(schema_name for schema_name in LOGICAL_SCHEMAS if schema_name in found)
