# Prediction Market Research Platform
## Database Architecture and PostgreSQL Specification
- Document: `06_DATABASE.md`
- Version: 1.0
- Status: Governing database specification
- Related documents:
  - `01_ARCHITECTURE.md`
  - `02_ENGINEERING.md`
  - `03_SCHEMAS.md`
  - `04_IMPLEMENTATION.md`
  - `05_API_SPEC.md`
- Primary database: PostgreSQL
- ORM and migration tooling: SQLAlchemy and Alembic
- Async driver: asyncpg
- Character set: ASCII only
- Intended audience: database engineers, backend developers, reviewers, operators, and coding agents
---
## Document Authority
This document defines the physical and operational database design for PMRP.
It maps the canonical contracts in `03_SCHEMAS.md` into PostgreSQL structures.
It governs tables, keys, constraints, indexes, transactions, migrations,
partitioning, retention, backup, restore, security, and operational procedures.
# 1. Executive Summary
PostgreSQL is the initial system of record for PMRP.
The database stores raw exchange records, canonical events, market projections,
strategy metadata, signals, order intents, orders, fills, positions, balances,
risk records, replay sessions, simulation sessions, health records, and audit
history.
The database design is intentionally hybrid:
- append-only event and audit history
- mutable operational projections
- exact financial arithmetic using NUMERIC
- timezone-aware timestamps using TIMESTAMPTZ
- JSONB for versioned payloads and extensible metadata
- first-class columns for frequently queried fields
- range partitioning for high-volume time-series tables
- optimistic concurrency for mutable aggregates
- durable idempotency for commands, events, orders, and fills
- outbox publication for reliable event delivery
- tested backup and restore
# 2. Database Goals
The database must make it possible to determine exactly:
- what an exchange sent
- when it was received
- how it was normalized
- which canonical event was created
- which strategy produced a signal
- which signal produced an order intent
- which risk decision approved or rejected the intent
- which order request was sent
- which exchange acknowledgement was received
- which fills changed the position
- which journal entries changed accounting
- which reconciliation run validated account state
- which configuration and code version were active
The design must support both operational safety and reproducible research.
# 3. Non-Goals
The initial database is not a general-purpose data warehouse.
It is not intended to store large model binaries, replace object storage,
provide unrestricted SQL access, or serve as the direct programming interface
for strategies.
The initial architecture does not require one database per service.
# 4. PostgreSQL Baseline
Recommended baseline:
```text
PostgreSQL 16 or newer supported release
SQLAlchemy 2.x
Alembic
asyncpg
```
Required extension:
```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```
Recommended observability extension:
```sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```
Optional extensions require an ADR.
# 5. Logical Schemas
Recommended namespaces:
```text
pmrp_core
pmrp_raw
pmrp_event
pmrp_market
pmrp_execution
pmrp_portfolio
pmrp_risk
pmrp_research
pmrp_ops
pmrp_audit
```
Responsibilities:
```text
pmrp_core       registries, identities, idempotency
pmrp_raw        original exchange payloads
pmrp_event      canonical events, processed events, outbox
pmrp_market     markets, outcomes, contracts, market data
pmrp_execution  intents, orders, transitions, fills
pmrp_portfolio  positions, balances, journals, PnL, settlements
pmrp_risk       limits, decisions, breaches, kill switches, reservations
pmrp_research   strategies, models, replay, simulation, experiments, matching
pmrp_ops        health, reconciliation, dead letters, jobs
pmrp_audit      operator and configuration audit
```
# 6. Naming Standards
Use lowercase snake_case.
Naming patterns:
```text
pk_<table>
fk_<table>__<column>__<target>
uq_<table>__<columns>
ck_<table>__<rule>
ix_<table>__<columns>
```
Tables are plural. Canonical identifiers end in `_id`.
# 7. Type Mapping
Canonical-to-PostgreSQL mapping:
```text
Decimal              NUMERIC(38,18)
timezone datetime    TIMESTAMPTZ
identifier           TEXT
enum                  TEXT
immutable payload     JSONB
raw bytes             BYTEA
hash                  TEXT with algorithm prefix
sequence              BIGINT
boolean               BOOLEAN
```
Never use REAL, DOUBLE PRECISION, or PostgreSQL MONEY for canonical financial
values.
# 8. Time and Precision
All business timestamps use TIMESTAMPTZ.
The database session timezone should be UTC.
Financial values use NUMERIC. Construct and deserialize through Decimal.
Common checks:
```sql
CHECK (quantity >= 0)
CHECK (price >= 0)
CHECK (probability >= 0 AND probability <= 1)
```
# 9. JSONB Policy
Use JSONB for immutable event payloads, model metrics, extensible metadata,
redacted configuration, and structured results.
Do not hide frequently queried values only inside JSONB.
Fields such as event type, occurred time, exchange, market ID, order ID,
strategy ID, status, and account ID should be first-class columns.
# 10. Transaction Principles
Transactions must be short, explicit, and owned by application use cases.
Never hold a database transaction open while waiting for:
- an exchange network response
- WebSocket data
- object storage
- long model inference
- a sleep or retry backoff
Default isolation is READ COMMITTED.
Use optimistic concurrency, row locks, advisory locks, or SERIALIZABLE only
where a documented invariant requires them.
# 11. Idempotency Principles
Durable idempotency is required for:
- canonical event append
- consumer processing
- command handling
- order submission
- fill application
- reconciliation correction
- outbox publication
- import jobs
Idempotency keys must be scoped by subject and operation.
# 12. Partitioning Principles
Partition high-volume append-only tables by business or event time.
Initial interval:
```text
monthly
```
Candidates:
- raw exchange records
- canonical events
- trades
- fills
- signals
- feature snapshots
- risk decisions
- health snapshots
- audit records
Create future partitions before boundaries and archive closed partitions only
after checksum verification.
# 13. Common DDL Conventions
Every mutable aggregate should include:
```sql
aggregate_version bigint NOT NULL DEFAULT 0
```
Every durable record should include an explicit primary key.
Storage timestamps may use:
```sql
inserted_at timestamptz NOT NULL DEFAULT now()
```
Domain timestamps should be supplied by the application clock.
# 14. Schema Registry
Purpose:
Registers canonical schema names, versions, compatibility, and upcasters.
Physical table:
```text
pmrp_core.schema_registry
```
## Columns
```sql
CREATE TABLE pmrp_core.schema_registry (
    schema_name text NOT NULL,
    schema_version integer NOT NULL,
    schema_category text NOT NULL,
    python_model_path text NOT NULL,
    json_schema_uri text,
    introduced_in_platform_version text NOT NULL,
    deprecated_in_platform_version text,
    backward_compatible_with integer[] NOT NULL DEFAULT '{}',
    upcaster_paths text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (schema_name, schema_version),
    CHECK (schema_version >= 1)
);
```
## Indexes
```sql
CREATE INDEX ix_schema_registry__category ON pmrp_core.schema_registry (schema_category);
```
## Primary Query Patterns
- lookup a model by name and version
- list active schemas by category
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 15. Exchange Registry
Purpose:
Stores configured exchanges and declared capabilities without credentials.
Physical table:
```text
pmrp_core.exchanges
```
## Columns
```sql
CREATE TABLE pmrp_core.exchanges (
    exchange text NOT NULL,
    display_name text NOT NULL,
    enabled boolean NOT NULL DEFAULT false,
    capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz,
    PRIMARY KEY (exchange)
);
```
## Primary Query Patterns
- list enabled exchanges
- read capabilities
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 16. Exchange Accounts
Purpose:
Stores account references and environment metadata without secret material.
Physical table:
```text
pmrp_core.exchange_accounts
```
## Columns
```sql
CREATE TABLE pmrp_core.exchange_accounts (
    account_id text NOT NULL,
    exchange text NOT NULL,
    environment text NOT NULL,
    external_account_id text,
    enabled boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz,
    PRIMARY KEY (account_id),
    FOREIGN KEY (exchange) REFERENCES pmrp_core.exchanges (exchange)
);
```
## Indexes
```sql
CREATE INDEX ix_exchange_accounts__exchange_environment ON pmrp_core.exchange_accounts (exchange, environment);
```
## Primary Query Patterns
- resolve account by environment
- list enabled accounts
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 17. Raw Exchange Records
Purpose:
Preserves original exchange payloads and transport metadata before normalization.
Physical table:
```text
pmrp_raw.exchange_records
```
## Columns
```sql
CREATE TABLE pmrp_raw.exchange_records (
    received_at timestamptz NOT NULL,
    raw_record_id text NOT NULL,
    exchange text NOT NULL,
    environment text NOT NULL,
    connection_id text,
    endpoint text,
    channel text,
    message_type text,
    exchange_occurred_at timestamptz,
    sequence bigint,
    content_type text NOT NULL DEFAULT 'application/json',
    compression text,
    payload_text text,
    payload_bytes bytea,
    payload_hash text NOT NULL,
    parser_version text,
    transport_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    inserted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (received_at, raw_record_id),
    CHECK ((payload_text IS NOT NULL AND payload_bytes IS NULL) OR (payload_text IS NULL AND payload_bytes IS NOT NULL))
) PARTITION BY RANGE (received_at);
```
## Indexes
```sql
CREATE INDEX ix_exchange_records__exchange_received ON pmrp_raw.exchange_records (exchange, received_at);
CREATE INDEX ix_exchange_records__channel_received ON pmrp_raw.exchange_records (channel, received_at);
CREATE INDEX ix_exchange_records__payload_hash ON pmrp_raw.exchange_records (payload_hash);
```
## Primary Query Patterns
- stream by exchange and time range
- find by payload hash
- reprocess a channel
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 18. Canonical Events
Purpose:
Stores immutable versioned canonical events for replay and audit.
Physical table:
```text
pmrp_event.canonical_events
```
## Columns
```sql
CREATE TABLE pmrp_event.canonical_events (
    occurred_at timestamptz NOT NULL,
    event_id text NOT NULL,
    event_type text NOT NULL,
    schema_version integer NOT NULL,
    received_at timestamptz NOT NULL,
    published_at timestamptz NOT NULL,
    producer text NOT NULL,
    exchange text,
    market_id text,
    account_id text,
    strategy_id text,
    order_id text,
    correlation_id text NOT NULL,
    causation_id text,
    trace_id text,
    replay_session_id text,
    simulation_session_id text,
    quality_flags text[] NOT NULL DEFAULT '{}',
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    inserted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (occurred_at, event_id),
    CHECK (schema_version >= 1)
) PARTITION BY RANGE (occurred_at);
```
## Indexes
```sql
CREATE INDEX ix_canonical_events__type_time ON pmrp_event.canonical_events (event_type, occurred_at);
CREATE INDEX ix_canonical_events__market_time ON pmrp_event.canonical_events (market_id, occurred_at) WHERE market_id IS NOT NULL;
CREATE INDEX ix_canonical_events__order_time ON pmrp_event.canonical_events (order_id, occurred_at) WHERE order_id IS NOT NULL;
CREATE INDEX ix_canonical_events__correlation ON pmrp_event.canonical_events (correlation_id);
```
## Primary Query Patterns
- deterministic replay
- order lineage
- market history
- correlation chain
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 19. Global Event IDs
Purpose:
Enforces global event ID uniqueness across event partitions.
Physical table:
```text
pmrp_event.event_ids
```
## Columns
```sql
CREATE TABLE pmrp_event.event_ids (
    event_id text NOT NULL,
    occurred_at timestamptz NOT NULL,
    inserted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (event_id)
);
```
## Primary Query Patterns
- resolve event partition time
- claim an event ID
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 20. Processed Events
Purpose:
Provides consumer-level event idempotency.
Physical table:
```text
pmrp_event.processed_events
```
## Columns
```sql
CREATE TABLE pmrp_event.processed_events (
    consumer_name text NOT NULL,
    event_id text NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    processing_version text,
    result_hash text,
    PRIMARY KEY (consumer_name, event_id)
);
```
## Indexes
```sql
CREATE INDEX ix_processed_events__time ON pmrp_event.processed_events (processed_at);
```
## Primary Query Patterns
- check duplicate delivery
- audit consumer progress
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 21. Outbox Messages
Purpose:
Reliably publishes events after transactional state changes.
Physical table:
```text
pmrp_event.outbox_messages
```
## Columns
```sql
CREATE TABLE pmrp_event.outbox_messages (
    outbox_id bigserial NOT NULL,
    event_id text NOT NULL,
    topic text NOT NULL,
    partition_key text,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    publish_attempts integer NOT NULL DEFAULT 0,
    last_error text,
    PRIMARY KEY (outbox_id),
    UNIQUE (event_id, topic)
);
```
## Indexes
```sql
CREATE INDEX ix_outbox_messages__pending ON pmrp_event.outbox_messages (available_at, outbox_id) WHERE published_at IS NULL;
```
## Primary Query Patterns
- claim pending messages with SKIP LOCKED
- measure oldest backlog
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 22. Idempotency Records
Purpose:
Stores command and API idempotency results.
Physical table:
```text
pmrp_core.idempotency_records
```
## Columns
```sql
CREATE TABLE pmrp_core.idempotency_records (
    subject_id text NOT NULL,
    operation text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    status text NOT NULL,
    response_status integer,
    response_headers jsonb,
    response_body jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (subject_id, operation, idempotency_key)
);
```
## Indexes
```sql
CREATE INDEX ix_idempotency_records__expires ON pmrp_core.idempotency_records (expires_at);
```
## Primary Query Patterns
- retrieve original result
- purge expired records
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 23. Dead Letters
Purpose:
Stores durable consumer failures and replay references.
Physical table:
```text
pmrp_ops.dead_letter_records
```
## Columns
```sql
CREATE TABLE pmrp_ops.dead_letter_records (
    dead_letter_id text NOT NULL,
    source_event_id text,
    source_command_id text,
    consumer_name text NOT NULL,
    failure_category text NOT NULL,
    exception_type text NOT NULL,
    exception_message text NOT NULL,
    first_failed_at timestamptz NOT NULL,
    last_failed_at timestamptz NOT NULL,
    retry_count integer NOT NULL,
    payload_reference text NOT NULL,
    replayable boolean NOT NULL,
    resolved_at timestamptz,
    resolution_note text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (dead_letter_id)
);
```
## Indexes
```sql
CREATE INDEX ix_dead_letter_records__unresolved ON pmrp_ops.dead_letter_records (last_failed_at) WHERE resolved_at IS NULL;
```
## Primary Query Patterns
- list unresolved failures
- group by consumer and category
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 24. Markets
Purpose:
Current canonical market catalog projection.
Physical table:
```text
pmrp_market.markets
```
## Columns
```sql
CREATE TABLE pmrp_market.markets (
    market_id text NOT NULL,
    exchange text NOT NULL,
    exchange_market_id text NOT NULL,
    exchange_event_id text,
    title text NOT NULL,
    subtitle text,
    description text,
    category text,
    tags text[] NOT NULL DEFAULT '{}',
    outcome_type text NOT NULL,
    status text NOT NULL,
    opens_at timestamptz,
    closes_at timestamptz,
    resolves_at timestamptz,
    finalized_at timestamptz,
    currency text NOT NULL,
    payout_per_unit numeric(38,18) NOT NULL,
    tick_size numeric(38,18) NOT NULL,
    quantity_increment numeric(38,18) NOT NULL,
    rules_text text,
    rules_url text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    aggregate_version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (market_id),
    UNIQUE (exchange, exchange_market_id),
    CHECK (payout_per_unit > 0),
    CHECK (tick_size > 0),
    CHECK (quantity_increment > 0)
);
```
## Indexes
```sql
CREATE INDEX ix_markets__exchange_status ON pmrp_market.markets (exchange, status);
CREATE INDEX ix_markets__status_closes ON pmrp_market.markets (status, closes_at);
CREATE INDEX ix_markets__updated ON pmrp_market.markets (updated_at DESC, market_id);
```
## Primary Query Patterns
- market list
- active market scan
- external ID resolution
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 25. Outcomes
Purpose:
Canonical outcomes associated with markets.
Physical table:
```text
pmrp_market.outcomes
```
## Columns
```sql
CREATE TABLE pmrp_market.outcomes (
    outcome_id text NOT NULL,
    market_id text NOT NULL,
    exchange_outcome_id text,
    name text NOT NULL,
    normalized_name text NOT NULL,
    outcome_index integer NOT NULL,
    is_tradeable boolean NOT NULL DEFAULT true,
    is_winning boolean,
    payout_per_unit numeric(38,18) NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz,
    PRIMARY KEY (outcome_id),
    FOREIGN KEY (market_id) REFERENCES pmrp_market.markets (market_id),
    UNIQUE (market_id, outcome_index),
    UNIQUE (market_id, normalized_name)
);
```
## Indexes
```sql
CREATE INDEX ix_outcomes__market ON pmrp_market.outcomes (market_id, outcome_index);
```
## Primary Query Patterns
- load market outcomes
- resolve normalized outcome
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 26. Contracts
Purpose:
Tradeable contracts associated with outcomes.
Physical table:
```text
pmrp_market.contracts
```
## Columns
```sql
CREATE TABLE pmrp_market.contracts (
    contract_id text NOT NULL,
    market_id text NOT NULL,
    outcome_id text NOT NULL,
    exchange_contract_id text,
    symbol text,
    display_name text NOT NULL,
    tick_size numeric(38,18) NOT NULL,
    quantity_increment numeric(38,18) NOT NULL,
    min_order_quantity numeric(38,18),
    max_order_quantity numeric(38,18),
    active boolean NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (contract_id),
    FOREIGN KEY (market_id) REFERENCES pmrp_market.markets (market_id),
    FOREIGN KEY (outcome_id) REFERENCES pmrp_market.outcomes (outcome_id),
    UNIQUE (market_id, outcome_id)
);
```
## Indexes
```sql
CREATE INDEX ix_contracts__market_active ON pmrp_market.contracts (market_id, active);
```
## Primary Query Patterns
- resolve contract
- load precision rules
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 27. Market Status History
Purpose:
Append-only market lifecycle transitions.
Physical table:
```text
pmrp_market.market_status_history
```
## Columns
```sql
CREATE TABLE pmrp_market.market_status_history (
    transition_id text NOT NULL,
    market_id text NOT NULL,
    previous_status text,
    current_status text NOT NULL,
    effective_at timestamptz NOT NULL,
    source_event_id text NOT NULL,
    reason_code text,
    reason_text text,
    exchange_status text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (transition_id),
    FOREIGN KEY (market_id) REFERENCES pmrp_market.markets (market_id)
);
```
## Indexes
```sql
CREATE INDEX ix_market_status_history__market_time ON pmrp_market.market_status_history (market_id, effective_at);
```
## Primary Query Patterns
- market lifecycle history
- status at time
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 28. Current Order Books
Purpose:
Current valid or invalid order-book projection per contract.
Physical table:
```text
pmrp_market.order_book_snapshots
```
## Columns
```sql
CREATE TABLE pmrp_market.order_book_snapshots (
    market_id text NOT NULL,
    contract_id text NOT NULL,
    exchange text NOT NULL,
    sequence bigint,
    exchange_occurred_at timestamptz,
    received_at timestamptz NOT NULL,
    bids jsonb NOT NULL,
    asks jsonb NOT NULL,
    is_valid boolean NOT NULL,
    snapshot_reason text NOT NULL,
    aggregate_version bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (market_id, contract_id),
    FOREIGN KEY (market_id) REFERENCES pmrp_market.markets (market_id),
    FOREIGN KEY (contract_id) REFERENCES pmrp_market.contracts (contract_id)
);
```
## Indexes
```sql
CREATE INDEX ix_order_book_snapshots__exchange_updated ON pmrp_market.order_book_snapshots (exchange, updated_at);
```
## Primary Query Patterns
- current best book
- stale-book scan
- invalid-book scan
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 29. Trades
Purpose:
Queryable canonical trade observations.
Physical table:
```text
pmrp_market.trades
```
## Columns
```sql
CREATE TABLE pmrp_market.trades (
    exchange_occurred_at timestamptz NOT NULL,
    trade_id text NOT NULL,
    exchange text NOT NULL,
    exchange_trade_id text NOT NULL,
    market_id text NOT NULL,
    contract_id text NOT NULL,
    outcome_id text NOT NULL,
    price numeric(38,18) NOT NULL,
    quantity numeric(38,18) NOT NULL,
    aggressor_side text,
    liquidity_role text NOT NULL,
    received_at timestamptz NOT NULL,
    sequence bigint,
    source_event_id text NOT NULL,
    PRIMARY KEY (exchange_occurred_at, trade_id),
    CHECK (quantity > 0)
) PARTITION BY RANGE (exchange_occurred_at);
```
## Indexes
```sql
CREATE INDEX ix_trades__market_time ON pmrp_market.trades (market_id, exchange_occurred_at DESC);
CREATE INDEX ix_trades__contract_time ON pmrp_market.trades (contract_id, exchange_occurred_at DESC);
```
## Primary Query Patterns
- market trade history
- feature windows
- trade deduplication
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 30. Strategy Definitions
Purpose:
Versioned strategy implementation metadata and supported modes.
Physical table:
```text
pmrp_research.strategy_definitions
```
## Columns
```sql
CREATE TABLE pmrp_research.strategy_definitions (
    strategy_type text NOT NULL,
    strategy_version text NOT NULL,
    implementation_path text NOT NULL,
    description text,
    configuration_schema_version integer NOT NULL,
    subscribed_event_types text[] NOT NULL,
    supports_replay boolean NOT NULL,
    supports_simulation boolean NOT NULL,
    supports_paper boolean NOT NULL,
    supports_shadow boolean NOT NULL,
    supports_live boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (strategy_type, strategy_version)
);
```
## Primary Query Patterns
- resolve strategy implementation
- list live-capable versions
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 31. Strategy Instances
Purpose:
Current lifecycle and health state of configured strategies.
Physical table:
```text
pmrp_research.strategy_instances
```
## Columns
```sql
CREATE TABLE pmrp_research.strategy_instances (
    strategy_id text NOT NULL,
    strategy_type text NOT NULL,
    strategy_version text NOT NULL,
    name text NOT NULL,
    environment text NOT NULL,
    state text NOT NULL,
    configuration_version integer NOT NULL,
    configuration_hash text NOT NULL,
    capital_allocation_amount numeric(38,18),
    capital_allocation_currency text,
    health_status text NOT NULL,
    health_message text,
    created_at timestamptz NOT NULL,
    started_at timestamptz,
    stopped_at timestamptz,
    updated_at timestamptz NOT NULL,
    aggregate_version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (strategy_id),
    FOREIGN KEY (strategy_type, strategy_version) REFERENCES pmrp_research.strategy_definitions (strategy_type, strategy_version)
);
```
## Indexes
```sql
CREATE INDEX ix_strategy_instances__state_health ON pmrp_research.strategy_instances (state, health_status);
```
## Primary Query Patterns
- operator strategy list
- active strategy health
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 32. Strategy Configurations
Purpose:
Immutable strategy configuration versions and approvals.
Physical table:
```text
pmrp_research.strategy_configurations
```
## Columns
```sql
CREATE TABLE pmrp_research.strategy_configurations (
    strategy_id text NOT NULL,
    configuration_version integer NOT NULL,
    effective_at timestamptz NOT NULL,
    configuration jsonb NOT NULL,
    configuration_hash text NOT NULL,
    created_by text NOT NULL,
    approved_by text,
    approval_required boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (strategy_id, configuration_version),
    FOREIGN KEY (strategy_id) REFERENCES pmrp_research.strategy_instances (strategy_id),
    UNIQUE (strategy_id, configuration_hash)
);
```
## Primary Query Patterns
- load approved configuration
- configuration history
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 33. Signals
Purpose:
Append-only strategy signal history.
Physical table:
```text
pmrp_research.signals
```
## Columns
```sql
CREATE TABLE pmrp_research.signals (
    generated_at timestamptz NOT NULL,
    signal_id text NOT NULL,
    strategy_id text NOT NULL,
    market_id text NOT NULL,
    contract_id text,
    outcome_id text,
    signal_type text NOT NULL,
    direction text NOT NULL,
    strength numeric(38,18),
    fair_probability numeric(38,18),
    confidence numeric(38,18),
    valid_from timestamptz NOT NULL,
    valid_until timestamptz,
    model_id text,
    model_version text,
    feature_snapshot_id text,
    reason_code text NOT NULL,
    reason_text text,
    correlation_id text NOT NULL,
    source_event_id text,
    PRIMARY KEY (generated_at, signal_id),
    CHECK (fair_probability IS NULL OR (fair_probability >= 0 AND fair_probability <= 1))
) PARTITION BY RANGE (generated_at);
```
## Indexes
```sql
CREATE INDEX ix_signals__strategy_time ON pmrp_research.signals (strategy_id, generated_at DESC);
CREATE INDEX ix_signals__market_time ON pmrp_research.signals (market_id, generated_at DESC);
```
## Primary Query Patterns
- strategy signal history
- market signal research
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 34. Feature Snapshots
Purpose:
Versioned feature values and source lineage.
Physical table:
```text
pmrp_research.feature_snapshots
```
## Columns
```sql
CREATE TABLE pmrp_research.feature_snapshots (
    observed_at timestamptz NOT NULL,
    feature_snapshot_id text NOT NULL,
    market_id text NOT NULL,
    strategy_id text,
    generated_at timestamptz NOT NULL,
    schema_version integer NOT NULL,
    calculation_version text NOT NULL,
    features jsonb NOT NULL,
    source_event_ids text[] NOT NULL,
    payload_hash text NOT NULL,
    PRIMARY KEY (observed_at, feature_snapshot_id)
) PARTITION BY RANGE (observed_at);
```
## Indexes
```sql
CREATE INDEX ix_feature_snapshots__market_time ON pmrp_research.feature_snapshots (market_id, observed_at DESC);
```
## Primary Query Patterns
- model lineage
- research export
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 35. Model Artifacts
Purpose:
Stores model artifact metadata and approval state.
Physical table:
```text
pmrp_research.model_artifacts
```
## Columns
```sql
CREATE TABLE pmrp_research.model_artifacts (
    model_id text NOT NULL,
    model_version text NOT NULL,
    model_name text NOT NULL,
    artifact_uri text NOT NULL,
    artifact_checksum text NOT NULL,
    training_dataset_id text NOT NULL,
    training_dataset_checksum text NOT NULL,
    training_code_commit text NOT NULL,
    dependency_lock_hash text NOT NULL,
    feature_schema_version text NOT NULL,
    target_definition text NOT NULL,
    trained_at timestamptz NOT NULL,
    random_seed bigint NOT NULL,
    evaluation_metrics jsonb NOT NULL,
    calibration_method text,
    approval_status text NOT NULL,
    approved_by text,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (model_id, model_version)
);
```
## Indexes
```sql
CREATE INDEX ix_model_artifacts__approval ON pmrp_research.model_artifacts (approval_status, trained_at DESC);
```
## Primary Query Patterns
- resolve approved model
- verify artifact checksum
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 36. Order Intents
Purpose:
Immutable strategy requests before risk approval.
Physical table:
```text
pmrp_execution.order_intents
```
## Columns
```sql
CREATE TABLE pmrp_execution.order_intents (
    intent_id text NOT NULL,
    strategy_id text NOT NULL,
    market_id text NOT NULL,
    contract_id text NOT NULL,
    outcome_id text NOT NULL,
    side text NOT NULL,
    quantity numeric(38,18) NOT NULL,
    limit_price numeric(38,18),
    order_type text NOT NULL,
    time_in_force text NOT NULL,
    post_only boolean NOT NULL,
    reduce_only boolean NOT NULL,
    urgency numeric(38,18),
    created_at timestamptz NOT NULL,
    expires_at timestamptz,
    signal_ids text[] NOT NULL DEFAULT '{}',
    correlation_id text NOT NULL,
    idempotency_key text NOT NULL,
    payload_hash text NOT NULL,
    PRIMARY KEY (intent_id),
    UNIQUE (strategy_id, idempotency_key),
    CHECK (quantity > 0),
    CHECK ((order_type = 'limit' AND limit_price IS NOT NULL) OR order_type <> 'limit')
);
```
## Indexes
```sql
CREATE INDEX ix_order_intents__strategy_time ON pmrp_execution.order_intents (strategy_id, created_at DESC);
```
## Primary Query Patterns
- risk input
- strategy lineage
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 37. Orders
Purpose:
Current canonical order aggregate.
Physical table:
```text
pmrp_execution.orders
```
## Columns
```sql
CREATE TABLE pmrp_execution.orders (
    order_id text NOT NULL,
    intent_id text,
    strategy_id text,
    risk_decision_id text,
    exchange text NOT NULL,
    account_id text NOT NULL,
    market_id text NOT NULL,
    contract_id text NOT NULL,
    outcome_id text NOT NULL,
    side text NOT NULL,
    quantity numeric(38,18) NOT NULL,
    filled_quantity numeric(38,18) NOT NULL DEFAULT 0,
    remaining_quantity numeric(38,18) NOT NULL,
    limit_price numeric(38,18),
    average_fill_price numeric(38,18),
    order_type text NOT NULL,
    time_in_force text NOT NULL,
    post_only boolean NOT NULL,
    reduce_only boolean NOT NULL,
    status text NOT NULL,
    client_order_id text NOT NULL,
    exchange_order_id text,
    created_at timestamptz NOT NULL,
    submitted_at timestamptz,
    accepted_at timestamptz,
    last_updated_at timestamptz NOT NULL,
    expires_at timestamptz,
    aggregate_version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (order_id),
    UNIQUE (exchange, account_id, client_order_id),
    UNIQUE (exchange, account_id, exchange_order_id),
    CHECK (quantity > 0),
    CHECK (filled_quantity >= 0),
    CHECK (remaining_quantity >= 0),
    CHECK (filled_quantity + remaining_quantity = quantity)
);
```
## Indexes
```sql
CREATE INDEX ix_orders__account_status ON pmrp_execution.orders (exchange, account_id, status);
CREATE INDEX ix_orders__strategy_created ON pmrp_execution.orders (strategy_id, created_at DESC) WHERE strategy_id IS NOT NULL;
CREATE INDEX ix_orders__active ON pmrp_execution.orders (exchange, account_id, created_at) WHERE status IN ('submitted','accepted','partially_filled','cancel_requested','cancelling');
```
## Primary Query Patterns
- open orders
- strategy history
- reconciliation
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 38. Order State Transitions
Purpose:
Append-only validated order lifecycle history.
Physical table:
```text
pmrp_execution.order_state_transitions
```
## Columns
```sql
CREATE TABLE pmrp_execution.order_state_transitions (
    transition_id text NOT NULL,
    order_id text NOT NULL,
    previous_status text,
    current_status text NOT NULL,
    occurred_at timestamptz NOT NULL,
    source_event_id text NOT NULL,
    reason_code text,
    reason_text text,
    aggregate_version_before bigint NOT NULL,
    aggregate_version_after bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (transition_id),
    FOREIGN KEY (order_id) REFERENCES pmrp_execution.orders (order_id),
    UNIQUE (order_id, aggregate_version_after)
);
```
## Indexes
```sql
CREATE INDEX ix_order_transitions__order_time ON pmrp_execution.order_state_transitions (order_id, occurred_at);
```
## Primary Query Patterns
- order lifecycle
- state-machine audit
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 39. Fills
Purpose:
Append-only exchange fills applied to orders and portfolios.
Physical table:
```text
pmrp_execution.fills
```
## Columns
```sql
CREATE TABLE pmrp_execution.fills (
    exchange_occurred_at timestamptz NOT NULL,
    fill_id text NOT NULL,
    exchange_fill_id text NOT NULL,
    order_id text NOT NULL,
    exchange_order_id text,
    client_order_id text NOT NULL,
    exchange text NOT NULL,
    account_id text NOT NULL,
    market_id text NOT NULL,
    contract_id text NOT NULL,
    outcome_id text NOT NULL,
    side text NOT NULL,
    price numeric(38,18) NOT NULL,
    quantity numeric(38,18) NOT NULL,
    liquidity_role text NOT NULL,
    fee_amount numeric(38,18),
    fee_currency text,
    rebate_amount numeric(38,18),
    rebate_currency text,
    received_at timestamptz NOT NULL,
    trade_id text,
    source_event_id text NOT NULL,
    PRIMARY KEY (exchange_occurred_at, fill_id),
    CHECK (quantity > 0)
) PARTITION BY RANGE (exchange_occurred_at);
```
## Indexes
```sql
CREATE INDEX ix_fills__order_time ON pmrp_execution.fills (order_id, exchange_occurred_at);
CREATE INDEX ix_fills__account_time ON pmrp_execution.fills (exchange, account_id, exchange_occurred_at DESC);
```
## Primary Query Patterns
- order fills
- account reconciliation
- PnL calculation
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 40. Fill ID Registry
Purpose:
Globally enforces exchange fill idempotency.
Physical table:
```text
pmrp_execution.fill_ids
```
## Columns
```sql
CREATE TABLE pmrp_execution.fill_ids (
    exchange text NOT NULL,
    account_id text NOT NULL,
    exchange_fill_id text NOT NULL,
    fill_id text NOT NULL,
    exchange_occurred_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exchange, account_id, exchange_fill_id),
    UNIQUE (fill_id)
);
```
## Primary Query Patterns
- claim fill
- resolve canonical fill
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 41. Positions
Purpose:
Current exact position projection per account and contract.
Physical table:
```text
pmrp_portfolio.positions
```
## Columns
```sql
CREATE TABLE pmrp_portfolio.positions (
    position_id text NOT NULL,
    exchange text NOT NULL,
    account_id text NOT NULL,
    market_id text NOT NULL,
    contract_id text NOT NULL,
    outcome_id text NOT NULL,
    quantity numeric(38,18) NOT NULL,
    average_entry_price numeric(38,18),
    realized_pnl_amount numeric(38,18) NOT NULL DEFAULT 0,
    unrealized_pnl_amount numeric(38,18) NOT NULL DEFAULT 0,
    currency text NOT NULL,
    fees_paid_amount numeric(38,18) NOT NULL DEFAULT 0,
    rebates_received_amount numeric(38,18) NOT NULL DEFAULT 0,
    opened_at timestamptz,
    last_updated_at timestamptz NOT NULL,
    aggregate_version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (position_id),
    UNIQUE (exchange, account_id, contract_id)
);
```
## Indexes
```sql
CREATE INDEX ix_positions__account_market ON pmrp_portfolio.positions (exchange, account_id, market_id);
```
## Primary Query Patterns
- portfolio view
- risk exposure
- reconciliation
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 42. Cash Balances
Purpose:
Current available, reserved, and total balances.
Physical table:
```text
pmrp_portfolio.cash_balances
```
## Columns
```sql
CREATE TABLE pmrp_portfolio.cash_balances (
    balance_id text NOT NULL,
    exchange text NOT NULL,
    account_id text NOT NULL,
    currency text NOT NULL,
    available numeric(38,18) NOT NULL,
    reserved numeric(38,18) NOT NULL,
    total numeric(38,18) NOT NULL,
    captured_at timestamptz NOT NULL,
    aggregate_version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (balance_id),
    UNIQUE (exchange, account_id, currency),
    CHECK (available + reserved = total)
);
```
## Primary Query Patterns
- risk balance check
- portfolio view
- reconciliation
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 43. Journal Entries
Purpose:
Append-only accounting journal headers.
Physical table:
```text
pmrp_portfolio.journal_entries
```
## Columns
```sql
CREATE TABLE pmrp_portfolio.journal_entries (
    journal_entry_id text NOT NULL,
    occurred_at timestamptz NOT NULL,
    source_event_id text NOT NULL,
    reference_type text NOT NULL,
    reference_id text NOT NULL,
    description text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (journal_entry_id),
    UNIQUE (source_event_id)
);
```
## Indexes
```sql
CREATE INDEX ix_journal_entries__reference ON pmrp_portfolio.journal_entries (reference_type, reference_id);
```
## Primary Query Patterns
- accounting lineage
- event-to-journal lookup
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 44. Journal Lines
Purpose:
Double-entry accounting lines grouped by journal entry.
Physical table:
```text
pmrp_portfolio.journal_lines
```
## Columns
```sql
CREATE TABLE pmrp_portfolio.journal_lines (
    journal_entry_id text NOT NULL,
    line_number integer NOT NULL,
    account_code text NOT NULL,
    amount numeric(38,18) NOT NULL,
    currency text NOT NULL,
    description text,
    PRIMARY KEY (journal_entry_id, line_number),
    FOREIGN KEY (journal_entry_id) REFERENCES pmrp_portfolio.journal_entries (journal_entry_id)
);
```
## Indexes
```sql
CREATE INDEX ix_journal_lines__account_currency ON pmrp_portfolio.journal_lines (account_code, currency);
```
## Primary Query Patterns
- journal balance check
- account ledger
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 45. PnL Attributions
Purpose:
Versioned PnL components for reporting and research.
Physical table:
```text
pmrp_portfolio.pnl_attributions
```
## Columns
```sql
CREATE TABLE pmrp_portfolio.pnl_attributions (
    attribution_id text NOT NULL,
    strategy_id text,
    market_id text,
    exchange text,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    currency text NOT NULL,
    realized_trading_pnl numeric(38,18) NOT NULL,
    unrealized_pnl_change numeric(38,18) NOT NULL,
    fees numeric(38,18) NOT NULL,
    rebates numeric(38,18) NOT NULL,
    slippage numeric(38,18),
    settlement_pnl numeric(38,18),
    total_pnl numeric(38,18) NOT NULL,
    calculation_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (attribution_id)
);
```
## Indexes
```sql
CREATE INDEX ix_pnl_attributions__strategy_period ON pmrp_portfolio.pnl_attributions (strategy_id, starts_at, ends_at);
```
## Primary Query Patterns
- strategy PnL
- market attribution
- period reports
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 46. Settlements
Purpose:
Canonical settlement lifecycle and correction history.
Physical table:
```text
pmrp_portfolio.settlements
```
## Columns
```sql
CREATE TABLE pmrp_portfolio.settlements (
    settlement_id text NOT NULL,
    market_id text NOT NULL,
    exchange text NOT NULL,
    status text NOT NULL,
    winning_outcome_ids text[] NOT NULL DEFAULT '{}',
    resolved_at timestamptz,
    finalized_at timestamptz,
    settled_at timestamptz,
    payout_per_unit numeric(38,18),
    source text NOT NULL,
    source_reference text,
    correction_of_settlement_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (settlement_id),
    FOREIGN KEY (correction_of_settlement_id) REFERENCES pmrp_portfolio.settlements (settlement_id)
);
```
## Indexes
```sql
CREATE INDEX ix_settlements__market_created ON pmrp_portfolio.settlements (market_id, created_at DESC);
```
## Primary Query Patterns
- current settlement
- correction lineage
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 47. Risk Limits
Purpose:
Versioned risk policy limits by scope.
Physical table:
```text
pmrp_risk.risk_limits
```
## Columns
```sql
CREATE TABLE pmrp_risk.risk_limits (
    risk_limit_id text NOT NULL,
    rule_id text NOT NULL,
    rule_version text NOT NULL,
    scope text NOT NULL,
    scope_id text,
    limit_type text NOT NULL,
    limit_value numeric(38,18) NOT NULL,
    unit text NOT NULL,
    effective_at timestamptz NOT NULL,
    expires_at timestamptz,
    enabled boolean NOT NULL,
    created_by text NOT NULL,
    approved_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz,
    aggregate_version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (risk_limit_id)
);
```
## Indexes
```sql
CREATE INDEX ix_risk_limits__active_scope ON pmrp_risk.risk_limits (scope, scope_id, rule_id) WHERE enabled = true;
```
## Primary Query Patterns
- load active limits
- limit history
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 48. Risk Decisions
Purpose:
Immutable pre-trade rule evaluation results.
Physical table:
```text
pmrp_risk.risk_decisions
```
## Columns
```sql
CREATE TABLE pmrp_risk.risk_decisions (
    evaluated_at timestamptz NOT NULL,
    risk_decision_id text NOT NULL,
    intent_id text NOT NULL,
    status text NOT NULL,
    input_snapshot_id text NOT NULL,
    approved_quantity numeric(38,18),
    approved_limit_price numeric(38,18),
    approval_expires_at timestamptz,
    configuration_hash text NOT NULL,
    correlation_id text NOT NULL,
    rule_results jsonb NOT NULL,
    payload_hash text NOT NULL,
    PRIMARY KEY (evaluated_at, risk_decision_id)
) PARTITION BY RANGE (evaluated_at);
```
## Indexes
```sql
CREATE INDEX ix_risk_decisions__intent ON pmrp_risk.risk_decisions (intent_id);
CREATE INDEX ix_risk_decisions__status_time ON pmrp_risk.risk_decisions (status, evaluated_at DESC);
```
## Primary Query Patterns
- intent decision
- risk rejection analysis
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 49. Risk Breaches
Purpose:
Records post-trade and operational risk breaches.
Physical table:
```text
pmrp_risk.risk_breaches
```
## Columns
```sql
CREATE TABLE pmrp_risk.risk_breaches (
    breach_id text NOT NULL,
    rule_id text NOT NULL,
    rule_version text NOT NULL,
    scope text NOT NULL,
    scope_id text,
    severity text NOT NULL,
    detected_at timestamptz NOT NULL,
    observed_value numeric(38,18),
    limit_value numeric(38,18),
    unit text,
    action_taken text NOT NULL,
    correlation_id text NOT NULL,
    resolved_at timestamptz,
    resolution_note text,
    PRIMARY KEY (breach_id)
);
```
## Indexes
```sql
CREATE INDEX ix_risk_breaches__open_severity ON pmrp_risk.risk_breaches (severity, detected_at DESC) WHERE resolved_at IS NULL;
```
## Primary Query Patterns
- active breaches
- breach history
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 50. Kill Switches
Purpose:
Durable scoped trading gates.
Physical table:
```text
pmrp_risk.kill_switches
```
## Columns
```sql
CREATE TABLE pmrp_risk.kill_switches (
    kill_switch_id text NOT NULL,
    scope text NOT NULL,
    scope_id text,
    active boolean NOT NULL,
    activated_at timestamptz,
    activated_by text,
    activation_reason text,
    released_at timestamptz,
    released_by text,
    release_reason text,
    aggregate_version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (kill_switch_id)
);
```
## Indexes
```sql
CREATE UNIQUE INDEX uq_kill_switches__active_scope ON pmrp_risk.kill_switches (scope, COALESCE(scope_id, '')) WHERE active = true;
```
## Primary Query Patterns
- active trading gates
- scope gate check
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 51. Capital Reservations
Purpose:
Prevents concurrent approvals from exceeding capital and exposure limits.
Physical table:
```text
pmrp_risk.capital_reservations
```
## Columns
```sql
CREATE TABLE pmrp_risk.capital_reservations (
    reservation_id text NOT NULL,
    intent_id text NOT NULL,
    strategy_id text NOT NULL,
    exchange text NOT NULL,
    account_id text NOT NULL,
    market_id text NOT NULL,
    quantity numeric(38,18) NOT NULL,
    notional numeric(38,18) NOT NULL,
    currency text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    released_at timestamptz,
    PRIMARY KEY (reservation_id),
    UNIQUE (intent_id)
);
```
## Indexes
```sql
CREATE INDEX ix_capital_reservations__active_expiry ON pmrp_risk.capital_reservations (expires_at) WHERE released_at IS NULL;
```
## Primary Query Patterns
- calculate reserved exposure
- release expired reservations
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 52. Reconciliation Runs
Purpose:
Stores account reconciliation lifecycle and trading-gate decision.
Physical table:
```text
pmrp_ops.reconciliation_runs
```
## Columns
```sql
CREATE TABLE pmrp_ops.reconciliation_runs (
    reconciliation_id text NOT NULL,
    exchange text NOT NULL,
    account_id text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    status text NOT NULL,
    open_orders_checked integer NOT NULL DEFAULT 0,
    positions_checked integer NOT NULL DEFAULT 0,
    balances_checked integer NOT NULL DEFAULT 0,
    fills_checked integer NOT NULL DEFAULT 0,
    trading_gate_released boolean NOT NULL DEFAULT false,
    initiated_by text NOT NULL,
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (reconciliation_id)
);
```
## Indexes
```sql
CREATE INDEX ix_reconciliation_runs__account_time ON pmrp_ops.reconciliation_runs (exchange, account_id, started_at DESC);
```
## Primary Query Patterns
- latest account reconciliation
- failed reconciliation list
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 53. Reconciliation Mismatches
Purpose:
Stores differences between local and exchange-authoritative state.
Physical table:
```text
pmrp_ops.reconciliation_mismatches
```
## Columns
```sql
CREATE TABLE pmrp_ops.reconciliation_mismatches (
    mismatch_id text NOT NULL,
    reconciliation_id text NOT NULL,
    category text NOT NULL,
    local_value text,
    external_value text,
    severity text NOT NULL,
    explanation text,
    requires_manual_review boolean NOT NULL,
    resolved_at timestamptz,
    resolution_note text,
    PRIMARY KEY (mismatch_id),
    FOREIGN KEY (reconciliation_id) REFERENCES pmrp_ops.reconciliation_runs (reconciliation_id)
);
```
## Indexes
```sql
CREATE INDEX ix_reconciliation_mismatches__run ON pmrp_ops.reconciliation_mismatches (reconciliation_id, severity);
```
## Primary Query Patterns
- reconciliation details
- unresolved mismatch scan
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 54. Replay Sessions
Purpose:
Stores deterministic replay manifests, state, progress, and checksum.
Physical table:
```text
pmrp_research.replay_sessions
```
## Columns
```sql
CREATE TABLE pmrp_research.replay_sessions (
    replay_session_id text NOT NULL,
    dataset_id text NOT NULL,
    dataset_checksum text NOT NULL,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    speed numeric(38,18) NOT NULL,
    deterministic boolean NOT NULL,
    random_seed bigint NOT NULL,
    event_ordering_policy_version text NOT NULL,
    strategy_versions jsonb NOT NULL,
    model_versions jsonb NOT NULL,
    configuration_hash text NOT NULL,
    code_commit text NOT NULL,
    dependency_lock_hash text NOT NULL,
    state text NOT NULL,
    current_time timestamptz,
    processed_events bigint NOT NULL DEFAULT 0,
    rejected_events bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL,
    started_at timestamptz,
    completed_at timestamptz,
    result_checksum text,
    failure_message text,
    PRIMARY KEY (replay_session_id)
);
```
## Indexes
```sql
CREATE INDEX ix_replay_sessions__state_created ON pmrp_research.replay_sessions (state, created_at DESC);
```
## Primary Query Patterns
- replay progress
- manifest lookup
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 55. Replay Results
Purpose:
Stores completed replay summary and final portfolio.
Physical table:
```text
pmrp_research.replay_results
```
## Columns
```sql
CREATE TABLE pmrp_research.replay_results (
    replay_session_id text NOT NULL,
    processed_events bigint NOT NULL,
    generated_signals bigint NOT NULL,
    generated_intents bigint NOT NULL,
    simulated_orders bigint NOT NULL,
    simulated_fills bigint NOT NULL,
    final_portfolio jsonb NOT NULL,
    metrics jsonb NOT NULL,
    result_checksum text NOT NULL,
    completed_at timestamptz NOT NULL,
    PRIMARY KEY (replay_session_id),
    FOREIGN KEY (replay_session_id) REFERENCES pmrp_research.replay_sessions (replay_session_id)
);
```
## Primary Query Patterns
- replay result
- checksum comparison
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 56. Simulation Sessions
Purpose:
Stores simulation configuration and lifecycle.
Physical table:
```text
pmrp_research.simulation_sessions
```
## Columns
```sql
CREATE TABLE pmrp_research.simulation_sessions (
    simulation_session_id text NOT NULL,
    replay_session_id text,
    configuration jsonb NOT NULL,
    configuration_hash text NOT NULL,
    state text NOT NULL,
    created_at timestamptz NOT NULL,
    started_at timestamptz,
    completed_at timestamptz,
    result_checksum text,
    PRIMARY KEY (simulation_session_id),
    FOREIGN KEY (replay_session_id) REFERENCES pmrp_research.replay_sessions (replay_session_id)
);
```
## Indexes
```sql
CREATE INDEX ix_simulation_sessions__state_created ON pmrp_research.simulation_sessions (state, created_at DESC);
```
## Primary Query Patterns
- simulation progress
- configuration comparison
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 57. Market Relationships
Purpose:
Stores approved and reviewed relationships between canonical markets.
Physical table:
```text
pmrp_research.market_relationships
```
## Columns
```sql
CREATE TABLE pmrp_research.market_relationships (
    relationship_id text NOT NULL,
    source_market_id text NOT NULL,
    target_market_id text NOT NULL,
    relationship_type text NOT NULL,
    confidence numeric(38,18) NOT NULL,
    valid_from timestamptz NOT NULL,
    valid_until timestamptz,
    evidence jsonb NOT NULL,
    validator_version text NOT NULL,
    settlement_rule_match boolean,
    human_review_status text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    aggregate_version bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (relationship_id),
    UNIQUE (source_market_id, target_market_id, relationship_type),
    CHECK (confidence >= 0 AND confidence <= 1)
);
```
## Indexes
```sql
CREATE INDEX ix_market_relationships__source_target ON pmrp_research.market_relationships (source_market_id, target_market_id);
```
## Primary Query Patterns
- approved relationship lookup
- cross-exchange candidate scan
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 58. Adapter Health Snapshots
Purpose:
Time-series adapter connectivity, freshness, and trading-gate state.
Physical table:
```text
pmrp_ops.adapter_health_snapshots
```
## Columns
```sql
CREATE TABLE pmrp_ops.adapter_health_snapshots (
    captured_at timestamptz NOT NULL,
    exchange text NOT NULL,
    environment text NOT NULL,
    status text NOT NULL,
    connected boolean NOT NULL,
    authenticated boolean NOT NULL,
    subscriptions_active boolean NOT NULL,
    last_message_at timestamptz,
    last_heartbeat_at timestamptz,
    last_reconciliation_at timestamptz,
    market_data_fresh boolean NOT NULL,
    trading_gate_open boolean NOT NULL,
    reconnect_attempts integer NOT NULL,
    message text,
    PRIMARY KEY (captured_at, exchange, environment)
) PARTITION BY RANGE (captured_at);
```
## Indexes
```sql
CREATE INDEX ix_adapter_health__exchange_time ON pmrp_ops.adapter_health_snapshots (exchange, captured_at DESC);
```
## Primary Query Patterns
- latest adapter health
- incident history
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 59. Operator Audit Records
Purpose:
Immutable operator and API control audit history.
Physical table:
```text
pmrp_audit.operator_audit_records
```
## Columns
```sql
CREATE TABLE pmrp_audit.operator_audit_records (
    requested_at timestamptz NOT NULL,
    audit_id text NOT NULL,
    actor text NOT NULL,
    action text NOT NULL,
    scope text NOT NULL,
    scope_id text,
    completed_at timestamptz,
    result text NOT NULL,
    reason text,
    correlation_id text NOT NULL,
    request_id text,
    idempotency_key text,
    source_ip_hash text,
    request_hash text,
    PRIMARY KEY (requested_at, audit_id)
) PARTITION BY RANGE (requested_at);
```
## Indexes
```sql
CREATE INDEX ix_operator_audit__actor_time ON pmrp_audit.operator_audit_records (actor, requested_at DESC);
CREATE INDEX ix_operator_audit__scope_time ON pmrp_audit.operator_audit_records (scope, scope_id, requested_at DESC);
```
## Primary Query Patterns
- operator action history
- control incident review
## Operational Rules
- Inserts and updates must use typed repositories.
- Financial NUMERIC values must deserialize to Decimal.
- Time values must remain timezone-aware.
- Any mutation that changes business state must preserve audit lineage.
- Constraints are part of the domain safety boundary and must be tested.
# 60. Global Uniqueness Across Partitions
PostgreSQL requires partition keys in partitioned unique constraints.
For globally unique IDs such as event IDs, trade IDs, and fill IDs, use a small
unpartitioned registry table.
Append pattern:
1. insert the globally unique ID into the registry
2. insert the partitioned row
3. apply related state changes
4. commit
The registry insert is the idempotency claim.
# 61. Monthly Partition Example
```sql
CREATE TABLE pmrp_event.canonical_events_2026_07
PARTITION OF pmrp_event.canonical_events
FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
```
Every partition must receive the required indexes.
Partition creation should be automated at least one interval in advance.
# 62. Optimistic Concurrency
Mutable aggregates use `aggregate_version`.
Example:
```sql
UPDATE pmrp_execution.orders
SET
    status = :status,
    filled_quantity = :filled_quantity,
    remaining_quantity = :remaining_quantity,
    aggregate_version = aggregate_version + 1,
    last_updated_at = :last_updated_at
WHERE order_id = :order_id
  AND aggregate_version = :expected_version;
```
Zero updated rows means the record is missing or the expected version is stale.
The repository must distinguish these cases.
# 63. Unit of Work
Application services use an explicit unit of work.
```python
async with unit_of_work:
    order = await unit_of_work.orders.get(order_id)
    order.apply_fill(fill)
    await unit_of_work.orders.save(
        order,
        expected_version=expected_version,
    )
    await unit_of_work.commit()
```
Repositories do not commit independently.
# 64. Order Creation Transaction
Recommended transaction:
1. insert order intent
2. insert risk input snapshot
3. insert risk decision
4. insert approved order aggregate
5. insert initial order state transition
6. insert canonical events
7. insert outbox messages
8. commit
Exchange submission occurs after the transaction commits.
# 65. Fill Application Transaction
Recommended transaction:
1. claim exchange fill ID
2. insert fill
3. update order with expected aggregate version
4. append order transition
5. update position
6. update balance if available
7. insert accounting journal
8. insert canonical events
9. insert outbox messages
10. commit
A duplicate fill ID returns the existing result without applying accounting
again.
# 66. Journal Balance Validation
Journal lines must sum to zero per currency.
Validation query:
```sql
SELECT
    journal_entry_id,
    currency,
    sum(amount) AS imbalance
FROM pmrp_portfolio.journal_lines
GROUP BY journal_entry_id, currency
HAVING sum(amount) <> 0;
```
The application validates before commit.
A scheduled reconciliation query verifies durable state.
# 67. Reconciliation Transaction
External exchange queries occur outside the database transaction.
The persistence transaction then:
1. stores the reconciliation run
2. stores mismatches
3. applies approved corrections
4. updates trading-gate state
5. appends canonical events
6. appends audit records
7. commits
# 68. Kill Switch Transaction
Activation transaction:
1. check for an existing active switch at scope
2. insert or update durable switch state
3. append audit record
4. append canonical event
5. append outbox message
6. commit
Order cancellation begins only after activation is durable.
# 69. Replay Query
Canonical replay query must use explicit deterministic ordering.
```sql
SELECT *
FROM pmrp_event.canonical_events
WHERE occurred_at >= :starts_at
  AND occurred_at < :ends_at
  AND event_type = ANY(:event_types)
ORDER BY
    occurred_at,
    COALESCE(
        (attributes->>'exchange_sequence')::bigint,
        9223372036854775807
    ),
    received_at,
    event_id;
```
Large replays use server-side cursors and bounded batches.
# 70. Cursor Pagination
Cursor pagination should encode the last stable sort key and a filter hash.
Market example:
```sql
SELECT *
FROM pmrp_market.markets
WHERE
    (updated_at, market_id) < (:last_updated_at, :last_market_id)
ORDER BY updated_at DESC, market_id DESC
LIMIT :limit_plus_one;
```
A cursor used with different filters must be rejected.
# 71. Open Order Query
```sql
SELECT *
FROM pmrp_execution.orders
WHERE exchange = :exchange
  AND account_id = :account_id
  AND status IN (
      'submitted',
      'accepted',
      'partially_filled',
      'cancel_requested',
      'cancelling'
  )
ORDER BY created_at, order_id;
```
This query supports execution recovery and reconciliation.
# 72. Active Kill Switch Query
```sql
SELECT *
FROM pmrp_risk.kill_switches
WHERE active = true
ORDER BY scope, scope_id;
```
Risk should cache this only with a durable invalidation strategy.
# 73. Outbox Worker Query
```sql
SELECT
    outbox_id,
    event_id,
    topic,
    partition_key,
    payload
FROM pmrp_event.outbox_messages
WHERE published_at IS NULL
  AND available_at <= now()
ORDER BY outbox_id
FOR UPDATE SKIP LOCKED
LIMIT :batch_size;
```
Workers must use bounded retries and backoff.
# 74. Outbox Backlog Monitoring
```sql
SELECT
    count(*) AS pending_count,
    min(created_at) AS oldest_created_at
FROM pmrp_event.outbox_messages
WHERE published_at IS NULL;
```
Alert on both count and oldest-message age.
# 75. Database Roles
Recommended roles:
```text
pmrp_owner
pmrp_migrator
pmrp_app_readwrite
pmrp_app_readonly
pmrp_replay_readonly
pmrp_auditor
pmrp_backup
```
Applications must not connect as the object owner.
Strategies never receive database credentials.
# 76. Permissions
Grant only required schema usage and table operations.
Example:
```sql
GRANT USAGE ON SCHEMA pmrp_market TO pmrp_app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA pmrp_market TO pmrp_app_readonly;
```
Configure default privileges for future tables.
Audit tables should deny update and delete to normal application roles.
# 77. Secret Handling
Do not store exchange private keys, bearer tokens, signing secrets, or plaintext
passwords in application tables.
The database may store secret references and rotation metadata.
Database connection strings come from secret management and must never be
written to audit payloads.
# 78. Database Encryption
Requirements:
- TLS for database connections
- encrypted storage volumes
- encrypted backups
- restricted backup credentials
- no secrets in SQL logs
Application-level encryption may be added for specially classified fields.
# 79. Alembic Migration Policy
Every schema change requires an Alembic migration.
Migration requirements:
- deterministic upgrade
- safe downgrade when practical
- descriptive name
- lock-risk note
- expected runtime
- backfill plan
- rollback or forward-fix plan
- integration test
Migration code should not import the full application runtime.
# 80. Expand-and-Contract
Use expand-and-contract for breaking physical changes:
1. add new nullable structure
2. deploy dual write if required
3. backfill in bounded batches
4. validate
5. switch reads
6. stop old writes
7. remove old structure in a later release
Do not rename or drop high-volume columns in one unsafe deployment.
# 81. Large Backfills
Large backfills run as restartable jobs outside the migration transaction.
They must:
- process bounded batches
- record progress
- be idempotent
- emit metrics
- avoid long locks
- verify checksums or row counts
- support safe pause and resume
# 82. Migration Testing
CI must test:
- upgrade from empty database
- upgrade from previous release
- SQLAlchemy metadata alignment
- constraints and indexes
- representative inserts
- supported downgrade
- re-upgrade after downgrade
Staging should test migrations with representative data volume.
# 83. Schema Drift Detection
Startup and CI should compare:
- expected Alembic head
- live Alembic revision
- required schemas
- required extensions
- expected indexes
- expected constraints
Live trading remains disabled when database schema compatibility is uncertain.
# 84. Backup Strategy
Required protection:
- scheduled full backup
- continuous WAL archive for point-in-time recovery
- object-store archive manifests
- migration history
- configuration snapshots
- model metadata
Backups must be encrypted and verified.
# 85. Recovery Objectives
Define and test:
```text
Recovery Point Objective
Recovery Time Objective
```
Example initial targets:
```text
RPO: 15 minutes
RTO: 4 hours
```
These are planning examples, not guarantees, until restore tests prove them.
# 86. Restore Test
Restore validation procedure:
1. provision isolated PostgreSQL
2. restore backup
3. apply WAL if required
4. verify Alembic revision
5. verify table and partition counts
6. verify event hashes
7. verify recent orders and fills
8. verify positions and balances
9. run reconciliation dry run
10. run a replay sample
11. record actual restore time
# 87. Point-in-Time Recovery
After point-in-time recovery:
- keep live trading disabled
- reconnect applications
- reconcile open orders
- reconcile fills
- reconcile positions and balances
- apply missing external activity
- release trading gates only after review
Database rollback cannot reverse orders already executed at an exchange.
# 88. Replication
Read replicas may serve:
- historical event reads
- market metadata
- completed replay results
- research exports
- audit queries
Safety-critical current order, risk, and portfolio state should use the primary
unless replica lag is explicitly bounded and accepted.
# 89. High Availability
Database failover requires:
- fencing
- connection re-resolution
- data-loss understanding
- post-failover health validation
- exchange reconciliation
Live trading remains gated after failover until account state is reconciled.
# 90. Retention
Example lifecycle:
```text
raw hot storage             30-90 days
canonical event hot storage 6-18 months
audit history               long retention
health snapshots            shorter retention
operational projections     current state plus required history
```
Actual retention depends on legal, operational, research, and cost requirements.
# 91. Archive Formats
Recommended:
- Parquet for analytical canonical data
- compressed JSON Lines for portable event archives
- compressed raw payload files for evidence
Every archive has:
- time range
- row count
- schema versions
- checksum
- compression
- source partition
- export tool version
# 92. Archive Verification
Before dropping hot partitions verify:
- file exists
- checksum matches
- row count matches
- timestamp bounds match
- sample rows deserialize
- schema versions are supported
- replay sample succeeds
# 93. Partition Maintenance
Automated maintenance must:
- create future partitions
- create required indexes
- verify partition constraints
- report missing partitions
- export closed partitions
- detach archived partitions
- update archive catalog
A missing future partition is an operational alert.
# 94. Index Policy
Every index must support a documented query.
Review:
- selectivity
- sort direction
- partial predicates
- write amplification
- partition count
- index size
- index-only scan value
Use `EXPLAIN (ANALYZE, BUFFERS)` on representative data.
# 95. JSONB Index Policy
Do not add broad GIN indexes to raw and event payloads by default.
Add JSONB indexes only for measured query needs.
Frequently queried operational fields should be columns.
# 96. Vacuum and Analyze
Monitor autovacuum on mutable tables:
- orders
- positions
- balances
- strategy instances
- kill switches
Append-only tables have different maintenance patterns.
After large backfills, run targeted ANALYZE.
# 97. Connection Pooling
Use one async pool per process.
Configuration:
```text
pool_min_size
pool_max_size
pool_timeout_seconds
pool_recycle_seconds
```
Pool sizing must account for process count, transaction duration, and database
connection limits.
# 98. Database Timeouts
Set environment-specific:
- connection timeout
- statement timeout
- lock timeout
- idle-in-transaction timeout
Example:
```sql
SET statement_timeout = '5s';
SET lock_timeout = '1s';
SET idle_in_transaction_session_timeout = '30s';
```
Replay export jobs may require different limits than live execution.
# 99. Application Names
Set PostgreSQL `application_name`.
Examples:
```text
pmrp-collector
pmrp-trader
pmrp-replay
pmrp-operator-api
pmrp-migrator
pmrp-backup
```
This improves monitoring and incident response.
# 100. Error Mapping
Map database failures into project errors.
```text
unique violation        DuplicateRecord or idempotent existing result
foreign key violation   IntegrityError
check violation         InvariantViolation
serialization failure   ConcurrencyConflict
deadlock                 ConcurrencyConflict
connection failure      PersistenceUnavailable
statement timeout        PersistenceTimeout
```
Retries must remain bounded and idempotent.
# 101. Deadlock Prevention
Use consistent lock order.
Keep transactions short.
Do not call external services while holding locks.
On deadlock:
- record metric
- classify the transaction
- retry only if idempotent
- investigate repeated patterns
# 102. Database Monitoring
Required metrics:
- open connections
- pool wait duration
- transaction duration
- query latency
- deadlocks
- lock waits
- serialization failures
- WAL volume
- replication lag
- table size
- index size
- disk usage
- long transactions
- autovacuum lag
# 103. Slow Query Monitoring
Enable slow query logging and `pg_stat_statements`.
Do not expose sensitive bind values.
Review the most expensive queries by:
- total time
- mean time
- calls
- rows
- buffer reads
# 104. Operational Alerts
Alert on:
- database unavailable
- connection usage high
- pool wait high
- disk usage high
- replication lag
- backup failure
- restore test overdue
- schema revision mismatch
- missing partition
- long transaction
- outbox backlog
- dead-letter growth
- reconciliation failures
# 105. Load Testing
Measure:
- raw append throughput
- canonical event throughput
- order transaction latency
- fill transaction latency
- replay scan rate
- API read latency
- pool contention
- WAL growth
- partition growth
# 106. Capacity Planning
Estimate:
```text
events per second
average raw payload bytes
average canonical payload bytes
events per day
retention days
index overhead
replication overhead
backup overhead
```
Daily raw size:
```text
events_per_second * average_payload_bytes * 86,400
```
Use measured compression ratios.
# 107. Research Exports
Research exports should include:
- manifest
- query parameters
- schema versions
- source time range
- row count
- checksum
- code version
- creation time
Exports should stream and should not block live critical transactions.
# 108. Data Warehouse Boundary
A future warehouse or analytical engine may store derived copies.
It is not authoritative for:
- open orders
- fills
- positions
- balances
- risk
- kill switches
Operational PostgreSQL remains authoritative for live state.
# 109. Test Database Isolation
Integration tests may use:
- database per worker
- schema per worker
- transaction rollback per test
Tests must apply migrations and must not rely on execution order.
# 110. Database Contract Tests
Required tests:
- Decimal exactness
- UTC timestamp preservation
- global event uniqueness
- global fill uniqueness
- order quantity constraint
- cash balance constraint
- optimistic concurrency conflict
- processed-event idempotency
- outbox claim behavior
- partition routing
- migration upgrade
# 111. Query Plan Tests
Critical queries should be tested with representative data.
Verify:
- active orders use the partial index
- market listing uses updated-time index
- replay prunes partitions
- fill lookup uses the fill registry
- outbox worker uses the pending index
Avoid asserting exact planner text across PostgreSQL versions.
# 112. SQLAlchemy Mapping
Use SQLAlchemy 2 typed declarative mappings.
```python
class OrderRow(Base):
    __tablename__ = "orders"
    __table_args__ = {"schema": "pmrp_execution"}
    order_id: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(38, 18),
        nullable=False,
    )
    aggregate_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
```
Persistence rows are not domain aggregates.
# 113. Mapping Functions
Use explicit mapping functions:
```python
def order_row_to_domain(row: OrderRow) -> Order:
    ...
def order_domain_to_values(order: Order) -> dict[str, object]:
    ...
```
Mapping tests must verify Decimal, enum, and timestamp behavior.
# 114. Startup Validation
Startup must verify:
- database reachable
- expected PostgreSQL version
- expected Alembic revision
- required schemas
- required extensions
- session timezone UTC
- role permissions
- read health
- write health
Live readiness is false on any required validation failure.
# 115. Environment Separation
Use separate databases or clusters for:
```text
local
test
development
staging
shadow
production
```
Production credentials must not connect to development databases.
Environment identity should be checked during startup.
# 116. Incident Response
Database incidents include:
- unavailable primary
- connection exhaustion
- disk full
- replication lag
- long lock
- failed migration
- corrupted projection
- missing fill
- duplicate data
- slow-query storm
Immediate priority:
- gate unsafe trading
- preserve evidence
- avoid destructive repair
- reconcile external exchange state
# 117. Failed Migration Runbook
1. stop application deployment
2. identify exact migration state
3. prevent mixed incompatible versions
4. follow rollback or forward-fix plan
5. verify schema revision
6. verify data constraints
7. run smoke tests
8. resume deployment
9. document incident
# 118. Corrupted Projection Runbook
1. disable affected trading scope
2. preserve the current projection
3. identify source event range
4. rebuild into a new table or schema
5. compare checksums and counts
6. reconcile exchange state
7. switch readers
8. archive the corrupted projection
# 119. Missing Fill Runbook
1. activate the appropriate trading gate
2. query exchange fill history
3. preserve the raw response
4. normalize the missing fill
5. claim fill idempotency
6. apply order and portfolio transaction
7. reconcile balances and positions
8. release the gate after review
# 120. Initial Migration Order
Recommended migration sequence:
```text
0001 create logical schemas
0002 create schema registry
0003 create exchange and account registries
0004 create raw exchange records
0005 create canonical events and global IDs
0006 create processed events and outbox
0007 create idempotency and dead letters
0008 create markets, outcomes, and contracts
0009 create order-book projection and trades
0010 create strategy and model metadata
0011 create signals and features
0012 create order intents, orders, and transitions
0013 create fills and fill registry
0014 create positions, balances, and journals
0015 create PnL and settlements
0016 create risk limits, decisions, and breaches
0017 create kill switches and reservations
0018 create reconciliation tables
0019 create replay and simulation tables
0020 create matching tables
0021 create health and audit tables
```
# 121. Coding-Agent Work Packet: Raw Store
```text
Goal:
Implement partitioned PostgreSQL raw exchange record storage.
Scope:
- migration
- SQLAlchemy row model
- repository
- integration tests
Requirements:
- exact one-of payload constraint
- payload hash
- exchange and receive-time indexes
- async streaming
- exact round trip
- no normalization logic
Tests:
- text payload
- binary payload
- invalid dual payload
- invalid empty payload
- time-range stream
- partition routing
```
# 122. Coding-Agent Work Packet: Event Store
```text
Goal:
Implement append-only canonical event storage.
Requirements:
- global event ID registry
- partitioned event table
- exact JSONB payload
- payload hash
- deterministic replay query
- duplicate event handling
- async streaming
- integration tests
Do not implement business consumers.
```
# 123. Coding-Agent Work Packet: Orders
```text
Goal:
Implement order and order-transition persistence.
Requirements:
- constraints
- optimistic concurrency
- transition uniqueness
- repository protocol
- SQLAlchemy mapper
- integration tests
Tests:
- insert
- update expected version
- stale version conflict
- quantity invariant
- duplicate client order ID
```
# 124. Coding-Agent Work Packet: Fill Transaction
```text
Goal:
Persist a fill idempotently and update order, position, journal, and outbox.
Tests:
- first fill
- duplicate fill
- partial fill
- final fill
- concurrency conflict
- transaction rollback on journal failure
```
# 125. Database Review Checklist
```text
[ ] Table owner is clear.
[ ] Primary key is explicit.
[ ] Foreign keys are intentional.
[ ] Financial values use NUMERIC.
[ ] Time values use TIMESTAMPTZ.
[ ] Nullability is justified.
[ ] Uniqueness is enforced.
[ ] Check constraints protect invariants.
[ ] Indexes support documented queries.
[ ] Partitioning is justified.
[ ] Transaction boundary is defined.
[ ] Idempotency is addressed.
[ ] Migration risk is documented.
[ ] Retention is defined.
[ ] Backup impact is reviewed.
[ ] Security classification is reviewed.
```
# 126. Database Definition of Done
A database change is complete when:
- Alembic migration exists
- SQLAlchemy mapping exists
- repository behavior exists
- constraints and indexes exist
- integration tests pass
- transaction semantics are documented
- rollback or forward-fix is documented
- retention and partition impact are reviewed
- backup and restore impact are reviewed
- permissions are correct
- monitoring is updated
# 127. Final Database Position
The database is the durable memory of PMRP.
It preserves source evidence, canonical facts, decisions, orders, fills,
accounting, risk, operator actions, and experiment lineage.
Append-only history protects evidence.
Operational projections support low-latency reads.
Transactions protect invariants.
Idempotency protects repeated delivery.
Reconciliation protects against uncertainty.
Backups and verified archives protect against infrastructure failure.
The database design is acceptable only when it can explain every meaningful
state change and recover safely when surrounding systems fail.
