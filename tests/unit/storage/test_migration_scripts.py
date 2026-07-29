"""Tests for committed Alembic migration scripts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.schema import CreateSchema, DropSchema

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INITIAL_MIGRATION_PATH = REPOSITORY_ROOT / "migrations/versions/0001_create_logical_schemas.py"
SCHEMA_REGISTRY_MIGRATION_PATH = (
    REPOSITORY_ROOT / "migrations/versions/0002_create_schema_registry.py"
)
EXCHANGE_REGISTRY_MIGRATION_PATH = (
    REPOSITORY_ROOT / "migrations/versions/0003_exchange_account_registries.py"
)
RAW_EXCHANGE_RECORDS_MIGRATION_PATH = (
    REPOSITORY_ROOT / "migrations/versions/0004_raw_exchange_records.py"
)
CANONICAL_EVENTS_MIGRATION_PATH = REPOSITORY_ROOT / "migrations/versions/0005_canonical_events.py"
PROCESSED_EVENTS_OUTBOX_MIGRATION_PATH = (
    REPOSITORY_ROOT / "migrations/versions/0006_processed_events_outbox.py"
)
IDEMPOTENCY_DEAD_LETTERS_MIGRATION_PATH = (
    REPOSITORY_ROOT / "migrations/versions/0007_idempotency_dead_letters.py"
)
MARKET_CATALOG_MIGRATION_PATH = (
    REPOSITORY_ROOT / "migrations/versions/0008_market_catalog_tables.py"
)
ORDER_BOOKS_TRADES_MIGRATION_PATH = (
    REPOSITORY_ROOT / "migrations/versions/0009_order_books_trades.py"
)
STRATEGY_MODEL_METADATA_MIGRATION_PATH = (
    REPOSITORY_ROOT / "migrations/versions/0010_strategy_model_metadata.py"
)
MAX_ALEMBIC_REVISION_ID_LENGTH = 32
EXPECTED_LOGICAL_SCHEMAS = (
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


@pytest.mark.unit
def test_initial_migration_revision_metadata_is_stable() -> None:
    migration = _load_initial_migration()

    assert migration.revision == "0001_create_logical_schemas"
    assert migration.down_revision is None
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_schema_registry_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(SCHEMA_REGISTRY_MIGRATION_PATH)

    assert migration.revision == "0002_create_schema_registry"
    assert migration.down_revision == "0001_create_logical_schemas"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_exchange_registry_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(EXCHANGE_REGISTRY_MIGRATION_PATH)

    assert migration.revision == "0003_exchange_account_registries"
    assert migration.down_revision == "0002_create_schema_registry"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_raw_exchange_records_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(RAW_EXCHANGE_RECORDS_MIGRATION_PATH)

    assert migration.revision == "0004_raw_exchange_records"
    assert migration.down_revision == "0003_exchange_account_registries"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_canonical_events_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(CANONICAL_EVENTS_MIGRATION_PATH)

    assert migration.revision == "0005_canonical_events"
    assert migration.down_revision == "0004_raw_exchange_records"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_processed_events_outbox_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(PROCESSED_EVENTS_OUTBOX_MIGRATION_PATH)

    assert migration.revision == "0006_processed_events_outbox"
    assert migration.down_revision == "0005_canonical_events"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_idempotency_dead_letters_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(IDEMPOTENCY_DEAD_LETTERS_MIGRATION_PATH)

    assert migration.revision == "0007_idempotency_dead_letters"
    assert migration.down_revision == "0006_processed_events_outbox"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_market_catalog_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(MARKET_CATALOG_MIGRATION_PATH)

    assert migration.revision == "0008_market_catalog_tables"
    assert migration.down_revision == "0007_idempotency_dead_letters"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_order_books_trades_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(ORDER_BOOKS_TRADES_MIGRATION_PATH)

    assert migration.revision == "0009_order_books_trades"
    assert migration.down_revision == "0008_market_catalog_tables"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
def test_strategy_model_metadata_migration_revision_metadata_is_stable() -> None:
    migration = _load_migration(STRATEGY_MODEL_METADATA_MIGRATION_PATH)

    assert migration.revision == "0010_strategy_model_metadata"
    assert migration.down_revision == "0009_order_books_trades"
    assert migration.branch_labels is None
    assert migration.depends_on is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "migration_path",
    [
        INITIAL_MIGRATION_PATH,
        SCHEMA_REGISTRY_MIGRATION_PATH,
        EXCHANGE_REGISTRY_MIGRATION_PATH,
        RAW_EXCHANGE_RECORDS_MIGRATION_PATH,
        CANONICAL_EVENTS_MIGRATION_PATH,
        PROCESSED_EVENTS_OUTBOX_MIGRATION_PATH,
        IDEMPOTENCY_DEAD_LETTERS_MIGRATION_PATH,
        MARKET_CATALOG_MIGRATION_PATH,
        ORDER_BOOKS_TRADES_MIGRATION_PATH,
        STRATEGY_MODEL_METADATA_MIGRATION_PATH,
    ],
)
def test_migration_revision_ids_fit_alembic_version_column(migration_path: Path) -> None:
    migration = _load_migration(migration_path)

    assert len(migration.revision) <= MAX_ALEMBIC_REVISION_ID_LENGTH


@pytest.mark.unit
def test_initial_migration_declares_expected_logical_schemas() -> None:
    migration = _load_initial_migration()

    assert migration.LOGICAL_SCHEMAS == EXPECTED_LOGICAL_SCHEMAS


@pytest.mark.unit
def test_initial_migration_upgrade_creates_extension_before_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_initial_migration()
    executed: list[object] = []

    monkeypatch.setattr(migration.op, "execute", executed.append)

    migration.upgrade()

    assert executed[0] == "CREATE EXTENSION IF NOT EXISTS pgcrypto"
    assert all(isinstance(statement, CreateSchema) for statement in executed[1:])
    create_schema_statements = [cast(CreateSchema, statement) for statement in executed[1:]]
    assert [
        (statement.element, statement.if_not_exists) for statement in create_schema_statements
    ] == [(schema_name, True) for schema_name in EXPECTED_LOGICAL_SCHEMAS]


@pytest.mark.unit
def test_initial_migration_downgrade_drops_schemas_in_reverse_without_cascade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_initial_migration()
    executed: list[object] = []

    monkeypatch.setattr(migration.op, "execute", executed.append)

    migration.downgrade()

    assert all(isinstance(statement, DropSchema) for statement in executed)
    drop_schema_statements = [cast(DropSchema, statement) for statement in executed]
    assert [(statement.element, statement.if_exists) for statement in drop_schema_statements] == [
        (schema_name, True) for schema_name in reversed(EXPECTED_LOGICAL_SCHEMAS)
    ]
    assert "DROP EXTENSION IF EXISTS pgcrypto" not in executed


@pytest.mark.unit
def test_schema_registry_migration_uses_expected_names() -> None:
    migration = _load_migration(SCHEMA_REGISTRY_MIGRATION_PATH)

    assert migration.SCHEMA_NAME == "pmrp_core"
    assert migration.TABLE_NAME == "schema_registry"
    assert migration.CATEGORY_INDEX_NAME == "ix_schema_registry__category"


@pytest.mark.unit
def test_schema_registry_migration_marks_check_constraint_name_as_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(SCHEMA_REGISTRY_MIGRATION_PATH)
    formatted_names: list[str] = []
    created_table_arguments: list[object] = []

    def fake_format_name(name: str) -> str:
        formatted_names.append(name)
        return f"final:{name}"

    def fake_create_table(*arguments: object, **_kwargs: object) -> None:
        created_table_arguments.extend(arguments)

    monkeypatch.setattr(migration.op, "f", fake_format_name)
    monkeypatch.setattr(migration.op, "create_table", fake_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)

    migration.upgrade()

    check_constraints = [
        argument for argument in created_table_arguments if isinstance(argument, CheckConstraint)
    ]
    assert formatted_names == ["ck_schema_registry__schema_version"]
    assert [constraint.name for constraint in check_constraints] == [
        "final:ck_schema_registry__schema_version"
    ]


@pytest.mark.unit
def test_exchange_registry_migration_uses_expected_names() -> None:
    migration = _load_migration(EXCHANGE_REGISTRY_MIGRATION_PATH)

    assert migration.SCHEMA_NAME == "pmrp_core"
    assert migration.EXCHANGES_TABLE_NAME == "exchanges"
    assert migration.EXCHANGE_ACCOUNTS_TABLE_NAME == "exchange_accounts"
    assert migration.EXCHANGE_ACCOUNT_INDEX_NAME == ("ix_exchange_accounts__exchange_environment")
    assert migration.EXCHANGE_ACCOUNT_FOREIGN_KEY_NAME == (
        "fk_exchange_accounts__exchange__exchanges"
    )


@pytest.mark.unit
def test_exchange_registry_migration_marks_foreign_key_name_as_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(EXCHANGE_REGISTRY_MIGRATION_PATH)
    formatted_names: list[str] = []
    created_table_arguments: list[object] = []

    def fake_format_name(name: str) -> str:
        formatted_names.append(name)
        return f"final:{name}"

    def fake_create_table(*arguments: object, **_kwargs: object) -> None:
        created_table_arguments.extend(arguments)

    monkeypatch.setattr(migration.op, "f", fake_format_name)
    monkeypatch.setattr(migration.op, "create_table", fake_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)

    migration.upgrade()

    foreign_key_constraints = [
        argument
        for argument in created_table_arguments
        if isinstance(argument, ForeignKeyConstraint)
    ]
    assert formatted_names == ["fk_exchange_accounts__exchange__exchanges"]
    assert [constraint.name for constraint in foreign_key_constraints] == [
        "final:fk_exchange_accounts__exchange__exchanges"
    ]


@pytest.mark.unit
def test_raw_exchange_records_migration_uses_expected_names() -> None:
    migration = _load_migration(RAW_EXCHANGE_RECORDS_MIGRATION_PATH)

    assert migration.SCHEMA_NAME == "pmrp_raw"
    assert migration.TABLE_NAME == "exchange_records"
    assert migration.EXCHANGE_RECEIVED_INDEX_NAME == "ix_exchange_records__exchange_received"
    assert migration.CHANNEL_RECEIVED_INDEX_NAME == "ix_exchange_records__channel_received"
    assert migration.PAYLOAD_HASH_INDEX_NAME == "ix_exchange_records__payload_hash"
    assert migration.PAYLOAD_STORAGE_CHECK_NAME == "ck_exchange_records__payload_storage"


@pytest.mark.unit
def test_raw_exchange_records_migration_marks_check_constraint_name_as_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(RAW_EXCHANGE_RECORDS_MIGRATION_PATH)
    formatted_names: list[str] = []
    created_table_arguments: list[object] = []

    def fake_format_name(name: str) -> str:
        formatted_names.append(name)
        return f"final:{name}"

    def fake_create_table(*arguments: object, **_kwargs: object) -> None:
        created_table_arguments.extend(arguments)

    monkeypatch.setattr(migration.op, "f", fake_format_name)
    monkeypatch.setattr(migration.op, "create_table", fake_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)

    migration.upgrade()

    check_constraints = [
        argument for argument in created_table_arguments if isinstance(argument, CheckConstraint)
    ]
    assert formatted_names == ["ck_exchange_records__payload_storage"]
    assert [constraint.name for constraint in check_constraints] == [
        "final:ck_exchange_records__payload_storage"
    ]


@pytest.mark.unit
def test_canonical_events_migration_uses_expected_names() -> None:
    migration = _load_migration(CANONICAL_EVENTS_MIGRATION_PATH)

    assert migration.SCHEMA_NAME == "pmrp_event"
    assert migration.EVENT_IDS_TABLE_NAME == "event_ids"
    assert migration.CANONICAL_EVENTS_TABLE_NAME == "canonical_events"
    assert migration.TYPE_TIME_INDEX_NAME == "ix_canonical_events__type_time"
    assert migration.MARKET_TIME_INDEX_NAME == "ix_canonical_events__market_time"
    assert migration.ORDER_TIME_INDEX_NAME == "ix_canonical_events__order_time"
    assert migration.CORRELATION_INDEX_NAME == "ix_canonical_events__correlation"
    assert migration.SCHEMA_VERSION_CHECK_NAME == "ck_canonical_events__schema_version"


@pytest.mark.unit
def test_canonical_events_migration_marks_check_constraint_name_as_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(CANONICAL_EVENTS_MIGRATION_PATH)
    formatted_names: list[str] = []
    created_table_arguments: list[object] = []

    def fake_format_name(name: str) -> str:
        formatted_names.append(name)
        return f"final:{name}"

    def fake_create_table(*arguments: object, **_kwargs: object) -> None:
        created_table_arguments.extend(arguments)

    monkeypatch.setattr(migration.op, "f", fake_format_name)
    monkeypatch.setattr(migration.op, "create_table", fake_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)

    migration.upgrade()

    check_constraints = [
        argument for argument in created_table_arguments if isinstance(argument, CheckConstraint)
    ]
    assert formatted_names == ["ck_canonical_events__schema_version"]
    assert [constraint.name for constraint in check_constraints] == [
        "final:ck_canonical_events__schema_version"
    ]


@pytest.mark.unit
def test_processed_events_outbox_migration_uses_expected_names() -> None:
    migration = _load_migration(PROCESSED_EVENTS_OUTBOX_MIGRATION_PATH)

    assert migration.SCHEMA_NAME == "pmrp_event"
    assert migration.PROCESSED_EVENTS_TABLE_NAME == "processed_events"
    assert migration.OUTBOX_MESSAGES_TABLE_NAME == "outbox_messages"
    assert migration.PROCESSED_EVENTS_TIME_INDEX_NAME == "ix_processed_events__time"
    assert migration.OUTBOX_PENDING_INDEX_NAME == "ix_outbox_messages__pending"
    assert migration.OUTBOX_EVENT_TOPIC_UNIQUE_NAME == "uq_outbox_messages__event_id_topic"


@pytest.mark.unit
def test_processed_events_outbox_migration_marks_unique_constraint_name_as_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(PROCESSED_EVENTS_OUTBOX_MIGRATION_PATH)
    formatted_names: list[str] = []
    created_table_arguments: list[object] = []

    def fake_format_name(name: str) -> str:
        formatted_names.append(name)
        return f"final:{name}"

    def fake_create_table(*arguments: object, **_kwargs: object) -> None:
        created_table_arguments.extend(arguments)

    monkeypatch.setattr(migration.op, "f", fake_format_name)
    monkeypatch.setattr(migration.op, "create_table", fake_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)

    migration.upgrade()

    unique_constraints = [
        argument for argument in created_table_arguments if isinstance(argument, UniqueConstraint)
    ]
    assert formatted_names == ["uq_outbox_messages__event_id_topic"]
    assert [constraint.name for constraint in unique_constraints] == [
        "final:uq_outbox_messages__event_id_topic"
    ]


@pytest.mark.unit
def test_idempotency_dead_letters_migration_uses_expected_names() -> None:
    migration = _load_migration(IDEMPOTENCY_DEAD_LETTERS_MIGRATION_PATH)

    assert migration.CORE_SCHEMA_NAME == "pmrp_core"
    assert migration.OPS_SCHEMA_NAME == "pmrp_ops"
    assert migration.IDEMPOTENCY_RECORDS_TABLE_NAME == "idempotency_records"
    assert migration.DEAD_LETTER_RECORDS_TABLE_NAME == "dead_letter_records"
    assert migration.IDEMPOTENCY_EXPIRES_INDEX_NAME == "ix_idempotency_records__expires"
    assert migration.DEAD_LETTER_UNRESOLVED_INDEX_NAME == ("ix_dead_letter_records__unresolved")


@pytest.mark.unit
def test_market_catalog_migration_uses_expected_names() -> None:
    migration = _load_migration(MARKET_CATALOG_MIGRATION_PATH)

    assert migration.SCHEMA_NAME == "pmrp_market"
    assert migration.MARKETS_TABLE_NAME == "markets"
    assert migration.OUTCOMES_TABLE_NAME == "outcomes"
    assert migration.CONTRACTS_TABLE_NAME == "contracts"
    assert migration.MARKETS_EXCHANGE_STATUS_INDEX_NAME == "ix_markets__exchange_status"
    assert migration.MARKETS_STATUS_CLOSES_INDEX_NAME == "ix_markets__status_closes"
    assert migration.MARKETS_UPDATED_INDEX_NAME == "ix_markets__updated"
    assert migration.OUTCOMES_MARKET_INDEX_NAME == "ix_outcomes__market"
    assert migration.CONTRACTS_MARKET_ACTIVE_INDEX_NAME == "ix_contracts__market_active"
    assert migration.MARKETS_PAYOUT_CHECK_NAME == "ck_markets__payout_per_unit"
    assert migration.MARKETS_TICK_SIZE_CHECK_NAME == "ck_markets__tick_size"
    assert migration.MARKETS_QUANTITY_INCREMENT_CHECK_NAME == ("ck_markets__quantity_increment")


@pytest.mark.unit
def test_market_catalog_migration_marks_constraint_names_as_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(MARKET_CATALOG_MIGRATION_PATH)
    formatted_names: list[str] = []
    created_table_arguments: list[object] = []

    def fake_format_name(name: str) -> str:
        formatted_names.append(name)
        return f"final:{name}"

    def fake_create_table(*arguments: object, **_kwargs: object) -> None:
        created_table_arguments.extend(arguments)

    monkeypatch.setattr(migration.op, "f", fake_format_name)
    monkeypatch.setattr(migration.op, "create_table", fake_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)

    migration.upgrade()

    final_constraint_names = [
        constraint.name
        for constraint in created_table_arguments
        if isinstance(constraint, CheckConstraint | ForeignKeyConstraint | UniqueConstraint)
    ]
    assert formatted_names == [
        "uq_markets__exchange_exchange_market_id",
        "ck_markets__payout_per_unit",
        "ck_markets__tick_size",
        "ck_markets__quantity_increment",
        "fk_outcomes__market_id__markets",
        "uq_outcomes__market_id_outcome_index",
        "uq_outcomes__market_id_normalized_name",
        "fk_contracts__market_id__markets",
        "fk_contracts__outcome_id__outcomes",
        "uq_contracts__market_id_outcome_id",
    ]
    assert final_constraint_names == [f"final:{name}" for name in formatted_names]


@pytest.mark.unit
def test_order_books_trades_migration_uses_expected_names() -> None:
    migration = _load_migration(ORDER_BOOKS_TRADES_MIGRATION_PATH)

    assert migration.SCHEMA_NAME == "pmrp_market"
    assert migration.ORDER_BOOK_SNAPSHOTS_TABLE_NAME == "order_book_snapshots"
    assert migration.TRADES_TABLE_NAME == "trades"
    assert migration.ORDER_BOOK_EXCHANGE_UPDATED_INDEX_NAME == (
        "ix_order_book_snapshots__exchange_updated"
    )
    assert migration.TRADES_MARKET_TIME_INDEX_NAME == "ix_trades__market_time"
    assert migration.TRADES_CONTRACT_TIME_INDEX_NAME == "ix_trades__contract_time"
    assert migration.ORDER_BOOK_MARKET_FOREIGN_KEY_NAME == (
        "fk_order_book_snapshots__market_id__markets"
    )
    assert migration.ORDER_BOOK_CONTRACT_FOREIGN_KEY_NAME == (
        "fk_order_book_snapshots__contract_id__contracts"
    )
    assert migration.TRADES_QUANTITY_CHECK_NAME == "ck_trades__quantity"


@pytest.mark.unit
def test_order_books_trades_migration_marks_constraint_names_as_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(ORDER_BOOKS_TRADES_MIGRATION_PATH)
    formatted_names: list[str] = []
    created_table_arguments: list[object] = []

    def fake_format_name(name: str) -> str:
        formatted_names.append(name)
        return f"final:{name}"

    def fake_create_table(*arguments: object, **_kwargs: object) -> None:
        created_table_arguments.extend(arguments)

    monkeypatch.setattr(migration.op, "f", fake_format_name)
    monkeypatch.setattr(migration.op, "create_table", fake_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)

    migration.upgrade()

    final_constraint_names = [
        constraint.name
        for constraint in created_table_arguments
        if isinstance(constraint, CheckConstraint | ForeignKeyConstraint)
    ]
    assert formatted_names == [
        "fk_order_book_snapshots__market_id__markets",
        "fk_order_book_snapshots__contract_id__contracts",
        "ck_trades__quantity",
    ]
    assert final_constraint_names == [f"final:{name}" for name in formatted_names]


@pytest.mark.unit
def test_strategy_model_metadata_migration_uses_expected_names() -> None:
    migration = _load_migration(STRATEGY_MODEL_METADATA_MIGRATION_PATH)

    assert migration.SCHEMA_NAME == "pmrp_research"
    assert migration.STRATEGY_DEFINITIONS_TABLE_NAME == "strategy_definitions"
    assert migration.STRATEGY_INSTANCES_TABLE_NAME == "strategy_instances"
    assert migration.STRATEGY_CONFIGURATIONS_TABLE_NAME == "strategy_configurations"
    assert migration.MODEL_ARTIFACTS_TABLE_NAME == "model_artifacts"
    assert migration.STRATEGY_INSTANCES_STATE_HEALTH_INDEX_NAME == (
        "ix_strategy_instances__state_health"
    )
    assert migration.MODEL_ARTIFACTS_APPROVAL_INDEX_NAME == "ix_model_artifacts__approval"
    assert migration.STRATEGY_INSTANCES_DEFINITION_FOREIGN_KEY_NAME == (
        "fk_strategy_instances__type_version__strategy_definitions"
    )
    assert migration.STRATEGY_CONFIGURATIONS_INSTANCE_FOREIGN_KEY_NAME == (
        "fk_strategy_configurations__strategy_id__strategy_instances"
    )
    assert migration.STRATEGY_CONFIGURATIONS_HASH_UNIQUE_NAME == (
        "uq_strategy_configurations__strategy_id_configuration_hash"
    )


@pytest.mark.unit
def test_strategy_model_metadata_migration_marks_constraint_names_as_final(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _load_migration(STRATEGY_MODEL_METADATA_MIGRATION_PATH)
    formatted_names: list[str] = []
    created_table_arguments: list[object] = []

    def fake_format_name(name: str) -> str:
        formatted_names.append(name)
        return f"final:{name}"

    def fake_create_table(*arguments: object, **_kwargs: object) -> None:
        created_table_arguments.extend(arguments)

    monkeypatch.setattr(migration.op, "f", fake_format_name)
    monkeypatch.setattr(migration.op, "create_table", fake_create_table)
    monkeypatch.setattr(migration.op, "create_index", lambda *_args, **_kwargs: None)

    migration.upgrade()

    final_constraint_names = [
        constraint.name
        for constraint in created_table_arguments
        if isinstance(constraint, ForeignKeyConstraint | UniqueConstraint)
    ]
    assert formatted_names == [
        "fk_strategy_instances__type_version__strategy_definitions",
        "fk_strategy_configurations__strategy_id__strategy_instances",
        "uq_strategy_configurations__strategy_id_configuration_hash",
    ]
    assert final_constraint_names == [f"final:{name}" for name in formatted_names]


def _load_initial_migration() -> ModuleType:
    return _load_migration(INITIAL_MIGRATION_PATH)


def _load_migration(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        path.stem,
        path,
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        msg = f"could not load Alembic migration: {path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
