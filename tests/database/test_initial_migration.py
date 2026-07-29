"""Database integration tests for the initial Alembic migration."""

from __future__ import annotations

import asyncio
import os
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
        "0008_market_catalog_tables",
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

    command.downgrade(alembic_config, "base")
    assert asyncio.run(_schemas()) == ()

    command.upgrade(alembic_config, "head")
    assert asyncio.run(_migration_state()) == (
        "0008_market_catalog_tables",
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
                  AND contype = :constraint_type
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
