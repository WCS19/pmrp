# Prediction Market Research Platform

## Implementation Plan and Delivery Roadmap

- Document: `04_IMPLEMENTATION.md`
- Version: 1.0
- Status: Governing implementation plan
- Related documents:
  - `01_ARCHITECTURE.md`
  - `02_ENGINEERING.md`
  - `03_SCHEMAS.md`
- Primary language: Python 3.13
- Package manager: uv
- Character set: ASCII only
- Intended audience: maintainers, contributors, technical leads, reviewers, and coding agents

---

## Document Authority

This document converts the platform architecture, engineering standards, and
canonical schemas into a concrete implementation sequence.

It defines:

- delivery phases
- repository scaffolding
- package order
- milestone dependencies
- pull-request boundaries
- implementation tasks
- acceptance criteria
- validation gates
- release gates
- coding-agent work packets
- risk controls
- readiness criteria

The plan favors small, reviewable, testable increments.

No milestone is considered complete because code merely compiles.

Each milestone must satisfy its acceptance criteria, test requirements,
documentation requirements, and operational requirements.

---

# 1. Executive Summary

PMRP should be built in deliberate vertical slices.

The implementation must not begin with live trading.

The recommended delivery sequence is:

1. repository foundation
2. common types and canonical schemas
3. event and command infrastructure
4. storage and migrations
5. exchange adapter contracts
6. Kalshi market-data adapter
7. Polymarket market-data adapter
8. normalization and market catalog
9. deterministic replay
10. strategy runtime
11. simulation
12. risk
13. portfolio accounting
14. paper trading
15. shadow trading
16. live execution
17. market matching
18. cross-exchange arbitrage
19. advanced analytics and scaling

The build should remain a modular monolith until measured evidence justifies
service extraction.

The recommended pull-request strategy is:

- one package or contract at a time
- tests in the same pull request
- documentation in the same pull request
- migrations in the same pull request
- no hidden follow-up work for safety-critical behavior
- no large unreviewed coding-agent dump

The implementation plan assumes the architecture documents are present under:

```text
docs/
  01_ARCHITECTURE.md
  02_ENGINEERING.md
  03_SCHEMAS.md
  04_IMPLEMENTATION.md
```


# 2. Delivery Philosophy

## 2.1 Build Contracts Before Implementations

Define:

- protocols
- canonical models
- state transitions
- error types
- test contracts

before concrete infrastructure.

## 2.2 Build One Safe Path First

The first complete path should be:

```text
fixture
  -> raw record
  -> normalization
  -> canonical event
  -> in-process event bus
  -> strategy
  -> simulated execution
  -> portfolio update
```

This validates the architecture before external connectivity.

## 2.3 Test at Every Boundary

Every package boundary gets:

- unit tests
- contract tests where applicable
- integration tests where applicable
- failure-path tests

## 2.4 Preserve Replayability

Every new live-data feature should have a replay representation.

## 2.5 Keep Live Trading Disabled

Live submission code may exist only after:

- risk
- accounting
- reconciliation
- operator controls
- incident procedures

are implemented.

## 2.6 Ship in Demonstrable Milestones

Each phase should produce a runnable demonstration, not only internal classes.


# 3. High-Level Milestone Map

```text
M0  Repository Foundation
 |
M1  Canonical Types and Schemas
 |
M2  Event, Command, Clock, and Bus Core
 |
M3  Storage Foundation
 |
M4  Adapter Contracts and Fixture Harness
 |
M5  Kalshi Market Data
 |
M6  Polymarket Market Data
 |
M7  Normalization and Market Catalog
 |
M8  Replay Engine
 |
M9  Strategy Runtime and Baseline Strategies
 |
M10 Simulation Engine
 |
M11 Risk Engine
 |
M12 Portfolio and Accounting
 |
M13 Paper Trading
 |
M14 Shadow Trading
 |
M15 Live Execution
 |
M16 Market Matching
 |
M17 Cross-Exchange Arbitrage
 |
M18 Operations, Scaling, and Expansion
```

Dependency rule:

A milestone may begin exploratory work early, but may not be declared complete
before all required predecessor interfaces and gates are satisfied.


# 4. Milestone Status Model

Each milestone uses the following status values:

```text
NOT_STARTED
DESIGN_READY
IN_PROGRESS
CODE_COMPLETE
VALIDATION
OPERATIONAL_REVIEW
COMPLETE
BLOCKED
DEFERRED
```

A milestone enters `DESIGN_READY` when:

- scope is approved
- interfaces are defined
- acceptance criteria exist
- dependencies are known

A milestone enters `COMPLETE` when:

- code is merged
- required tests pass
- documentation is updated
- operational requirements are met
- no blocking defects remain


# 5. Repository Bootstrap

Create the repository with:

```text
prediction-market-platform/
|
+-- .github/
|   +-- workflows/
|   +-- pull_request_template.md
|   +-- ISSUE_TEMPLATE/
|
+-- docs/
|   +-- 01_ARCHITECTURE.md
|   +-- 02_ENGINEERING.md
|   +-- 03_SCHEMAS.md
|   +-- 04_IMPLEMENTATION.md
|   +-- adr/
|   +-- runbooks/
|
+-- src/
|   +-- pmrp/
|       +-- __init__.py
|
+-- tests/
|   +-- unit/
|   +-- integration/
|   +-- contract/
|   +-- replay/
|   +-- simulation/
|   +-- end_to_end/
|   +-- fixtures/
|
+-- migrations/
+-- scripts/
+-- notebooks/
+-- examples/
+-- docker/
+-- .python-version
+-- pyproject.toml
+-- uv.lock
+-- .pre-commit-config.yaml
+-- .gitignore
+-- README.md
+-- CONTRIBUTING.md
+-- SECURITY.md
+-- LICENSE
+-- Makefile
```

The repository should build before any business implementation is added.


# 6. Milestone M0 - Repository Foundation

## 6.1 Objective

Create a reproducible, typed, tested Python project with continuous integration.

## 6.2 Deliverables

- Python 3.13 pin
- `pyproject.toml`
- `uv.lock`
- source layout
- test layout
- Ruff configuration
- mypy configuration
- pytest configuration
- coverage configuration
- pre-commit configuration
- CI workflow
- package build
- contribution guide
- security policy
- pull-request template

## 6.3 Tasks

1. initialize Git repository
2. create package metadata
3. configure uv
4. create source package
5. create test directories
6. configure Ruff
7. configure mypy
8. configure pytest markers
9. configure coverage threshold
10. configure pre-commit
11. configure GitHub Actions
12. add package build job
13. add basic health test
14. document local setup

## 6.4 Acceptance Criteria

```text
[ ] uv sync --locked --all-groups succeeds.
[ ] uv run ruff format --check . succeeds.
[ ] uv run ruff check . succeeds.
[ ] uv run mypy src succeeds.
[ ] uv run pytest succeeds.
[ ] uv build succeeds.
[ ] CI runs on pull requests.
[ ] Main branch protection is documented.
[ ] No secrets are committed.
```

## 6.5 Demonstration

A clean checkout can be installed and validated using one documented command.


# 7. M0 Pull Request Sequence

Recommended pull requests:

### PR M0-01 - Repository skeleton

Includes:

- directories
- package metadata
- README
- license
- Python pin

### PR M0-02 - Quality tooling

Includes:

- Ruff
- mypy
- pytest
- coverage
- pre-commit

### PR M0-03 - Continuous integration

Includes:

- GitHub Actions
- package build
- test reports
- branch protection documentation

### PR M0-04 - Contribution and security docs

Includes:

- CONTRIBUTING.md
- SECURITY.md
- PR template
- issue templates


# 8. Milestone M1 - Canonical Types and Schemas

## 8.1 Objective

Implement the foundational canonical types defined in `03_SCHEMAS.md`.

## 8.2 Package Layout

```text
src/pmrp/
  schemas/
    __init__.py
    base.py
    identifiers.py
    enums.py
    numeric.py
    time.py
    metadata.py
    markets.py
    market_data.py
    orders.py
    portfolio.py
    risk.py
    strategy.py
    models.py
    matching.py
    replay.py
    simulation.py
    system.py
    commands.py
    events.py
    api.py
    serialization.py
    versions.py
```

## 8.3 First Schema Slice

Implement first:

- CanonicalModel
- identifiers
- enums
- Price
- Probability
- Quantity
- Money
- EventEnvelope
- CommandEnvelope

## 8.4 Second Schema Slice

Implement:

- Market
- Outcome
- Contract
- OrderBookLevel
- OrderBookSnapshot
- OrderBookDelta
- Trade

## 8.5 Third Schema Slice

Implement:

- Signal
- OrderIntent
- ApprovedOrder
- Order
- Fill
- Position
- CashBalance

## 8.6 Fourth Schema Slice

Implement:

- RiskLimit
- RiskDecision
- KillSwitchState
- ReplayManifest
- SimulationConfiguration
- ServiceHealth

## 8.7 Acceptance Criteria

```text
[ ] All public schemas are immutable.
[ ] Extra canonical fields are rejected.
[ ] Decimal values reject float input where required.
[ ] Datetimes reject naive values.
[ ] JSON round trips are exact.
[ ] JSON Schema generation works.
[ ] Schema registry exists.
[ ] Required validation invariants are tested.
[ ] Coverage meets repository threshold.
```


# 9. M1 Test Plan

Unit tests:

- identifier validation
- enum serialization
- Decimal float rejection
- probability bounds
- quantity bounds
- money currency validation
- datetime awareness
- event envelope validation
- command envelope validation
- order invariants
- cash balance invariants

Property tests:

- Decimal round trip
- probability closed interval
- order quantity invariant
- balance invariant
- stable serialization
- stable hashing

Compatibility tests:

- JSON Schema snapshot
- schema registry lookup
- unknown field rejection
- version lookup


# 10. M1 Coding-Agent Work Packet

Suggested coding-agent prompt:

```text
Implement the foundational canonical schema package for PMRP.

Read:
- docs/01_ARCHITECTURE.md
- docs/02_ENGINEERING.md
- docs/03_SCHEMAS.md

Scope:
- src/pmrp/schemas/base.py
- src/pmrp/schemas/identifiers.py
- src/pmrp/schemas/enums.py
- src/pmrp/schemas/numeric.py
- src/pmrp/schemas/time.py
- tests/unit/schemas/

Requirements:
- Python 3.13
- Pydantic
- frozen models
- extra fields forbidden
- Decimal values must reject float input
- UTC-aware datetime validation
- complete type annotations
- unit and property tests
- no database or exchange code

Do not modify unrelated files.
Run Ruff, mypy, and pytest before finishing.
```


# 11. Milestone M2 - Event, Command, Clock, and Bus Core

## 11.1 Objective

Create the in-process runtime primitives used by live, replay, and simulation.

## 11.2 Packages

```text
src/pmrp/
  events/
    registry.py
    factory.py
    serialization.py
  commands/
    registry.py
    dispatcher.py
  clock/
    protocol.py
    system.py
    frozen.py
    replay.py
  bus/
    protocol.py
    in_process.py
    subscription.py
    errors.py
```

## 11.3 Event Factory

Responsibilities:

- create event IDs
- create correlation IDs
- set timestamps through injected clock
- apply schema version
- attach quality flags
- attach replay or simulation session IDs

## 11.4 Command Dispatcher

Responsibilities:

- register handlers
- validate command type
- enforce idempotency hook
- propagate correlation context
- classify handler failures

## 11.5 In-Process Event Bus

Required behavior:

- typed subscriptions
- named consumers
- bounded queues
- deterministic mode
- partition key support
- consumer failure isolation
- health reporting
- graceful shutdown

## 11.6 Clock Implementations

Implement:

- SystemClock
- FrozenClock
- ReplayClock
- AdvancingTestClock

## 11.7 Acceptance Criteria

```text
[ ] No domain code calls wall-clock time directly.
[ ] Event bus queues are bounded.
[ ] Consumer exceptions do not stop unrelated consumers.
[ ] Deterministic ordering is tested.
[ ] Cancellation and shutdown are tested.
[ ] Command handlers receive correlation context.
[ ] Duplicate command hook exists.
```


# 12. M2 Event Bus Test Matrix

```text
Scenario                          Expected Result
-------------------------------------------------------------
single publisher                  subscriber receives event
multiple subscribers              each receives event
full queue                        configured backpressure occurs
consumer exception                other consumers continue
shutdown                          pending tasks terminate cleanly
duplicate publish                 behavior is explicit
partitioned events                partition ordering preserved
deterministic mode                stable ordering across runs
cancel subscriber                 resources are released
unsupported event                rejected or ignored by policy
```


# 13. Milestone M3 - Storage Foundation

## 13.1 Objective

Create the PostgreSQL-backed raw store, event store, and repository foundation.

## 13.2 Packages

```text
src/pmrp/storage/
  database.py
  session.py
  transactions.py
  raw_store.py
  event_store.py
  repositories/
  models/
  mappers/
  errors.py
```

## 13.3 Database Deliverables

- async SQLAlchemy engine
- async session factory
- transaction context
- connection health check
- migration bootstrap
- repository protocols
- optimistic concurrency support

## 13.4 Initial Tables

- raw_exchange_records
- canonical_events
- processed_events
- dead_letter_records
- schema_registry
- service_health_snapshots

## 13.5 Raw Store

Methods:

```python
async def append(record: RawExchangeRecord) -> None
async def get(raw_record_id: str) -> RawExchangeRecord | None
async def stream(query: RawRecordQuery) -> AsyncIterator[RawExchangeRecord]
```

## 13.6 Event Store

Methods:

```python
async def append(event: CanonicalEvent) -> None
async def append_many(events: Sequence[CanonicalEvent]) -> None
async def get(event_id: str) -> CanonicalEvent | None
async def stream(query: EventQuery) -> AsyncIterator[CanonicalEvent]
```

## 13.7 Acceptance Criteria

```text
[ ] Migrations apply to empty database.
[ ] Migrations upgrade from previous revision.
[ ] Raw records persist exactly.
[ ] Canonical events round trip exactly.
[ ] Duplicate event IDs are rejected idempotently.
[ ] Event queries use explicit ordering.
[ ] Database failures are classified.
[ ] Integration tests run in CI.
```


# 14. M3 Migration Sequence

Recommended migrations:

```text
0001_create_schema_registry
0002_create_raw_exchange_records
0003_create_canonical_events
0004_create_processed_events
0005_create_dead_letter_records
0006_create_health_snapshots
```

Each migration should include:

- upgrade
- downgrade where safe
- index rationale
- lock-risk note
- representative test


# 15. Milestone M4 - Adapter Contracts and Fixture Harness

## 15.1 Objective

Define the common exchange adapter interface and contract-test harness before
implementing live adapters.

## 15.2 Packages

```text
src/pmrp/adapters/
  base/
    protocol.py
    capabilities.py
    health.py
    errors.py
    requests.py
    responses.py
    rate_limits.py
tests/contract/adapters/
  test_adapter_contract.py
```

## 15.3 Required Adapter Operations

- connect
- disconnect
- health
- list markets
- subscribe market data
- place order
- cancel order
- get open orders
- get positions
- get balances
- get recent fills

## 15.4 Capability Model

Define:

- supported order types
- supported time-in-force values
- post-only support
- replace-order support
- client order ID support
- streaming order updates
- historical-data support
- sequence-number support
- batch endpoint support

## 15.5 Fixture Adapter

Implement a deterministic fixture adapter that:

- reads test payloads
- emits raw exchange records
- simulates connection state
- simulates rate limits
- simulates failures
- supports contract tests

## 15.6 Acceptance Criteria

```text
[ ] Adapter protocol is typed.
[ ] Capability model is complete.
[ ] Common contract suite exists.
[ ] Fixture adapter passes contract suite.
[ ] Error taxonomy is implemented.
[ ] Adapter health model is implemented.
[ ] Rate-limit abstraction is tested.
```


# 16. Adapter Contract Acceptance Matrix

```text
Contract Area               Required
-------------------------------------------------
connect success             yes
disconnect success          yes
double disconnect           idempotent
authentication failure      classified
transport timeout           classified
market listing              normalized raw model
subscription lifecycle      deterministic
sequence gap                surfaced
order submission            typed acknowledgement
ambiguous submission        explicit error
cancel                      typed acknowledgement
open-order query            supported
position query              supported
balance query               supported
rate limit                  visible
health                      visible
shutdown                    graceful
```


# 17. Milestone M5 - Kalshi Market-Data Adapter

## 17.1 Objective

Collect and normalize Kalshi market metadata, order books, and trades.

## 17.2 Package Layout

```text
src/pmrp/adapters/kalshi/
  authentication.py
  client.py
  websocket.py
  rest.py
  raw_models.py
  mapper.py
  rate_limits.py
  capabilities.py
  errors.py
  health.py
```

## 17.3 Phase A Scope

- authentication
- list markets
- fetch market details
- connect WebSocket
- subscribe order books
- subscribe trades
- preserve raw payloads
- emit raw records
- fixture coverage
- reconnect
- heartbeat
- sequence validation

## 17.4 Deferred Scope

- live order placement
- cancellation
- account positions
- balances
- fills
- settlement execution

These are implemented after execution and accounting foundations.

## 17.5 Acceptance Criteria

```text
[ ] Public market endpoints map correctly.
[ ] Raw payloads are stored.
[ ] WebSocket reconnect is tested.
[ ] Sequence gaps invalidate local books.
[ ] Snapshot recovery is tested.
[ ] Malformed payloads create data-quality findings.
[ ] Adapter passes applicable common contracts.
[ ] No strategy imports Kalshi modules.
```


# 18. M5 Fixture Requirements

Required Kalshi fixture categories:

```text
markets/
  list_success.json
  optional_fields.json
  unknown_status.json

order_book/
  snapshot.json
  delta_insert.json
  delta_update.json
  delta_delete.json
  duplicate_sequence.json
  sequence_gap.json

trades/
  trade.json
  duplicate_trade.json
  missing_optional_field.json

errors/
  unauthorized.json
  rate_limited.json
  service_error.json
  malformed.json
```


# 19. Milestone M6 - Polymarket Market-Data Adapter

## 19.1 Objective

Collect and normalize Polymarket market metadata, order books, and trades.

## 19.2 Package Layout

```text
src/pmrp/adapters/polymarket/
  authentication.py
  clob_client.py
  websocket.py
  rest.py
  raw_models.py
  mapper.py
  chain_metadata.py
  rate_limits.py
  capabilities.py
  errors.py
  health.py
```

## 19.3 Phase A Scope

- market discovery
- token and outcome mapping
- order-book snapshots
- order-book updates
- trade observations
- raw payload storage
- reconnect
- heartbeat
- sequence or consistency validation
- chain metadata capture where required

## 19.4 Time Semantics

The adapter must distinguish:

- exchange API time
- local receive time
- blockchain time
- finality-related time where relevant

## 19.5 Acceptance Criteria

```text
[ ] Outcome token mapping is explicit.
[ ] Market metadata maps to canonical IDs.
[ ] Raw payloads are preserved.
[ ] Reconnect and resubscribe are tested.
[ ] Unknown token relationships are quarantined.
[ ] Adapter passes applicable common contracts.
[ ] No chain-specific details leak into strategies.
```


# 20. Milestone M7 - Normalization and Market Catalog

## 20.1 Objective

Convert raw adapter records into canonical market and market-data events.

## 20.2 Packages

```text
src/pmrp/normalization/
  pipeline.py
  registry.py
  result.py
  errors.py
  quality.py
  kalshi.py
  polymarket.py

src/pmrp/markets/
  catalog.py
  repository.py
  identifiers.py
  lifecycle.py
```

## 20.3 Normalization Flow

```text
RawExchangeRecord
  |
adapter-specific parser
  |
validated transport model
  |
canonical mapper
  |
quality checks
  |
canonical event
  |
event store
  |
event bus
```

## 20.4 Market Catalog Responsibilities

- canonical market ID allocation
- external ID lookup
- market metadata projection
- outcome projection
- contract projection
- lifecycle state
- precision rules

## 20.5 Acceptance Criteria

```text
[ ] Every raw record has a normalization result.
[ ] Successful records produce canonical events.
[ ] Failed records create data-quality findings.
[ ] Canonical market IDs remain stable.
[ ] Duplicate records are idempotent.
[ ] Market lifecycle transitions are validated.
[ ] Order-book projection rejects sequence gaps.
[ ] Cross-exchange code is not yet required.
```


# 21. M7 Normalization Result Model

Recommended result type:

```python
class NormalizationResult(CanonicalModel):
    raw_record_id: str
    accepted: bool

    events: tuple[CanonicalEvent, ...] = ()
    findings: tuple[DataQualityFinding, ...] = ()

    parser_version: str
    mapper_version: str

    normalized_at: datetime
```

A raw record may produce:

- zero events
- one event
- multiple events

The reason must be explicit.


# 22. Milestone M8 - Deterministic Replay

## 22.1 Objective

Replay canonical events using the same downstream contracts as live mode.

## 22.2 Packages

```text
src/pmrp/replay/
  manifest.py
  loader.py
  sorter.py
  clock.py
  engine.py
  controller.py
  results.py
  checksum.py
  errors.py
```

## 22.3 Features

- load event range
- validate dataset checksum
- stable sort
- replay clock
- speed control
- pause
- resume
- seek
- event filters
- session metadata
- result checksum
- synthetic fault injection

## 22.4 Ordering Policy

Implement documented tie-break order:

1. occurred_at
2. exchange sequence
3. received_at
4. source partition
5. event ID

## 22.5 Replay Isolation

Replay dependency graph must not include live execution adapters.

Use a simulated or null execution gateway.

## 22.6 Acceptance Criteria

```text
[ ] Same manifest produces same result checksum.
[ ] Replay does not access network.
[ ] Replay does not read wall-clock time.
[ ] Replay does not mutate live tables.
[ ] Pause and resume are deterministic.
[ ] Seek behavior is documented and tested.
[ ] Replay events carry replay_session_id.
[ ] Golden replay fixtures exist.
```


# 23. M8 Golden Replay Dataset

Create one small repository fixture:

```text
tests/fixtures/replay/basic_market/
  manifest.json
  events.jsonl
  expected_signals.jsonl
  expected_orders.jsonl
  expected_portfolio.json
  checksum.txt
```

The scenario should include:

- market discovery
- order-book snapshot
- order-book delta
- trade
- strategy signal
- simulated order
- partial fill
- final fill
- portfolio update


# 24. Milestone M9 - Strategy Runtime

## 24.1 Objective

Run multiple isolated strategies against canonical events.

## 24.2 Packages

```text
src/pmrp/strategies/
  protocol.py
  context.py
  registry.py
  runtime.py
  lifecycle.py
  health.py
  state_store.py
  errors.py
  examples/
```

## 24.3 Strategy Context

Provide:

- Clock
- event subscription
- market-data views
- signal publisher
- order-intent publisher
- metrics
- structured logger
- read-only portfolio view
- read-only risk view
- feature access

Do not provide:

- exchange client
- database session
- secrets
- environment-variable access

## 24.4 Runtime Features

- register strategy type
- instantiate strategy
- initialize
- subscribe
- process events
- isolate failures
- drain
- stop
- restart policy
- health status
- state checkpoint

## 24.5 Acceptance Criteria

```text
[ ] Multiple strategies run concurrently.
[ ] Event ordering per strategy is stable.
[ ] Strategy exceptions are isolated.
[ ] Failed strategy cannot emit new intents.
[ ] Strategy lifecycle events are emitted.
[ ] Strategy configuration is validated.
[ ] Strategy code is unchanged between replay and paper modes.
```


# 25. Baseline Strategy Set

Implement simple, transparent strategies for validation.

## 25.1 Midpoint Observer

Behavior:

- consumes quotes
- calculates midpoint
- emits metrics
- no orders

Purpose:

- validate strategy runtime

## 25.2 Threshold Signal Strategy

Behavior:

- compares best ask to configured probability
- emits buy signal below threshold
- emits no live order initially

Purpose:

- validate signal pipeline

## 25.3 Simple Market Maker

Behavior:

- computes fixed spread around midpoint
- applies inventory skew
- emits order intents

Purpose:

- validate simulation and risk


# 26. Milestone M10 - Simulation Engine

## 26.1 Objective

Simulate exchange order behavior using configurable assumptions.

## 26.2 Packages

```text
src/pmrp/simulation/
  exchange.py
  order_book.py
  queue_models.py
  latency_models.py
  fill_models.py
  fee_models.py
  rejection_models.py
  slippage_models.py
  settlement.py
  scenarios.py
  results.py
```

## 26.3 Initial Models

Queue:

- immediate touch
- volume ahead

Latency:

- fixed latency

Fill:

- trade-through fill
- touch fill
- partial fill

Fees:

- exchange-specific configurable fee table

Rejections:

- invalid price
- invalid quantity
- market closed
- insufficient balance

## 26.4 Scenario Harness

A scenario defines:

- initial book
- scheduled market events
- order intents
- latency configuration
- expected fills
- expected final state

## 26.5 Acceptance Criteria

```text
[ ] Fixed seed produces deterministic results.
[ ] Partial fills work.
[ ] Cancel-fill races work.
[ ] Latency affects activation time.
[ ] Fees use Decimal.
[ ] Invalid orders are rejected.
[ ] Scenario results are reproducible.
[ ] Simulator never submits live orders.
```


# 27. M10 Simulation Scenario Catalog

Required scenarios:

```text
SIM-001 limit order immediately marketable
SIM-002 passive order no fill
SIM-003 passive order partial fill
SIM-004 passive order full fill
SIM-005 cancel before activation
SIM-006 fill during cancel race
SIM-007 stale quote after latency
SIM-008 market closes before activation
SIM-009 insufficient simulated balance
SIM-010 post-only order would cross
SIM-011 fee calculation
SIM-012 settlement payout
SIM-013 disconnect while order open
SIM-014 duplicate market event
SIM-015 multi-leg imbalance
```


# 28. Milestone M11 - Risk Engine

## 28.1 Objective

Implement centralized pre-trade and post-trade risk.

## 28.2 Packages

```text
src/pmrp/risk/
  engine.py
  context.py
  decisions.py
  limits.py
  rules/
    strategy_enabled.py
    exchange_enabled.py
    market_enabled.py
    market_open.py
    data_freshness.py
    order_size.py
    order_notional.py
    position_limit.py
    exposure_limit.py
    daily_loss.py
    open_order_limit.py
    duplicate_guard.py
    balance.py
    reconciliation.py
    kill_switch.py
  breaches.py
  kill_switches.py
  health.py
```

## 28.3 Pre-Trade Flow

```text
OrderIntent
  |
RiskInputSnapshot
  |
Rule Evaluation
  |
RiskDecision
  |
ApprovedOrder or Rejection
```

## 28.4 Required Rules

Implement RISK-001 through RISK-020 from the architecture documents.

## 28.5 Concurrency Control

Risk must account for:

- current positions
- open orders
- concurrently approved but unsubmitted orders
- pending cancels
- multi-leg reservations

Use reservations to prevent simultaneous approvals from exceeding limits.

## 28.6 Acceptance Criteria

```text
[ ] Every approved order references a risk decision.
[ ] Missing required state rejects the intent.
[ ] Stale market data rejects the intent.
[ ] Kill switches block approval.
[ ] Concurrent approvals respect limits.
[ ] Rule reason codes are stable.
[ ] Risk decisions are persisted.
[ ] Risk rule property tests pass.
```


# 29. M11 Risk Rule Implementation Template

Each rule should implement:

```python
class RiskRule(Protocol):
    @property
    def rule_id(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def evaluate(
        self,
        intent: OrderIntent,
        context: RiskContext,
    ) -> RiskRuleResult:
        ...
```

Each rule requires:

- unit tests
- boundary tests
- missing-input test
- stale-input test where relevant
- reason-code documentation


# 30. Milestone M12 - Portfolio and Accounting

## 30.1 Objective

Maintain exact positions, balances, PnL, fees, and reconciliation state.

## 30.2 Packages

```text
src/pmrp/portfolio/
  positions.py
  balances.py
  pnl.py
  fees.py
  settlement.py
  journal.py
  projections.py
  reconciliation.py
  repositories.py
  errors.py
```

## 30.3 Initial Accounting Method

Use weighted average cost unless an ADR selects another method.

Define:

- position sign
- realized PnL formula
- unrealized mark policy
- fee treatment
- settlement treatment
- correction treatment

## 30.4 Event Inputs

- Fill
- Fee
- Rebate
- Transfer
- Settlement
- ReconciliationCorrection

## 30.5 Reconciliation

Compare:

- open orders
- positions
- balances
- fills
- settlements

## 30.6 Acceptance Criteria

```text
[ ] Duplicate fills are idempotent.
[ ] Position quantity reconciles.
[ ] Fees are exact.
[ ] PnL uses Decimal.
[ ] Journal entries balance by currency.
[ ] Settlement updates positions and cash.
[ ] Unknown mismatch blocks live trading.
[ ] Reconciliation events are persisted.
```


# 31. M12 Accounting Test Matrix

```text
Scenario                              Required
------------------------------------------------------------
single buy fill                       yes
multiple buy fills                    yes
partial sell reduction                yes
position reversal                     yes
maker fee                             yes
taker fee                             yes
rebate                                yes
duplicate fill                        yes
out-of-order fill                     yes
settlement win                        yes
settlement loss                       yes
settlement correction                 yes
manual balance drift                  yes
journal balancing                     yes
```


# 32. Milestone M13 - Paper Trading

## 32.1 Objective

Run strategies against live market data with simulated execution and accounting.

## 32.2 Flow

```text
Live Exchange Data
  |
Canonical Events
  |
Strategy Runtime
  |
Risk Engine
  |
Simulation Engine
  |
Simulated Fills
  |
Portfolio
```

## 32.3 Required Features

- live data subscriptions
- strategy runtime
- risk checks
- simulated account
- paper order history
- paper fills
- paper portfolio
- metrics
- operator status
- session manifest

## 32.4 Acceptance Criteria

```text
[ ] No live order gateway is present in dependency graph.
[ ] Live data drives paper decisions.
[ ] Simulated fills update paper portfolio.
[ ] Paper sessions are reproducible where inputs are archived.
[ ] Strategy failures are isolated.
[ ] Risk rules still apply.
[ ] Operator can stop a strategy.
[ ] Kill switch stops paper order flow.
```


# 33. Paper Trading Demonstration

The milestone demo should:

1. connect to one exchange market-data feed
2. run a threshold strategy
3. produce signals
4. pass intents through risk
5. simulate orders
6. produce fills
7. display paper position
8. display PnL
9. stop cleanly
10. archive the session manifest


# 34. Milestone M14 - Shadow Trading

## 34.1 Objective

Run the full live decision pipeline without sending orders.

## 34.2 Shadow Behavior

For each approved order:

- record the exact exchange request that would have been sent
- record decision latency
- record hypothetical submission time
- observe subsequent market data
- estimate fill outcome
- compare expected and observed execution

## 34.3 Packages

```text
src/pmrp/shadow/
  gateway.py
  evaluator.py
  outcomes.py
  reports.py
```

## 34.4 Acceptance Criteria

```text
[ ] No exchange order submission occurs.
[ ] Exact hypothetical request is persisted.
[ ] Decision lineage is complete.
[ ] Hypothetical outcomes are evaluated.
[ ] Shadow and replay results can be compared.
[ ] Operator UI clearly labels shadow mode.
[ ] Production credentials are not required for order submission.
```


# 35. Shadow Evaluation Metrics

Measure:

- signal-to-intent latency
- intent-to-risk latency
- risk-to-hypothetical-submit latency
- hypothetical fill rate
- expected versus observed price
- adverse selection
- missed opportunities
- cancellation effectiveness
- strategy PnL estimate
- limit utilization
- risk rejection rate


# 36. Milestone M15 - Live Execution Foundation

## 36.1 Objective

Implement tightly controlled live order submission.

## 36.2 Preconditions

M15 cannot begin operational validation until:

- M11 risk complete
- M12 portfolio complete
- M14 shadow complete
- adapter reconciliation implemented
- kill switches tested
- operator controls available
- runbooks approved

## 36.3 Packages

```text
src/pmrp/execution/
  gateway.py
  router.py
  state_machine.py
  idempotency.py
  retries.py
  reconciliation.py
  reservations.py
  errors.py
```

## 36.4 Adapter Expansion

Add to Kalshi and Polymarket adapters:

- place order
- cancel order
- get open orders
- get positions
- get balances
- get fills
- order update stream

## 36.5 Live Gating

Live gateway starts only when:

- live flag enabled
- production environment explicit
- credentials valid
- adapter healthy
- market data fresh
- risk healthy
- reconciliation healthy
- kill switch clear
- operator authorization present

## 36.6 Acceptance Criteria

```text
[ ] Order state machine covers all transitions.
[ ] Idempotency is enforced.
[ ] Ambiguous submission triggers reconciliation.
[ ] Reconnect blocks trading until reconciliation.
[ ] Live gateway cannot start in test or replay mode.
[ ] Every order has full lineage.
[ ] Every fill updates portfolio once.
[ ] Global kill switch is tested end to end.
```


# 37. M15 Safe Rollout Plan

Stage 1:

- one exchange
- one account
- one market
- one strategy
- minimal quantity
- manual approval

Stage 2:

- small market set
- strict daily loss
- automatic kill switch
- continuous operator monitoring

Stage 3:

- more markets
- still one exchange
- controlled capital increase

Stage 4:

- second exchange
- independent limits
- cross-exchange reconciliation

No stage advances without written review.


# 38. Live Execution Incident Tests

Before production enablement, run controlled tests for:

- network timeout before acknowledgement
- duplicate submit retry
- reject after risk approval
- partial fill before cancel
- fill after disconnect
- sequence gap during open orders
- stale data
- database interruption
- portfolio mismatch
- kill switch during order flow
- credential expiration
- exchange maintenance state


# 39. Milestone M16 - Market Matching

## 39.1 Objective

Identify and validate relationships between markets across exchanges.

## 39.2 Packages

```text
src/pmrp/matching/
  candidates.py
  metadata_filters.py
  entities.py
  embeddings.py
  llm_analysis.py
  validators.py
  relationships.py
  review.py
  registry.py
```

## 39.3 Pipeline

```text
market metadata
  |
deterministic filters
  |
entity extraction
  |
embedding similarity
  |
structured LLM proposal
  |
deterministic validation
  |
human review if needed
  |
relationship registry
```

## 39.4 Initial Deterministic Checks

- same event entity
- same date window
- same threshold
- same unit
- same jurisdiction
- same settlement source
- compatible outcomes
- compatible resolution rule

## 39.5 LLM Restrictions

LLM output may:

- propose relationship
- extract entities
- summarize rules
- identify ambiguity

LLM output may not:

- authorize live arbitrage
- bypass deterministic validation
- set risk limits
- modify settlement state

## 39.6 Acceptance Criteria

```text
[ ] Candidate generation is reproducible.
[ ] Rule extraction is persisted.
[ ] Relationship evidence is stored.
[ ] Deterministic validator is versioned.
[ ] Human review state exists.
[ ] Live arbitrage uses only approved relationships.
[ ] False-positive fixtures are tested.
```


# 40. Market Matching Fixture Set

Fixture groups:

```text
equivalent/
  same_fed_decision_different_wording
  same_election_winner_different_labels

complement/
  yes_market_vs_no_market

subset_superset/
  candidate_wins_state_vs_candidate_wins_election

not_equivalent/
  different_resolution_source
  different_close_date
  different_threshold
  different jurisdiction
  ambiguous settlement language
```


# 41. Milestone M17 - Cross-Exchange Arbitrage

## 41.1 Objective

Detect and safely execute approved cross-exchange arbitrage opportunities.

## 41.2 Packages

```text
src/pmrp/arbitrage/
  detector.py
  pricing.py
  fees.py
  slippage.py
  plans.py
  coordinator.py
  hedge.py
  recovery.py
  metrics.py
```

## 41.3 Detection Inputs

- approved market relationships
- live order books
- fee schedules
- slippage assumptions
- capital availability
- settlement compatibility
- exchange health
- transfer constraints

## 41.4 Coordinator Responsibilities

- validate opportunity freshness
- reserve capital
- create execution plan
- submit legs
- track acknowledgements
- track fills
- enforce hedge timeout
- recover from partial failure
- release reservations
- emit full audit trail

## 41.5 Acceptance Criteria

```text
[ ] Net edge includes fees and slippage.
[ ] Stale opportunities are rejected.
[ ] Capital is reserved before submission.
[ ] Leg state is explicit.
[ ] Partial failure triggers recovery.
[ ] Maximum unhedged exposure is enforced.
[ ] Simulation scenarios pass.
[ ] Live rollout requires separate approval.
```


# 42. Arbitrage Simulation Scenarios

Required scenarios:

- both legs fill
- first leg fills, second rejects
- first leg partial fill
- second leg delayed
- opportunity disappears before submission
- fee changes
- one exchange disconnects
- settlement-rule mismatch discovered
- hedge timeout exceeded
- capital reservation conflict
- duplicate fill event
- kill switch during execution


# 43. Milestone M18 - Operations and Scaling

## 43.1 Objective

Harden the platform for sustained operation and future growth.

## 43.2 Workstreams

- monitoring dashboards
- alerting
- service-level objectives
- backup and restore
- object storage archival
- event partitioning
- database retention
- performance profiling
- capacity testing
- deployment automation
- incident exercises
- release automation
- security review

## 43.3 Optional Scaling Work

Only after profiling:

- process separation
- Redis
- external broker
- dedicated collector
- dedicated execution gateway
- compiled high-throughput service

## 43.4 Acceptance Criteria

```text
[ ] Backup and restore are tested.
[ ] Incident runbooks exist.
[ ] Alert thresholds are defined.
[ ] Capacity limits are measured.
[ ] Replay archives are durable.
[ ] Deployment rollback is tested.
[ ] Security review is complete.
[ ] Performance work has baseline evidence.
```


# 44. Cross-Cutting Workstream - Configuration

Implement typed configuration early and expand it with each milestone.

Initial classes:

- AppConfig
- DatabaseConfig
- LoggingConfig
- TestingConfig

Add later:

- AdapterConfig
- ReplayConfig
- StrategyConfig
- SimulationConfig
- RiskConfig
- PortfolioConfig
- ExecutionConfig
- MonitoringConfig
- SecurityConfig

Every new configuration field requires:

- type
- default policy
- environment scope
- documentation
- validation
- test
- redaction classification


# 45. Cross-Cutting Workstream - Observability

Add observability in the same pull request as behavior.

Every component should define:

- log events
- metrics
- health state
- trading impact

Minimum early metrics:

- raw records received
- canonical events emitted
- normalization failures
- queue depth
- storage latency
- replay throughput
- strategy failures
- risk rejections
- simulated fills

Do not postpone observability until production.


# 46. Cross-Cutting Workstream - Security

Security tasks by phase:

M0:

- secret scanning
- SECURITY.md
- dependency lock

M3:

- database credential handling
- redaction

M5-M6:

- exchange credential isolation
- request logging redaction

M14:

- shadow environment separation

M15:

- production credential policy
- operator authorization
- audit logs
- withdrawal permission review

M18:

- security review
- container scan
- release attestation


# 47. Cross-Cutting Workstream - Documentation

Every milestone updates:

- README
- package documentation
- configuration examples
- runbooks where needed
- ADRs when required
- schema registry
- changelog or release notes

Documentation pull requests should not lag multiple milestones behind the code.


# 48. Cross-Cutting Workstream - Data Management

Data work includes:

- fixture naming
- raw archive format
- canonical archive format
- checksums
- retention
- Parquet exports
- test dataset manifests
- license or source notes
- redaction

No test or replay should silently fetch mutable external data.


# 49. Application Composition

Create explicit runtime builders:

```python
def build_collector_app(config: AppConfig) -> CollectorApp: ...
def build_replay_app(config: AppConfig) -> ReplayApp: ...
def build_paper_app(config: AppConfig) -> PaperApp: ...
def build_shadow_app(config: AppConfig) -> ShadowApp: ...
def build_live_app(config: AppConfig) -> LiveApp: ...
```

Each builder wires a distinct dependency graph.

The replay builder must not have access to live order adapters.

The live builder must require all safety dependencies.


# 50. Dependency Injection Plan

Use constructor injection.

Avoid a global service container.

Example:

```python
class ReplayEngine:
    def __init__(
        self,
        *,
        clock: ReplayClock,
        event_store: EventStore,
        event_bus: EventBus,
        result_writer: ReplayResultWriter,
    ) -> None:
        ...
```

Benefits:

- testability
- explicit dependencies
- environment separation
- safer live gating


# 51. Package Initialization Order

Recommended source-package build order:

```text
pmrp.schemas
pmrp.clock
pmrp.events
pmrp.commands
pmrp.bus
pmrp.config
pmrp.monitoring
pmrp.storage
pmrp.adapters.base
pmrp.normalization
pmrp.markets
pmrp.replay
pmrp.strategies
pmrp.models
pmrp.simulation
pmrp.risk
pmrp.portfolio
pmrp.execution
pmrp.shadow
pmrp.matching
pmrp.arbitrage
pmrp.operator_api
pmrp.cli
pmrp.app
```

Some packages can be developed in parallel after their interfaces stabilize.


# 52. Database Implementation Order

Recommended table order:

1. schema_registry
2. raw_exchange_records
3. canonical_events
4. processed_events
5. dead_letter_records
6. markets
7. outcomes
8. contracts
9. order_book_snapshots
10. orders
11. order_state_transitions
12. fills
13. positions
14. cash_balances
15. risk_limits
16. risk_decisions
17. kill_switches
18. reconciliation_runs
19. market_relationships
20. replay_sessions
21. simulation_sessions
22. strategy_instances
23. signal_records
24. audit_records


# 53. CLI Implementation Plan

Initial commands:

```text
pmrp doctor
pmrp config validate
pmrp db upgrade
pmrp db current
pmrp fixtures validate
pmrp replay run
pmrp replay inspect
pmrp strategy list
pmrp strategy validate
```

Later commands:

```text
pmrp collector start
pmrp paper start
pmrp shadow start
pmrp trade start
pmrp reconcile account
pmrp risk status
pmrp risk kill-switch activate
pmrp risk kill-switch release
```

Dangerous commands require explicit environment and confirmation flags.


# 54. Operator API Implementation Plan

Implement after paper trading is functional.

Read endpoints:

- health
- exchanges
- strategies
- orders
- positions
- balances
- risk status
- kill switches
- replay sessions

Control endpoints:

- start strategy
- stop strategy
- activate kill switch
- release kill switch
- trigger reconciliation
- pause replay
- resume replay

Requirements:

- authentication
- authorization
- audit
- idempotency
- correlation IDs
- no secret exposure


# 55. Research Notebook Integration

Provide a small library for notebooks:

```python
from pmrp.research import load_events, run_replay, summarize_results
```

Notebook APIs should:

- use canonical datasets
- use manifest metadata
- return typed result objects
- avoid hidden global state
- avoid direct production database access
- support deterministic seeds


# 56. Feature Store Implementation Plan

Phase 1:

- in-process feature calculation
- persisted FeatureSnapshot
- source event IDs

Phase 2:

- batch feature export
- Parquet feature datasets
- experiment integration

Phase 3:

- online feature cache if justified
- shared feature service if justified

Do not build a distributed feature store before strategy requirements exist.


# 57. Model Registry Implementation Plan

Initial model registry may be database-backed.

Required operations:

- register artifact
- validate metadata
- resolve approved version
- verify checksum
- load artifact
- record usage
- revoke artifact

A model cannot be used in live mode unless approval state permits it.


# 58. Replay Dataset Tooling

Provide scripts or CLI for:

- export event range
- validate archive
- compute checksum
- inspect event counts
- inspect schema versions
- redact raw payloads
- convert JSONL to Parquet
- create manifest
- compare replay results

Dataset tooling should stream large files.


# 59. Fixture Generation Tooling

Provide controlled fixture capture:

```text
pmrp fixtures capture --exchange kalshi --channel order_book
pmrp fixtures redact
pmrp fixtures validate
```

Capture tooling must:

- remove credentials
- remove account-specific sensitive data
- attach source metadata
- attach capture date
- attach schema version
- produce stable filenames


# 60. Release Train

Suggested pre-1.0 release sequence:

```text
0.1.0 repository and schemas
0.2.0 storage and fixture adapter
0.3.0 Kalshi market data
0.4.0 Polymarket market data
0.5.0 replay and strategies
0.6.0 simulation and risk
0.7.0 portfolio and paper trading
0.8.0 shadow trading
0.9.0 limited live execution
1.0.0 stable platform contracts
```

Versions may change, but each release should represent a coherent capability.


# 61. Branch and Pull Request Strategy

Use short-lived branches.

Recommended maximum scope:

- one interface
- one schema group
- one repository
- one adapter endpoint family
- one risk rule family
- one simulator model

Avoid pull requests that simultaneously:

- redesign schemas
- change storage
- add live execution
- alter risk
- refactor unrelated modules

Large generated changes should be split before review.


# 62. Pull Request Dependency Labels

Suggested labels:

```text
area:schemas
area:storage
area:adapter
area:replay
area:strategy
area:simulation
area:risk
area:portfolio
area:execution
area:matching
area:operations

risk:low
risk:normal
risk:high
risk:live

type:feature
type:fix
type:refactor
type:docs
type:migration
type:security
```


# 63. Issue Template for Implementation Work

Each implementation issue should include:

```text
Goal
Scope
Non-Scope
Owning Package
Dependencies
Interfaces
Schemas
Acceptance Criteria
Tests
Observability
Security
Migration
Replay Impact
Operational Impact
```


# 64. Milestone Gate Review

At the end of each milestone, review:

- functionality
- test evidence
- architecture conformance
- schema conformance
- operational readiness
- documentation
- unresolved risks
- next milestone dependencies

A milestone gate should produce a short decision record:

```text
approved
approved_with_followups
blocked
deferred
```


# 65. Architecture Conformance Tests

Implement tests or static checks for:

- strategy packages do not import adapters
- domain packages do not import SQLAlchemy
- replay does not import live execution gateway
- test and replay builders do not require credentials
- money fields do not use float
- canonical models are frozen
- queues are bounded
- live builder requires risk and reconciliation


# 66. Code Generation Policy

Code generation may be used for:

- JSON Schema files
- client SDK stubs
- database model boilerplate
- event registry tables
- documentation tables

Generated files must be:

- reproducible
- clearly marked
- generated from committed sources
- checked in only when useful
- validated in CI

Do not hand-edit generated files.


# 67. Coding-Agent Operating Model

Coding agents should work in bounded packets.

Good packet:

```text
Implement Market, Outcome, and Contract schemas with tests.
```

Bad packet:

```text
Build the whole platform.
```

Each packet should provide:

- exact files
- governing docs
- acceptance criteria
- tests
- prohibited areas
- required commands

Agent output should be reviewed before the next packet depends on it.


# 68. Coding-Agent Review Checklist

Review agent-generated code for:

- invented exchange behavior
- invented library APIs
- broad exception handling
- missing timeouts
- unbounded queues
- float use
- weak types
- missing idempotency
- missing tests
- brittle fixtures
- architecture leakage
- hidden global state
- incomplete shutdown
- live safety bypass


# 69. Parallel Workstreams

After M4, work can proceed in parallel.

Track A:

- Kalshi adapter

Track B:

- Polymarket adapter

Track C:

- storage performance
- replay tooling

Track D:

- strategy framework
- baseline models

Track E:

- documentation
- observability
- operator API design

Parallel work must still use stable shared interfaces.


# 70. Critical Path

The critical path to useful research is:

```text
M0 -> M1 -> M2 -> M3 -> M4 -> M7 -> M8 -> M9 -> M10
```

The critical path to safe live trading is:

```text
M0 -> M1 -> M2 -> M3 -> M4 -> adapters -> M7 -> M11 -> M12 -> M14 -> M15
```

Market matching and arbitrage are not required for the first live single-market
strategy.


# 71. Deferred Decisions

Defer until evidence exists:

- Kafka versus Redpanda
- Redis requirement
- Kubernetes
- Go service extraction
- distributed feature store
- GPU serving
- dedicated event-sourcing database
- complex workflow engine
- multi-region deployment
- automated capital allocation


# 72. Technical Debt Policy

Technical debt must be explicit.

A debt item records:

- issue
- reason
- risk
- scope
- owner
- due milestone
- removal criteria

Safety-critical TODO comments are prohibited without an issue reference.

Debt that blocks deterministic replay, accounting, risk, or security should not
be deferred into live release.


# 73. Performance Validation Plan

Performance benchmarks by milestone:

M3:

- raw write throughput
- event write throughput
- query latency

M8:

- replay events per second
- memory usage

M9:

- strategy processing latency

M10:

- simulation throughput

M15:

- order submit latency
- acknowledgement latency
- reconciliation duration

M18:

- sustained-load test
- capacity limits


# 74. Capacity Test Plan

Capacity dimensions:

- number of markets
- events per second
- order-book depth
- number of strategies
- number of open orders
- event archive size
- replay duration
- database retention
- concurrent accounts

Test at:

- expected load
- two times expected load
- burst load
- dependency degradation


# 75. Data Retention Implementation Plan

Raw records:

- hot PostgreSQL retention
- compressed archive
- checksum manifest

Canonical events:

- queryable hot partition
- long-term archive
- replay export

Operational projections:

- current state
- historical snapshots when required

Logs:

- shorter hot retention
- archived incident evidence

Retention changes require documented data-loss impact.


# 76. Backup and Restore Plan

Implement before live trading:

- PostgreSQL backup
- restore test
- raw archive backup
- configuration snapshot backup
- model artifact backup
- migration history backup

Restore validation should confirm:

- schema version
- row counts
- event checksums
- portfolio state
- replay capability


# 77. Deployment Plan

Local:

- uv
- Docker Compose
- local PostgreSQL

Development:

- container deployment
- development credentials
- shared monitoring

Staging:

- production-like database
- shadow or sandbox credentials
- full reconciliation

Production:

- immutable images
- separate secrets
- controlled rollout
- health checks
- rollback
- audit


# 78. Environment Promotion Gates

Development to staging:

- CI complete
- migration tested
- integration tests complete
- configuration validated

Staging to shadow:

- live market-data stability
- operator API
- monitoring
- incident runbook

Shadow to live:

- shadow report reviewed
- risk review
- accounting reconciliation
- kill-switch drill
- production credentials
- explicit approval


# 79. Live Readiness Checklist

```text
[ ] Live environment is explicit.
[ ] Production credentials are separate.
[ ] Withdrawals are disabled where possible.
[ ] Adapter health is green.
[ ] Market data is fresh.
[ ] Open orders reconcile.
[ ] Positions reconcile.
[ ] Balances reconcile.
[ ] Risk engine is healthy.
[ ] Kill switches are tested.
[ ] Operator audit is active.
[ ] Database backups are current.
[ ] Rollback is documented.
[ ] Incident owner is assigned.
[ ] Capital limits are minimal.
```


# 80. First End-to-End Vertical Slice

The first full vertical slice should use fixtures, not live APIs.

Scenario:

1. load market fixture
2. persist raw record
3. normalize market event
4. publish event
5. build order-book snapshot
6. strategy emits signal
7. strategy emits order intent
8. risk approves
9. simulator accepts
10. simulator fills
11. portfolio updates
12. replay repeats the same result

This slice proves the architecture.


# 81. Second End-to-End Vertical Slice

The second vertical slice should use live market data and paper execution.

Scenario:

1. connect one adapter
2. subscribe one market
3. preserve raw payloads
4. normalize
5. run simple strategy
6. apply risk
7. simulate execution
8. update paper portfolio
9. stop cleanly
10. replay captured session


# 82. Third End-to-End Vertical Slice

The third vertical slice should use shadow mode.

Scenario:

1. connect live market data
2. run strategy
3. create approved order
4. generate exact hypothetical exchange request
5. do not submit
6. evaluate hypothetical fill
7. compare with simulation
8. produce shadow report


# 83. Fourth End-to-End Vertical Slice

The fourth vertical slice is limited live trading.

Scenario:

1. one approved market
2. one strategy
3. one minimal order
4. full pre-trade risk
5. live submit
6. acknowledgement
7. cancellation
8. fill or no fill
9. reconciliation
10. operator review


# 84. Acceptance Test Inventory

Repository-wide acceptance tests should eventually include:

```text
AT-001 clean setup
AT-002 schema round trip
AT-003 raw-to-canonical
AT-004 event bus isolation
AT-005 storage idempotency
AT-006 adapter reconnect
AT-007 replay determinism
AT-008 strategy isolation
AT-009 simulation partial fill
AT-010 risk rejection
AT-011 portfolio reconciliation
AT-012 paper trading
AT-013 shadow no-submit guarantee
AT-014 live gating
AT-015 kill switch
AT-016 market relationship approval
AT-017 arbitrage leg failure recovery
```


# 85. Definition of Done by Package

Every package should have:

- README or module documentation
- public interface
- typed implementation
- unit tests
- failure tests
- metrics
- structured logs
- health behavior
- configuration validation
- graceful shutdown if stateful
- no secret leakage
- no architecture violations


# 86. Release Artifact Inventory

Each release may include:

- Python wheel
- source distribution
- container image
- migration package
- JSON Schema bundle
- release notes
- checksum manifest
- SBOM
- replay fixture results
- configuration examples


# 87. Documentation Deliverables by Milestone

M0:

- README
- CONTRIBUTING
- SECURITY

M1:

- schema docs
- examples

M3:

- database setup
- migration guide

M5-M6:

- adapter setup
- fixture guide

M8:

- replay guide

M9:

- strategy authoring guide

M10:

- simulation guide

M11:

- risk rule guide

M12:

- accounting guide

M13:

- paper-trading guide

M14:

- shadow guide

M15:

- live runbooks


# 88. Runbook Delivery Plan

Required before M15:

- adapter disconnect
- authentication failure
- sequence gap storm
- database outage
- strategy failure
- unknown order
- portfolio mismatch
- kill switch
- bad deployment
- credential rotation
- exchange maintenance


# 89. Ownership Model

Assign owners for:

- architecture
- schemas
- database
- adapters
- replay
- strategies
- simulation
- risk
- portfolio
- execution
- security
- operations

A single person may own multiple areas initially.

Ownership means:

- review responsibility
- documentation responsibility
- incident responsibility
- roadmap responsibility


# 90. Project Board Structure

Suggested columns:

```text
Backlog
Design Ready
In Progress
Review
Validation
Operational Review
Done
Blocked
```

Suggested views:

- by milestone
- by package
- by risk level
- by owner
- by release


# 91. Milestone Metrics

Track:

- issues completed
- pull-request lead time
- CI duration
- test count
- coverage
- defect escape rate
- flaky tests
- replay determinism failures
- adapter disconnect recovery
- data-quality errors
- risk rule coverage
- reconciliation mismatches


# 92. Quality Gates by Risk Level

Low risk:

- one review
- unit tests
- standard CI

Normal risk:

- one domain review
- integration tests where applicable
- documentation

High risk:

- two reviewers
- failure-injection tests
- operational review
- rollback plan
- extended replay
- security review where relevant

Live risk:

- explicit approval
- shadow evidence
- runbook
- kill-switch drill
- limited rollout


# 93. Example Work Packet - Order State Machine

```text
Goal:
Implement canonical order state transitions.

Scope:
- src/pmrp/execution/state_machine.py
- tests/unit/execution/test_state_machine.py

Inputs:
- Order
- OrderStateTransition
- Fill
- ExchangeOrderAcknowledgement

Requirements:
- validate all transitions
- reject invalid terminal transitions
- support fill during cancellation
- enforce quantity invariants
- emit transition record
- no database code
- no adapter code

Acceptance:
- full transition table covered
- property tests for quantity invariants
- duplicate fill behavior tested
- Ruff, mypy, pytest pass
```


# 94. Example Work Packet - Replay Sorter

```text
Goal:
Implement deterministic canonical event sorting.

Scope:
- src/pmrp/replay/sorter.py
- tests/replay/test_sorter.py

Ordering:
1. occurred_at
2. exchange sequence
3. received_at
4. source partition
5. event_id

Requirements:
- stable ordering
- explicit handling of missing sequence
- no wall-clock access
- streaming-friendly design
- deterministic across runs

Acceptance:
- property tests
- randomized input order test
- duplicate timestamp fixture
- missing sequence fixture
```


# 95. Example Work Packet - Adapter Mapper

```text
Goal:
Map exchange order-book payloads to canonical events.

Scope:
- one adapter mapper module
- fixtures
- unit tests

Requirements:
- preserve raw identifiers
- exact Decimal conversion
- UTC-aware timestamps
- sequence mapping
- unknown enum handling
- data-quality findings
- no strategy logic

Acceptance:
- normal fixture
- malformed fixture
- unknown status fixture
- sequence gap fixture
- JSON round trip
```


# 96. Example Work Packet - Risk Rule

```text
Goal:
Implement market-data freshness risk rule.

Rule ID:
RISK-005

Inputs:
- order intent
- market-data timestamp
- configured maximum age
- evaluation time from Clock

Behavior:
- approve when age <= limit
- reject when age > limit
- reject when timestamp missing
- reject when clock state invalid

Outputs:
- stable reason codes
- observed age
- configured limit
- unit

Tests:
- exact boundary
- below boundary
- above boundary
- missing timestamp
- future timestamp
```


# 97. Example Work Packet - Portfolio Fill Application

```text
Goal:
Apply a fill to a position and accounting journal.

Requirements:
- Decimal only
- duplicate fill idempotency
- weighted average cost
- realized PnL on reduction
- position reversal
- fee posting
- balanced journal lines
- source lineage

Tests:
- first fill
- add to position
- partial close
- full close
- reversal
- duplicate
- fee
```


# 98. Example Work Packet - Paper Runtime

```text
Goal:
Wire live market data to strategy, risk, simulation, and portfolio.

Constraints:
- no live execution gateway
- paper account only
- all order intents risk checked
- structured session manifest
- graceful shutdown

Acceptance:
- fixture adapter end-to-end test
- one live-data adapter smoke test excluded from normal CI
- final portfolio snapshot
- metrics
- replay of archived session
```


# 99. Example Work Packet - Shadow Gateway

```text
Goal:
Record exact hypothetical live orders without sending them.

Requirements:
- accept ApprovedOrder
- create exchange request
- persist request
- emit shadow submission event
- never call adapter.place_order
- evaluate future market data
- report hypothetical outcome

Acceptance:
- static architecture test
- mock assertion that place_order is never called
- outcome evaluation test
- operator mode label
```


# 100. Dependency Freeze Points

Freeze interface changes at these points:

After M1:

- core schema names
- event envelope
- command envelope

After M4:

- adapter protocol
- capability model

After M8:

- replay manifest
- clock protocol
- event ordering policy

After M11:

- risk decision contract

After M12:

- portfolio and reconciliation contracts

Breaking changes after freeze require ADR and migration plan.


# 101. Schema Implementation Tracking

Track schema implementation status:

```text
Schema                      Code   Tests   JSON Schema   Registry   Example
---------------------------------------------------------------------------
Market                      [ ]    [ ]     [ ]           [ ]        [ ]
OrderBookSnapshot           [ ]    [ ]     [ ]           [ ]        [ ]
Trade                       [ ]    [ ]     [ ]           [ ]        [ ]
Signal                      [ ]    [ ]     [ ]           [ ]        [ ]
OrderIntent                 [ ]    [ ]     [ ]           [ ]        [ ]
Order                       [ ]    [ ]     [ ]           [ ]        [ ]
Fill                        [ ]    [ ]     [ ]           [ ]        [ ]
Position                    [ ]    [ ]     [ ]           [ ]        [ ]
RiskDecision                [ ]    [ ]     [ ]           [ ]        [ ]
ReplayManifest              [ ]    [ ]     [ ]           [ ]        [ ]
```


# 102. Adapter Implementation Tracking

```text
Capability                  Kalshi   Polymarket
------------------------------------------------
connect                     [ ]      [ ]
disconnect                  [ ]      [ ]
health                      [ ]      [ ]
list markets                [ ]      [ ]
market details              [ ]      [ ]
order-book snapshot         [ ]      [ ]
order-book updates          [ ]      [ ]
trades                      [ ]      [ ]
reconnect                   [ ]      [ ]
sequence recovery           [ ]      [ ]
place order                 [ ]      [ ]
cancel order                [ ]      [ ]
open orders                 [ ]      [ ]
positions                   [ ]      [ ]
balances                    [ ]      [ ]
fills                       [ ]      [ ]
reconciliation              [ ]      [ ]
```


# 103. Risk Implementation Tracking

```text
Rule ID     Description                         Code   Tests   Docs
-----------------------------------------------------------------
RISK-001    strategy enabled                    [ ]    [ ]     [ ]
RISK-002    exchange enabled                    [ ]    [ ]     [ ]
RISK-003    market enabled                      [ ]    [ ]     [ ]
RISK-004    market open                         [ ]    [ ]     [ ]
RISK-005    market data fresh                   [ ]    [ ]     [ ]
RISK-006    order price valid                   [ ]    [ ]     [ ]
RISK-007    order quantity limit                [ ]    [ ]     [ ]
RISK-008    order notional limit                [ ]    [ ]     [ ]
RISK-009    market position limit               [ ]    [ ]     [ ]
RISK-010    portfolio gross limit               [ ]    [ ]     [ ]
RISK-011    portfolio net limit                 [ ]    [ ]     [ ]
RISK-012    strategy capital limit              [ ]    [ ]     [ ]
RISK-013    exchange capital limit              [ ]    [ ]     [ ]
RISK-014    daily loss limit                    [ ]    [ ]     [ ]
RISK-015    open-order limit                    [ ]    [ ]     [ ]
RISK-016    duplicate-order guard               [ ]    [ ]     [ ]
RISK-017    balance available                   [ ]    [ ]     [ ]
RISK-018    reconciliation healthy              [ ]    [ ]     [ ]
RISK-019    kill switch clear                   [ ]    [ ]     [ ]
RISK-020    arbitrage leg risk                  [ ]    [ ]     [ ]
```


# 104. Replay Implementation Tracking

```text
Capability                  Status
----------------------------------
manifest validation         [ ]
dataset checksum            [ ]
event loading               [ ]
stable sorting              [ ]
replay clock                [ ]
speed control               [ ]
pause                       [ ]
resume                      [ ]
seek                        [ ]
filter                      [ ]
result checksum             [ ]
golden fixture              [ ]
fault injection             [ ]
```


# 105. Simulation Implementation Tracking

```text
Capability                  Status
----------------------------------
simulated exchange          [ ]
fixed latency               [ ]
volume-ahead queue          [ ]
partial fill                [ ]
cancel race                 [ ]
fee model                   [ ]
rejection model             [ ]
settlement model            [ ]
scenario harness            [ ]
result checksum             [ ]
```


# 106. Live Execution Implementation Tracking

```text
Capability                  Status
----------------------------------
approved order input        [ ]
idempotency                 [ ]
state machine               [ ]
submit                      [ ]
acknowledgement             [ ]
reject                      [ ]
partial fill                [ ]
fill                        [ ]
cancel                      [ ]
ambiguous state             [ ]
reconciliation              [ ]
kill switch                 [ ]
operator audit              [ ]
```


# 107. Minimum Viable Research Platform

The minimum viable research platform is complete when:

- schemas exist
- raw fixtures load
- normalization works
- canonical events persist
- replay works
- one strategy runs
- simulation works
- results are reproducible
- no live credentials are needed

This milestone is valuable even before live adapters are complete.


# 108. Minimum Viable Paper Platform

The minimum viable paper platform is complete when:

- one live market-data adapter works
- live data is archived
- one strategy runs
- risk evaluates intents
- simulator produces fills
- portfolio updates
- operator can stop runtime
- captured session replays


# 109. Minimum Viable Shadow Platform

The minimum viable shadow platform is complete when:

- exact hypothetical order requests are created
- no order is submitted
- decision latency is measured
- hypothetical outcomes are evaluated
- reconciliation health is visible
- shadow reports are generated


# 110. Minimum Viable Live Platform

The minimum viable live platform is complete when:

- one exchange order gateway works
- one strategy is approved
- risk limits are strict
- portfolio reconciles
- kill switch works
- operator controls work
- incident runbook exists
- minimal order is executed safely


# 111. Exit Criteria for Version 1.0

Version 1.0 should require:

- stable canonical schemas
- two market-data adapters
- at least one live execution adapter
- deterministic replay
- simulation
- strategy runtime
- risk engine
- portfolio accounting
- paper mode
- shadow mode
- limited live mode
- monitoring
- documentation
- migrations
- backup and restore
- security review


# 112. Non-Functional Acceptance Criteria

Correctness:

- no known accounting mismatch
- deterministic replay
- valid state transitions

Reliability:

- reconnect tested
- database failure handled
- graceful shutdown

Security:

- no secrets logged
- environment isolation
- least privilege

Observability:

- health
- metrics
- structured logs
- correlation IDs

Maintainability:

- typed interfaces
- package boundaries
- documentation
- test coverage


# 113. Milestone Completion Template

```text
Milestone:
Owner:
Date:
Status:

Deliverables:
- ...

Acceptance Criteria:
- ...

Tests:
- ...

Operational Review:
- ...

Known Limitations:
- ...

Deferred Work:
- ...

Decision:
APPROVED / APPROVED WITH FOLLOWUPS / BLOCKED
```


# 114. Suggested First Twenty Pull Requests

```text
01 repository skeleton
02 quality tooling
03 CI workflow
04 canonical base models
05 identifiers and enums
06 financial value objects
07 event and command envelopes
08 market schemas
09 market-data schemas
10 order and fill schemas
11 risk and portfolio schemas
12 clock implementations
13 event bus protocol
14 in-process event bus
15 storage engine and migration bootstrap
16 raw store
17 event store
18 adapter protocol
19 fixture adapter
20 normalization pipeline skeleton
```


# 115. Suggested Pull Requests Twenty-One Through Forty

```text
21 market catalog
22 Kalshi raw models
23 Kalshi REST market listing
24 Kalshi WebSocket connection
25 Kalshi order-book mapper
26 Kalshi trade mapper
27 Polymarket raw models
28 Polymarket market listing
29 Polymarket WebSocket connection
30 Polymarket order-book mapper
31 Polymarket trade mapper
32 replay manifest and loader
33 replay sorter
34 replay clock
35 replay engine
36 strategy protocol and context
37 strategy runtime
38 threshold strategy
39 simulation exchange
40 simulation fill model
```


# 116. Suggested Pull Requests Forty-One Through Sixty

```text
41 simulation scenarios
42 risk rule framework
43 risk basic rules
44 risk exposure rules
45 kill switches
46 portfolio position projection
47 fee and PnL accounting
48 reconciliation framework
49 paper runtime composition
50 paper end-to-end test
51 shadow gateway
52 shadow evaluator
53 operator health API
54 strategy control API
55 execution state machine
56 adapter order submission
57 adapter cancellation
58 execution reconciliation
59 live gating
60 limited live smoke workflow
```


# 117. Suggested Pull Requests Sixty-One Through Eighty

```text
61 matching candidate generation
62 entity extraction
63 embedding similarity
64 structured LLM proposal
65 deterministic relationship validation
66 relationship review workflow
67 arbitrage opportunity calculation
68 fee and slippage integration
69 arbitrage execution plans
70 arbitrage coordinator
71 arbitrage recovery
72 monitoring dashboards
73 alert rules
74 backup tooling
75 restore test
76 release automation
77 security scan hardening
78 capacity test
79 performance review
80 version 1.0 release preparation
```


# 118. Implementation Risks

Major risks:

- exchange API changes
- incomplete raw data
- incorrect normalization
- hidden float usage
- nondeterministic replay
- duplicated fills
- ambiguous order state
- weak reconciliation
- overfitting simulation
- market-matching false positives
- live mode enabled too early
- coding-agent scope drift
- excessive architecture complexity

Each risk should have:

- owner
- detection
- mitigation
- trigger
- contingency


# 119. Risk Mitigations

Exchange API changes:

- fixture contracts
- raw preservation
- parser versioning

Normalization errors:

- dead-letter records
- replayable raw data
- mapper tests

Duplicate fills:

- unique constraints
- idempotency tests

Ambiguous orders:

- client order IDs
- reconciliation
- trading gate

Simulation overconfidence:

- explicit assumptions
- shadow comparison
- conservative models

Matching false positives:

- deterministic validation
- human review
- live approval state


# 120. Stop Conditions

Pause implementation or rollout when:

- architecture contracts are unstable
- replay is nondeterministic
- accounting does not reconcile
- adapter sequence handling is unreliable
- live state is ambiguous
- secrets are exposed
- test suite is flaky
- database migration is unsafe
- risk limits can be bypassed
- shadow results materially disagree with assumptions

Stopping is a valid engineering decision.


# 121. Resumption Conditions

Resume after:

- root cause identified
- corrective change implemented
- regression test added
- affected data assessed
- operational state reconciled
- reviewer approval
- runbook updated if needed


# 122. Long-Term Extension Plan

Possible future additions:

- additional exchanges
- event-driven external data sources
- news and document extraction
- options-style prediction contracts
- reinforcement learning research
- portfolio optimization
- capital allocation service
- distributed replay
- GPU inference
- cross-asset hedging
- public SDK
- strategy marketplace

These are not prerequisites for the core platform.


# 123. Final Implementation Position

The platform should be built in the same order that confidence is earned.

First confidence in:

- code
- schemas
- data
- replay
- strategies
- simulation
- risk
- accounting
- operations

Only then confidence in live trading.

The implementation plan exists to prevent the project from becoming a large
collection of partially connected components.

Every milestone should produce:

- a working capability
- a testable contract
- a demonstrable result
- a safer foundation for the next milestone

The correct outcome is not the fastest possible path to submitting an order.

The correct outcome is the fastest defensible path to a trustworthy research
and trading platform.
