# Prediction Market Research Platform

## System Architecture Specification

- Document: `01_ARCHITECTURE.md`
- Version: 1.0
- Status: Governing architecture specification
- Language: Python 3.13
- Initial exchanges: Kalshi and Polymarket
- Primary audience: maintainers, contributors, quantitative researchers, and coding agents
- Character set: ASCII only

---

## Document Authority

This document defines the target architecture for the Prediction Market Research
Platform, abbreviated as PMRP.

The repository implementation should conform to this specification unless a later
Architecture Decision Record explicitly supersedes a decision in this document.

This is a platform specification, not a single-strategy bot design.

The intended system supports:

- historical market-data ingestion
- raw payload preservation
- canonical normalization
- deterministic replay
- multiple simultaneous strategies
- statistical research
- simulation
- paper trading
- shadow trading
- live trading
- cross-exchange market matching
- cross-exchange arbitrage
- risk management
- portfolio accounting
- monitoring
- auditability
- future exchange expansion

---

# 1. Executive Summary

PMRP is an exchange-agnostic, event-driven research and trading platform for
prediction markets.

The platform separates exchange connectivity, market-data normalization,
research, simulation, strategy logic, risk, execution, and accounting into
independent components with narrow interfaces.

The central architectural idea is that live trading, paper trading, shadow
trading, simulation, and historical replay should share the same canonical
events and nearly the same downstream runtime.

A strategy should not know whether an event came from:

- a live WebSocket
- a recorded historical file
- a database query
- a simulator
- a synthetic scenario test

A strategy should also not know how an exchange authenticates, how its REST
endpoint is shaped, or how its order identifiers are represented.

The platform therefore places a hard boundary between:

1. exchange-specific infrastructure
2. canonical domain infrastructure
3. research and strategy infrastructure
4. execution and risk infrastructure

The design prioritizes correctness, determinism, reproducibility, and
observability over premature microsecond optimization.

The initial implementation should be entirely in Python. Individual
infrastructure services may later be rewritten in Go only after profiling
proves a material bottleneck.


# 2. Vision

The end product is a reusable prediction-market research operating system.

It should allow a researcher to:

1. add an exchange adapter
2. collect and store data
3. define a canonical market relationship
4. write a strategy against stable interfaces
5. replay historical data deterministically
6. measure behavior in a simulator
7. run in paper mode
8. run in shadow mode against live data
9. enable live execution only after risk and operational validation

The platform should make the safe path the easiest path.

Research code should be easy to write.

Live trading should be difficult to enable accidentally.

All live side effects should be explicit, authenticated, logged, rate-limited,
risk-checked, and reconcilable.


# 3. Goals

## 3.1 Primary Goals

The platform shall:

- support multiple exchanges
- preserve raw exchange data
- normalize data into canonical schemas
- use an event-driven pipeline
- provide deterministic replay
- support multiple concurrent strategies
- isolate strategy failures
- support simulation with configurable market assumptions
- support paper, shadow, and live execution modes
- provide centralized pre-trade and post-trade risk controls
- provide portfolio accounting across exchanges
- support market equivalence and relationship matching
- provide full observability and audit trails
- support reproducible experiments
- support incremental open-source development

## 3.2 Secondary Goals

The platform should:

- be understandable by new contributors
- be usable from notebooks and command-line tools
- provide stable plugin interfaces
- permit optional distributed deployment
- support future message brokers
- support future compiled infrastructure services
- support model versioning and experiment tracking
- support structured exports for analysis

## 3.3 Success Criteria

The architecture is successful when:

- a strategy runs unchanged in replay, simulation, paper, shadow, and live modes
- the same recorded event stream produces identical strategy outputs
- all exchange-specific code is confined to adapters and mapping modules
- every order transition is auditable
- portfolio state reconciles to exchange state
- risk limits can halt order flow without stopping market-data collection
- new exchanges can be added without modifying strategy code


# 4. Non-Goals

The first production version is not intended to:

- compete in sub-millisecond high-frequency trading
- implement a general-purpose exchange matching engine
- support every prediction-market venue immediately
- guarantee profitable strategies
- replace formal legal, tax, or compliance advice
- perform autonomous unrestricted capital allocation
- hide complexity behind a monolithic framework
- use machine learning where deterministic logic is sufficient
- depend on a single cloud provider
- require Kubernetes for local development
- require Kafka for the initial deployment
- use a microservice architecture by default

The initial system is a modular monolith with explicit boundaries.

Distribution is an evolution path, not a starting requirement.


# 5. Architectural Principles

## 5.1 Exchange Agnosticism

Strategies and research modules operate on canonical domain objects.

They do not import exchange clients or exchange payload models.

## 5.2 Event-Driven Core

State changes are represented as immutable events.

Commands request side effects.

Events report facts that occurred.

## 5.3 Deterministic Replay

Historical replay is a first-class runtime, not a secondary testing utility.

All time-dependent components use an injected clock.

## 5.4 Raw Data Preservation

Raw exchange payloads are stored before normalization whenever operationally
possible.

Normalization bugs must be repairable without reacquiring source data.

## 5.5 Explicit Side Effects

Network calls, order submissions, cancellations, file writes, and database
writes occur only in infrastructure components.

Domain logic remains side-effect controlled.

## 5.6 Dependency Inversion

High-level policy depends on interfaces.

Infrastructure implements those interfaces.

## 5.7 Fail Closed for Trading

If risk state, authentication state, market state, or accounting state is
uncertain, new live orders are blocked.

Market-data ingestion may continue.

## 5.8 Observability by Default

Every component emits structured logs, metrics, and health state.

## 5.9 Idempotency

Repeated delivery of a command or event must not create duplicate business
effects.

## 5.10 Versioned Contracts

Canonical events, storage schemas, and public interfaces are versioned.

## 5.11 Progressive Operational Modes

The intended progression is:

```text
research
  |
historical replay
  |
simulation
  |
paper trading
  |
shadow trading
  |
limited live trading
  |
scaled live trading
```

## 5.12 Simple Before Distributed

Use in-process interfaces first.

Add external brokers or services only when scaling, isolation, or operational
needs justify them.


# 6. System Context

## 6.1 External Actors

The system interacts with:

- prediction-market exchanges
- exchange authentication systems
- operators
- researchers
- strategy developers
- monitoring systems
- relational databases
- object storage
- optional message brokers
- optional experiment-tracking systems

## 6.2 Context Diagram

```text
+-------------------+          +-------------------+
| Kalshi            |          | Polymarket        |
| REST + WebSocket  |          | REST + WebSocket  |
+---------+---------+          +---------+---------+
          |                              |
          +---------------+--------------+
                          |
                 +--------v--------+
                 | Exchange Layer  |
                 +--------+--------+
                          |
                 +--------v--------+
                 | Canonical Core  |
                 +---+----+----+---+
                     |    |    |
          +----------+    |    +-----------+
          |               |                |
+---------v--------+ +----v-----+ +--------v---------+
| Storage          | | Replay   | | Strategy Runtime |
+---------+--------+ +----+-----+ +--------+---------+
          |               |                |
          +---------------+----------------+
                          |
                 +--------v--------+
                 | Risk + Execution|
                 +--------+--------+
                          |
                 +--------v--------+
                 | Portfolio       |
                 +--------+--------+
                          |
                 +--------v--------+
                 | Monitoring      |
                 +-----------------+
```

## 6.3 Trust Boundaries

External exchange data is untrusted.

Configuration is trusted only after validation.

Secrets are trusted but must never be logged.

Strategy outputs are untrusted until risk validation.

Exchange acknowledgements are authoritative for exchange-side state but must
still be reconciled against fills, balances, and open-order snapshots.


# 7. High-Level Logical Architecture

```text
                        CONTROL PLANE

      Configuration  Strategy Registry  Operator Commands
             |               |                 |
             +---------------+-----------------+
                             |
                             v

                         DATA PLANE

+-------------+     +----------------+     +------------------+
| Exchange    | --> | Adapter        | --> | Raw Event Store  |
| APIs        |     | Connectors     |     +------------------+
+-------------+     +-------+--------+
                            |
                            v
                   +------------------+
                   | Normalization    |
                   +--------+---------+
                            |
                            v
                   +------------------+
                   | Canonical Bus    |
                   +--+---+---+---+---+
                      |   |   |   |
          +-----------+   |   |   +----------------+
          |               |   |                    |
          v               v   v                    v
+----------------+ +----------+----------+ +----------------+
| Normalized     | | Strategy Runtime    | | Monitoring     |
| Event Store    | | and Models          | | and Audit      |
+----------------+ +----------+----------+ +----------------+
                              |
                              v
                     +------------------+
                     | Signal Bus       |
                     +--------+---------+
                              |
                              v
                     +------------------+
                     | Risk Engine      |
                     +--------+---------+
                              |
                              v
                     +------------------+
                     | Execution Engine |
                     +--------+---------+
                              |
                              v
                     +------------------+
                     | Exchange Adapter |
                     +------------------+
```

The control plane changes what the platform should do.

The data plane processes market data, decisions, orders, fills, and accounting.


# 8. Deployment Architecture

## 8.1 Initial Deployment

The initial deployment is a modular monolith.

Recommended processes:

```text
process: collector
  - exchange market-data adapters
  - normalization
  - raw storage
  - normalized storage

process: trader
  - canonical subscriptions
  - strategy runtime
  - risk
  - execution
  - portfolio

process: researcher
  - replay
  - simulation
  - experiment runner

process: operator-api
  - health
  - configuration inspection
  - trading controls
```

These may run as a single process in development.

They should be separable without redesign.

## 8.2 Local Development

```text
Docker Compose
  |
  +-- PostgreSQL
  +-- optional Redis
  +-- collector
  +-- trader
  +-- operator API
  +-- metrics exporter
```

## 8.3 Future Distributed Deployment

```text
Exchange Gateways
        |
Canonical Message Broker
        |
+-------+--------+--------+
|                |        |
Strategy Pods  Storage   Monitoring
|                |
Risk Service     |
|                |
Execution Gateway
```

A distributed architecture must preserve:

- event ordering guarantees
- idempotency
- schema versioning
- correlation identifiers
- replay compatibility
- auditability


# 9. Repository Structure

```text
prediction-market-platform/
|
+-- pyproject.toml
+-- uv.lock
+-- .python-version
+-- README.md
+-- LICENSE
+-- Makefile
+-- docker-compose.yml
+-- alembic.ini
+-- .env.example
+-- .pre-commit-config.yaml
|
+-- docs/
|   +-- 01_ARCHITECTURE.md
|   +-- 02_ENGINEERING.md
|   +-- 03_SCHEMAS.md
|   +-- 04_IMPLEMENTATION.md
|   +-- adr/
|
+-- src/
|   +-- pmrp/
|       +-- app/
|       +-- domain/
|       +-- events/
|       +-- commands/
|       +-- adapters/
|       |   +-- base/
|       |   +-- kalshi/
|       |   +-- polymarket/
|       +-- normalization/
|       +-- ingestion/
|       +-- bus/
|       +-- storage/
|       +-- replay/
|       +-- clock/
|       +-- strategies/
|       +-- models/
|       +-- matching/
|       +-- simulation/
|       +-- execution/
|       +-- risk/
|       +-- portfolio/
|       +-- analytics/
|       +-- monitoring/
|       +-- config/
|       +-- security/
|       +-- operator_api/
|       +-- cli/
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
+-- data/
    +-- raw/
    +-- normalized/
    +-- snapshots/
    +-- exports/
```

## 9.1 Dependency Rules

Allowed dependency direction:

```text
infrastructure --> application --> domain
```

Domain must not depend on:

- HTTP clients
- WebSocket libraries
- SQLAlchemy
- cloud SDKs
- exchange SDKs
- CLI frameworks

Strategies may depend on:

- domain models
- canonical events
- strategy interfaces
- approved analytics utilities

Strategies may not depend on:

- concrete exchange adapters
- database sessions
- secret managers
- raw HTTP clients


# 10. Domain Model

## 10.1 Core Entities

The primary domain entities are:

- Exchange
- Event
- Market
- Contract
- Outcome
- OrderBook
- Quote
- Trade
- Order
- Fill
- Position
- CashBalance
- Portfolio
- Signal
- StrategyInstance
- RiskLimit
- RiskDecision
- MarketRelationship
- Experiment
- ReplaySession

## 10.2 Aggregate Boundaries

### Market Aggregate

Owns:

- market identity
- outcomes
- lifecycle
- resolution status
- canonical relationships

### Order Aggregate

Owns:

- order state
- requested quantity
- remaining quantity
- fills
- cancellation state
- exchange identifiers

### Portfolio Aggregate

Owns:

- cash balances
- positions
- realized PnL
- unrealized PnL
- exposure
- reconciliation status

### Strategy Aggregate

Owns:

- strategy instance identity
- configuration
- lifecycle state
- model version
- emitted signal lineage

## 10.3 Value Objects

Use immutable value objects for:

- Money
- Price
- Probability
- Quantity
- BasisPoints
- Timestamp
- ExchangeMarketId
- CanonicalMarketId
- OrderId
- StrategyId
- CorrelationId

Financial values use `Decimal`.

Binary probability values are constrained to the inclusive range zero through
one.


# 11. Canonical Identity Model

## 11.1 Identifier Types

Every object must have an internal canonical identifier.

External identifiers remain attached as metadata.

Example:

```text
canonical_market_id: pmkt_01J...
exchange: kalshi
exchange_market_id: FED-25DEC-T4.50
```

## 11.2 Identifier Rules

Identifiers shall be:

- globally unique
- immutable
- opaque
- non-semantic where practical
- stable across replays

Recommended format:

- UUIDv7
- ULID
- prefixed ULID

## 11.3 Correlation and Causation

Every event includes:

- event_id
- correlation_id
- causation_id
- trace_id
- producer
- schema_version

Example causal chain:

```text
market_data_event
    |
signal_event
    |
risk_decision_event
    |
order_submission_event
    |
order_acknowledged_event
    |
fill_event
    |
position_changed_event
```


# 12. Canonical Event Model

## 12.1 Event Envelope

All canonical events share a common envelope.

```python
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID
    event_type: str
    schema_version: int
    occurred_at: datetime
    received_at: datetime
    published_at: datetime
    producer: str
    exchange: str | None
    market_id: str | None
    correlation_id: UUID
    causation_id: UUID | None
    trace_id: str | None
    replay_session_id: UUID | None
    attributes: Mapping[str, Any]
```

## 12.2 Event Categories

Market-data events:

- MarketDiscovered
- MarketUpdated
- MarketStatusChanged
- OrderBookSnapshot
- OrderBookDelta
- QuoteUpdated
- TradeObserved
- SettlementObserved

Execution events:

- OrderCreated
- OrderSubmitted
- OrderAccepted
- OrderRejected
- OrderPartiallyFilled
- OrderFilled
- OrderCancelRequested
- OrderCancelled
- OrderExpired
- OrderLost
- ExecutionReconciled

Strategy events:

- StrategyStarted
- StrategyStopped
- SignalGenerated
- SignalWithdrawn
- ModelPredictionGenerated
- StrategyHealthChanged

Risk events:

- RiskCheckRequested
- RiskApproved
- RiskRejected
- RiskLimitBreached
- KillSwitchActivated
- KillSwitchReleased

Portfolio events:

- PositionOpened
- PositionChanged
- PositionClosed
- CashBalanceChanged
- PnlUpdated
- PortfolioReconciled
- PortfolioMismatchDetected

System events:

- AdapterConnected
- AdapterDisconnected
- SequenceGapDetected
- DataQualityIssueDetected
- ServiceHealthChanged
- ConfigurationLoaded
- ConfigurationRejected

## 12.3 Event Immutability

Published events are immutable.

Corrections are represented by new events.

A correction event references the event it supersedes.

## 12.4 Event Ordering

Global total ordering is not assumed.

Ordering is guaranteed within a partition.

Recommended partition keys:

- exchange + market
- strategy instance
- order
- portfolio account

Replay merges partitions according to stored timestamps and deterministic
tie-breaking rules.


# 13. Command Model

Commands request an action.

Commands may be rejected.

Commands are not facts.

Primary commands:

- ConnectAdapter
- DisconnectAdapter
- SubscribeMarket
- UnsubscribeMarket
- PlaceOrder
- CancelOrder
- ReplaceOrder
- StartStrategy
- StopStrategy
- ActivateKillSwitch
- ReleaseKillSwitch
- StartReplay
- PauseReplay
- ResumeReplay
- SeekReplay
- ReconcileAccount

Command envelope fields:

- command_id
- command_type
- issued_at
- issuer
- correlation_id
- causation_id
- idempotency_key
- payload
- deadline
- priority


# 14. Exchange Adapter Architecture

## 14.1 Adapter Responsibilities

An exchange adapter owns:

- authentication
- REST transport
- WebSocket transport
- reconnect logic
- heartbeat logic
- exchange rate limits
- exchange error parsing
- payload parsing
- exchange identifier mapping
- order command translation
- exchange-side reconciliation calls

An exchange adapter does not own:

- strategy logic
- fair-value calculation
- portfolio policy
- global risk policy
- cross-exchange market equivalence
- canonical accounting

## 14.2 Adapter Interface

```python
from collections.abc import AsyncIterator
from typing import Protocol


class ExchangeAdapter(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def health(self) -> "AdapterHealth": ...

    async def list_markets(
        self,
        request: "MarketListRequest",
    ) -> list["RawMarket"]: ...

    async def subscribe_market_data(
        self,
        subscriptions: list["MarketSubscription"],
    ) -> AsyncIterator["RawExchangeEvent"]: ...

    async def place_order(
        self,
        request: "ExchangeOrderRequest",
    ) -> "ExchangeOrderAck": ...

    async def cancel_order(
        self,
        request: "ExchangeCancelRequest",
    ) -> "ExchangeCancelAck": ...

    async def get_open_orders(self) -> list["RawOpenOrder"]: ...
    async def get_positions(self) -> list["RawPosition"]: ...
    async def get_balances(self) -> list["RawBalance"]: ...
```

## 14.3 Capability Model

Not every exchange supports identical features.

Each adapter publishes capabilities:

- order types
- time-in-force values
- batch operations
- streaming order updates
- streaming market data
- historical endpoints
- self-trade controls
- client order identifiers
- replace-order support
- post-only support

The execution engine checks capabilities before creating exchange requests.

## 14.4 Reconnect Behavior

On disconnect:

1. emit AdapterDisconnected
2. stop accepting new live order commands for that adapter
3. preserve current local state as uncertain
4. reconnect with exponential backoff and jitter
5. reauthenticate
6. resubscribe
7. fetch open orders
8. fetch positions
9. fetch balances
10. reconcile
11. emit AdapterConnected
12. release the adapter trading gate only after reconciliation

## 14.5 Sequence Gap Handling

If an exchange provides sequence numbers:

```text
expected = previous + 1

if received == expected:
    apply delta

if received <= previous:
    classify as duplicate or stale

if received > expected:
    emit SequenceGapDetected
    invalidate local book
    request fresh snapshot
    rebuild
```

No strategy receives order-book deltas while the book is invalid.


# 15. Kalshi Adapter Boundary

The Kalshi adapter should be isolated under:

```text
adapters/kalshi/
  authentication.py
  client.py
  websocket.py
  rest.py
  mapper.py
  models.py
  rate_limits.py
  errors.py
  capabilities.py
  fixtures/
```

Kalshi-specific concepts remain inside this package.

The mapper converts Kalshi payloads into canonical events.

The adapter must preserve:

- original ticker or market identifiers
- original timestamps
- raw prices
- raw quantities
- sequence values
- order status strings
- rejection payloads

No canonical module should import from `adapters.kalshi`.


# 16. Polymarket Adapter Boundary

The Polymarket adapter should be isolated under:

```text
adapters/polymarket/
  authentication.py
  clob_client.py
  websocket.py
  rest.py
  mapper.py
  models.py
  chain_metadata.py
  rate_limits.py
  errors.py
  capabilities.py
  fixtures/
```

The adapter may need to model both centralized order-book APIs and relevant
on-chain metadata.

Exchange-specific signing, token handling, chain identifiers, and API response
structures must not leak into canonical strategy interfaces.

The adapter must clearly distinguish:

- exchange event time
- local receive time
- blockchain time, if applicable
- finality assumptions, if applicable


# 17. Normalization Layer

## 17.1 Responsibilities

The normalization layer converts raw exchange payloads into canonical domain
objects and events.

Responsibilities:

- schema validation
- field mapping
- timestamp conversion
- side normalization
- price normalization
- quantity normalization
- market lifecycle mapping
- identifier mapping
- duplicate detection
- data-quality annotation
- schema-version assignment

## 17.2 Raw Before Normalized

Preferred flow:

```text
receive payload
    |
persist raw envelope
    |
validate
    |
normalize
    |
persist canonical event
    |
publish canonical event
```

If raw persistence is temporarily unavailable, the system may buffer according
to an explicit durability policy.

## 17.3 Normalization Errors

Normalization errors do not crash the adapter loop.

They produce:

- structured error logs
- DataQualityIssueDetected events
- dead-letter records
- metrics
- optional operator alerts

## 17.4 Canonical Side Mapping

Canonical order sides should describe the economic action unambiguously.

Recommended:

- BUY
- SELL

Outcome or contract identity is represented separately.

Avoid encoding exchange-specific "yes bid" or "no ask" semantics in generic
strategy interfaces.


# 18. Market Data Ingestion Pipeline

## 18.1 Pipeline

```text
WebSocket frame
    |
RawExchangeEvent
    |
RawEventWriter
    |
Normalizer
    |
CanonicalMarketEvent
    |
CanonicalEventWriter
    |
EventBus
    |
Consumers
```

## 18.2 Consumers

Primary consumers:

- order-book state builder
- strategy runtime
- replay recorder
- market catalog
- monitoring
- analytics
- market matcher

## 18.3 Backpressure

The ingestion pipeline must define bounded queues.

If a consumer is slow:

- noncritical analytics may drop or sample
- durable storage must not silently drop
- strategy feeds must expose lag
- order-book reconstruction must preserve ordering
- the system may pause subscriptions if supported
- the system may rotate to disk buffers

## 18.4 Data Quality Flags

Canonical events may include quality flags:

- delayed
- duplicate
- out_of_order
- inferred
- snapshot_recovery
- incomplete
- stale
- corrected
- simulated


# 19. Event Bus Architecture

## 19.1 Initial Bus

Use an in-process asynchronous event bus for the initial modular monolith.

Required features:

- typed subscriptions
- bounded queues
- partition-aware ordering
- backpressure metrics
- consumer isolation
- graceful shutdown
- deterministic test mode

## 19.2 Interface

```python
from collections.abc import AsyncIterator
from typing import Protocol, TypeVar

T = TypeVar("T")


class EventBus(Protocol):
    async def publish(self, event: object) -> None: ...

    def subscribe(
        self,
        event_type: type[T],
        *,
        consumer_name: str,
        partition_key: str | None = None,
    ) -> AsyncIterator[T]: ...

    async def close(self) -> None: ...
```

## 19.3 Delivery Semantics

Initial target:

- at-least-once delivery to durable consumers
- at-most-once delivery may be acceptable for noncritical telemetry
- idempotent consumers
- deterministic in-process ordering

## 19.4 Future Broker Migration

A future broker may be:

- Kafka
- Redpanda
- NATS JetStream
- Redis Streams

The migration must not alter canonical event schemas.

## 19.5 Dead-Letter Handling

Failed durable consumption writes:

- event envelope
- consumer name
- exception type
- exception message
- retry count
- first failure time
- latest failure time
- stack trace reference
- replayability metadata


# 20. Storage Architecture

## 20.1 Storage Tiers

The platform uses three logical storage tiers.

### Raw Store

Stores original exchange payloads.

### Canonical Event Store

Stores normalized immutable events.

### Operational State Store

Stores current projections:

- markets
- order books
- open orders
- positions
- balances
- risk state
- strategy state

## 20.2 Recommended Initial Technologies

- PostgreSQL for operational and event metadata
- partitioned PostgreSQL tables for moderate event volume
- object storage or compressed files for large raw archives
- Parquet for analytical exports

## 20.3 Raw Record Fields

Raw records include:

- raw_record_id
- exchange
- channel
- endpoint
- message_type
- received_at
- exchange_timestamp
- sequence
- payload_bytes
- payload_hash
- compression
- parser_version
- connection_id

## 20.4 Canonical Event Fields

Canonical event records include:

- event_id
- event_type
- schema_version
- occurred_at
- received_at
- published_at
- exchange
- market_id
- correlation_id
- causation_id
- replay_session_id
- payload_json
- payload_hash
- quality_flags

## 20.5 Partitioning

Recommended partitioning axes:

- month by occurred_at
- exchange
- event category

Partitioning should be selected from measured volume.

## 20.6 Retention

Retention policies differ by data class.

Raw data:

- long retention
- compressed
- immutable

Canonical events:

- long retention
- queryable
- versioned

Operational logs:

- shorter hot retention
- archived according to policy

Secrets:

- never persisted in event payloads


# 21. Database Consistency Model

Use database transactions to atomically persist related operational state.

Examples:

- fill + order state + position projection
- risk decision + order approval record
- portfolio reconciliation result + mismatch records

The event store is append-only.

Operational projections may be updated.

Projection rebuilds should be possible from canonical events where practical.

Optimistic concurrency should protect aggregates.

Recommended version column:

```text
aggregate_version bigint not null
```

Updates use:

```text
where aggregate_id = ? and aggregate_version = expected
```


# 22. Replay Architecture

## 22.1 Goals

Replay shall provide:

- deterministic ordering
- configurable speed
- pause and resume
- bounded time windows
- event filtering
- repeatability
- session metadata
- result comparison
- synthetic event injection
- fault injection

## 22.2 Replay Input Sources

Supported sources:

- canonical event database
- Parquet files
- JSON Lines archives
- scenario fixtures
- synthetic generators

## 22.3 Replay Session

A replay session records:

- replay_session_id
- dataset identifier
- dataset checksum
- start time
- end time
- speed
- seed
- strategy versions
- model versions
- configuration hash
- code commit
- result checksum

## 22.4 Deterministic Ordering

Tie-break order:

1. occurred_at
2. exchange sequence, if available
3. received_at
4. stable source partition
5. event_id

The tie-break policy is versioned.

## 22.5 Replay Flow

```text
Dataset Loader
      |
Event Sorter
      |
Replay Clock
      |
Canonical Event Bus
      |
Same Consumers Used in Live Mode
```

## 22.6 Replay Isolation

Replay must not:

- use live exchange credentials
- submit live orders
- mutate live operational tables
- read wall-clock time directly
- share live strategy state

## 22.7 Determinism Test

Given:

- same dataset checksum
- same strategy version
- same model version
- same configuration hash
- same random seed
- same replay engine version

The platform must produce identical:

- signals
- simulated orders
- fills
- positions
- PnL
- result checksums


# 23. Clock Abstraction

## 23.1 Rule

Direct calls to system time are prohibited in domain, strategy, simulation, and
risk code.

## 23.2 Interface

```python
from datetime import datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...
    async def sleep(self, duration: timedelta) -> None: ...
```

## 23.3 Implementations

- SystemClock
- ReplayClock
- SimulatedClock
- FrozenClock
- AdvancingTestClock

## 23.4 Timers

Timer scheduling must use the injected clock.

Examples:

- order timeout
- quote refresh
- stale market detection
- strategy cadence
- risk cooldown
- reconciliation interval


# 24. Strategy Runtime

## 24.1 Strategy Contract

```python
from typing import Protocol


class Strategy(Protocol):
    async def initialize(self, context: "StrategyContext") -> None: ...
    async def on_event(self, event: object) -> None: ...
    async def shutdown(self, reason: str) -> None: ...
```

## 24.2 Strategy Context

The context provides approved services:

- clock
- market-data views
- signal publisher
- order-intent publisher
- feature store
- metrics
- logger
- read-only portfolio view
- read-only risk view

The context does not provide raw exchange clients.

## 24.3 Lifecycle

```text
CREATED
   |
INITIALIZING
   |
RUNNING
   |
DRAINING
   |
STOPPED

Failure path:

RUNNING --> DEGRADED --> STOPPED
```

## 24.4 Isolation

Each strategy instance receives:

- separate configuration
- separate state namespace
- separate metrics labels
- separate error budget
- separate order tags
- separate capital allocation

## 24.5 Concurrency

Strategies may run concurrently.

Events within a strategy partition must be processed sequentially unless the
strategy explicitly declares safe parallelism.

## 24.6 Strategy Failure

A strategy exception:

1. is logged
2. increments failure metrics
3. marks the instance degraded
4. blocks new order intents from that instance
5. optionally cancels its open orders
6. does not terminate unrelated strategies


# 25. Signal and Order Intent Model

A signal expresses a research or trading opinion.

An order intent expresses a desired market action.

Signals and order intents are distinct.

## 25.1 Signal Example

```text
signal_id
strategy_id
market_id
signal_type
direction
strength
fair_probability
confidence
valid_from
valid_until
model_version
feature_snapshot_id
reason_code
```

## 25.2 Order Intent Example

```text
intent_id
strategy_id
market_id
side
quantity
limit_price
time_in_force
post_only
reduce_only
urgency
expires_at
signal_ids
```

The risk engine consumes order intents.

The execution engine consumes only approved order requests.


# 26. Market-Making Architecture

## 26.1 Components

A market-making strategy typically contains:

- fair-value estimator
- spread model
- inventory skew model
- volatility estimator
- liquidity estimator
- quote generator
- quote manager
- adverse-selection detector

## 26.2 Quote Flow

```text
Market Data
    |
Feature Calculation
    |
Fair Probability
    |
Inventory Adjustment
    |
Risk Budget
    |
Bid and Ask Generation
    |
Order Intents
```

## 26.3 Quote Manager

The quote manager decides whether to:

- create
- cancel
- replace
- leave unchanged

It should minimize unnecessary churn.

## 26.4 Inventory Skew

Inventory changes quoting behavior.

Example:

```text
long inventory:
  lower bid aggressiveness
  increase ask aggressiveness

short inventory:
  increase bid aggressiveness
  lower ask aggressiveness
```

All formulas and parameters must be versioned.


# 27. Statistical Model Architecture

Statistical models are separate from strategy orchestration.

A model consumes features and returns predictions.

```python
from typing import Protocol


class PredictiveModel(Protocol):
    @property
    def version(self) -> str: ...

    def predict(
        self,
        features: "FeatureVector",
    ) -> "ModelPrediction": ...
```

Model metadata includes:

- model name
- model version
- training dataset
- training code commit
- feature schema version
- calibration method
- evaluation metrics
- creation time
- approval status

Models should not submit orders.

Strategies translate predictions into signals and order intents.


# 28. Feature Architecture

## 28.1 Feature Categories

- market microstructure
- price momentum
- spread
- depth
- order imbalance
- trade intensity
- volatility
- time to resolution
- cross-exchange divergence
- external reference data
- inventory
- liquidity
- market lifecycle

## 28.2 Feature Store

The initial feature store may be in-process plus persisted snapshots.

Required properties:

- feature schema version
- timestamp
- source event references
- deterministic calculation
- no future leakage in replay
- reproducible windowing

## 28.3 Leakage Prevention

Replay features may use only data available at the replay clock time.

Training pipelines must define label horizons and embargo periods explicitly.


# 29. Market Matching and Canonical Event Graph

## 29.1 Purpose

Prediction-market exchanges may list economically related contracts with
different wording, settlement rules, dates, and outcome structures.

The matching subsystem identifies possible relationships.

## 29.2 Relationship Types

- equivalent
- complement
- subset
- superset
- mutually_exclusive
- conditionally_equivalent
- correlated
- unrelated
- unresolved

## 29.3 Matching Pipeline

```text
Exchange Market Metadata
        |
Deterministic Filters
        |
Text and Entity Extraction
        |
Embedding Similarity
        |
LLM Structured Analysis
        |
Rule Validation
        |
Human Review, if required
        |
Canonical Relationship Record
```

## 29.4 LLM Boundary

An LLM may propose:

- entities
- dates
- thresholds
- logical conditions
- candidate relationships

An LLM may not alone authorize live arbitrage.

Tradable equivalence requires deterministic validation and confidence policy.

## 29.5 Canonical Event Graph

Nodes represent markets or outcomes.

Edges represent relationships.

Edge metadata:

- relationship type
- confidence
- valid_from
- valid_until
- evidence
- validator version
- review status
- settlement-rule comparison


# 30. Cross-Exchange Arbitrage Architecture

## 30.1 Inputs

- matched market relationships
- normalized order books
- fee schedules
- expected slippage
- latency assumptions
- capital constraints
- settlement constraints
- withdrawal and funding constraints

## 30.2 Opportunity Calculation

A candidate opportunity must account for:

- executable prices
- available depth
- fees
- rebates
- settlement asymmetry
- fill risk
- transfer constraints
- inventory cost
- probability of partial execution

## 30.3 Execution Policy

Cross-exchange arbitrage requires an execution plan.

Possible policies:

- simultaneous submission
- primary leg then hedge
- passive leg then aggressive hedge
- inventory-backed execution

## 30.4 Leg Risk

The system tracks:

- submitted legs
- accepted legs
- filled legs
- remaining hedge quantity
- maximum tolerated unhedged exposure
- hedge timeout

If a leg fails, recovery actions may include:

- cancel remaining passive orders
- cross the spread to hedge
- reduce position elsewhere
- activate strategy kill switch


# 31. Simulation Architecture

## 31.1 Purpose

Simulation estimates how order intents would behave under configurable market
assumptions.

## 31.2 Simulation Components

- simulated exchange
- order book
- queue model
- latency model
- fill model
- fee model
- rejection model
- disconnect model
- settlement model

## 31.3 Queue Models

Supported levels:

1. immediate-touch model
2. price-time approximation
3. volume-ahead model
4. probabilistic queue model
5. calibrated exchange-specific model

## 31.4 Latency Model

Latency components:

- strategy compute
- internal routing
- network outbound
- exchange processing
- network inbound
- event publication

Latency may be:

- fixed
- sampled from distribution
- replayed from measurements

## 31.5 Fill Logic

Simulation must support:

- full fills
- partial fills
- no fills
- maker fills
- taker fills
- price improvement
- slippage
- stale-order fills
- cancellation races

## 31.6 Scenario Testing

Scenarios include:

- rapid spread widening
- crossed books
- missing deltas
- delayed trades
- disconnect during open orders
- partial fill before cancel
- market halt
- resolution update
- fee change
- duplicate acknowledgement


# 32. Execution Modes

## 32.1 Research Mode

No order intents leave the experiment process.

## 32.2 Simulation Mode

Order intents go to a simulated exchange.

## 32.3 Paper Mode

Live market data drives a simulated account.

## 32.4 Shadow Mode

The system performs full live decisioning but does not submit orders.

It records hypothetical requests and compares them with subsequent market data.

## 32.5 Live Mode

Approved orders are sent to exchanges.

Live mode requires:

- explicit configuration
- valid credentials
- risk approval
- operator authorization
- reconciliation health
- kill-switch availability
- environment labeling


# 33. Execution Engine

## 33.1 Responsibilities

The execution engine owns:

- approved order request intake
- exchange routing
- idempotency
- order state machine
- retry policy
- timeout policy
- cancellation
- replacement
- reconciliation
- execution metrics

## 33.2 Execution Interface

```python
from typing import Protocol


class ExecutionGateway(Protocol):
    async def submit(
        self,
        order: "ApprovedOrder",
    ) -> "OrderHandle": ...

    async def cancel(
        self,
        order_id: str,
    ) -> None: ...

    async def replace(
        self,
        order_id: str,
        replacement: "ApprovedOrder",
    ) -> "OrderHandle": ...
```

## 33.3 Idempotency

Every order submission carries an idempotency key.

Repeated attempts with the same key must not create multiple logical orders.

## 33.4 Retry Rules

Safe to retry:

- connection timeout before acknowledgement, subject to idempotency
- temporary rate-limit response
- transient server error

Not automatically safe to retry:

- ambiguous submission without idempotency support
- validation rejection
- insufficient balance
- market closed
- duplicate client identifier

Ambiguous state triggers reconciliation.


# 34. Order State Machine

## 34.1 States

```text
CREATED
   |
RISK_PENDING
   |
APPROVED
   |
SUBMITTING
   |
SUBMITTED
   |
ACCEPTED
   |
+-------------------+
|                   |
PARTIALLY_FILLED    |
|                   |
+--------+----------+
         |
       FILLED
```

Terminal and alternate states:

- REJECTED
- CANCELLED
- EXPIRED
- LOST
- FAILED
- SUPERSEDED

## 34.2 Cancellation Path

```text
ACCEPTED
   |
CANCEL_REQUESTED
   |
CANCELLING
   |
CANCELLED
```

A fill may arrive during cancellation.

The state machine must permit:

```text
CANCELLING --> PARTIALLY_FILLED
CANCELLING --> FILLED
```

## 34.3 Invariants

- filled quantity never decreases
- remaining quantity is never negative
- terminal orders do not accept new state transitions except correction events
- each fill identifier is applied once
- total fill quantity does not exceed order quantity unless explicitly flagged
- exchange order ID mapping is immutable after confirmed


# 35. Pre-Trade Risk Architecture

## 35.1 Placement

```text
Strategy
   |
Order Intent
   |
Pre-Trade Risk
   |
Approved Order
   |
Execution Engine
```

## 35.2 Checks

Initial checks:

- strategy enabled
- exchange enabled
- market enabled
- market open
- data freshness
- order size
- price bounds
- notional
- position limit
- portfolio exposure
- concentration
- daily loss
- open-order count
- duplicate intent
- available balance
- rate-limit budget
- kill-switch state
- reconciliation health

## 35.3 Risk Decision

Each decision records:

- decision ID
- intent ID
- rule versions
- approved or rejected
- rejection reasons
- calculated exposures
- limits
- timestamp
- configuration hash

## 35.4 Fail-Closed Rule

If required risk data is stale or unavailable, live order approval is denied.


# 36. Post-Trade Risk Architecture

Post-trade risk monitors:

- realized PnL
- unrealized PnL
- gross exposure
- net exposure
- market concentration
- exchange concentration
- strategy concentration
- unresolved settlement exposure
- unhedged arbitrage legs
- balance drift
- reconciliation mismatches
- execution anomalies

Post-trade risk may:

- block new orders
- cancel open orders
- reduce position
- disable a strategy
- disable an exchange
- activate a global kill switch


# 37. Kill Switches

Kill-switch scopes:

- global
- exchange
- account
- strategy
- market
- execution gateway

Activation sources:

- operator
- automated risk rule
- reconciliation failure
- adapter failure
- excessive losses
- data staleness
- unknown order state
- repeated rejects

Activation behavior:

1. block new approvals
2. cancel scoped open orders where safe
3. preserve market-data collection
4. emit audit events
5. alert operators
6. require explicit release policy

Release may require:

- operator acknowledgement
- successful reconciliation
- healthy adapters
- fresh data
- reviewed cause


# 38. Portfolio Accounting

## 38.1 Responsibilities

The portfolio subsystem owns:

- cash balances
- reserved cash
- positions
- average entry price
- realized PnL
- unrealized PnL
- fees
- settlement proceeds
- exchange exposure
- strategy allocation
- reconciliation status

## 38.2 Event-Sourced Updates

Portfolio projections update from:

- fills
- fee events
- transfers
- settlement events
- balance corrections
- reconciliation corrections

## 38.3 Precision

Use `Decimal`.

Define rounding policies per exchange.

Store original exchange precision and canonical precision.

## 38.4 Reconciliation

Reconciliation compares local state against:

- open orders
- positions
- balances
- fills
- settlements

Mismatch classes:

- timing difference
- duplicate event
- missing event
- mapping error
- fee difference
- manual activity
- exchange correction
- unknown

Unknown mismatches block live trading until resolved.


# 39. Profit and Loss Model

PnL categories:

- realized trading PnL
- unrealized mark-to-market PnL
- fees
- rebates
- settlement PnL
- transfer costs
- funding costs
- slippage attribution

Marking policies:

- midpoint
- best executable price
- conservative liquidation price
- model fair value
- settlement value

The selected mark policy must be explicit in reports.

Strategy PnL and account PnL must reconcile to portfolio PnL.


# 40. Settlement Architecture

Settlement is a domain lifecycle, not merely a final price update.

Required states:

- unresolved
- pending_resolution
- resolved
- disputed
- finalized
- settled
- corrected

Settlement records include:

- source
- outcome
- resolution timestamp
- finalization timestamp
- payout
- correction history
- supporting references
- exchange status

Strategies should stop opening new positions when settlement state or market
status disallows trading.


# 41. Configuration Architecture

## 41.1 Sources

Configuration precedence:

1. built-in defaults
2. repository configuration
3. environment-specific configuration
4. environment variables
5. command-line overrides
6. controlled operator changes

## 41.2 Validation

Use Pydantic Settings.

Invalid configuration prevents service startup.

## 41.3 Configuration Classes

- AppConfig
- DatabaseConfig
- ExchangeConfig
- StrategyConfig
- RiskConfig
- ReplayConfig
- SimulationConfig
- MonitoringConfig
- SecurityConfig

## 41.4 Secrets

Secrets are referenced, not embedded.

Approved sources:

- environment injection
- operating-system secret store
- cloud secret manager
- encrypted local development store

Secrets must be redacted in:

- logs
- traces
- errors
- configuration dumps
- support bundles


# 42. Security Architecture

## 42.1 Principles

- least privilege
- secret minimization
- environment isolation
- explicit live-mode activation
- immutable audit records
- dependency scanning
- signed releases where practical

## 42.2 Credential Separation

Use separate credentials for:

- development
- paper or sandbox
- shadow
- live

Use exchange API permissions that exclude withdrawals when possible.

## 42.3 Network Controls

Production may restrict outbound traffic to approved exchange and monitoring
endpoints.

Operator APIs should bind to trusted networks and require authentication.

## 42.4 Audit Log

Audit events include:

- configuration changes
- strategy enable and disable
- live-mode activation
- kill-switch changes
- risk-limit changes
- credential rotation metadata
- manual order actions
- reconciliation overrides


# 43. Observability Architecture

## 43.1 Logs

Use structured JSON logs.

Required fields:

- timestamp
- level
- service
- component
- environment
- event
- correlation_id
- trace_id
- exchange
- market_id
- strategy_id
- order_id
- replay_session_id

## 43.2 Metrics

Core metrics:

- market events per second
- event queue depth
- consumer lag
- adapter reconnects
- sequence gaps
- normalization failures
- order submit latency
- acknowledgement latency
- fill latency
- rejection rate
- cancel latency
- risk rejection rate
- strategy processing latency
- replay throughput
- portfolio mismatch count
- stale-data duration
- kill-switch state

## 43.3 Tracing

Distributed traces should connect:

```text
market event
  -> feature calculation
  -> signal
  -> order intent
  -> risk decision
  -> execution request
  -> exchange acknowledgement
  -> fill
  -> portfolio update
```

## 43.4 Health Checks

Health states:

- healthy
- degraded
- unhealthy
- unknown

Readiness and liveness are separate.

A service may be alive but not ready to trade.


# 44. Operator Control Plane

The operator control plane provides:

- health overview
- exchange connection state
- strategy state
- risk state
- open orders
- positions
- balances
- replay control
- kill-switch control
- configuration inspection
- reconciliation triggers

Dangerous actions require:

- authentication
- authorization
- explicit scope
- audit event
- confirmation policy
- idempotency key

The operator API should never expose secrets.


# 45. Failure Model

## 45.1 Failure Categories

- network failure
- exchange failure
- authentication failure
- rate-limit failure
- schema change
- data corruption
- sequence gap
- database failure
- queue saturation
- strategy failure
- model failure
- risk failure
- clock failure
- disk exhaustion
- configuration failure
- operator error

## 45.2 Recovery Principle

Recover automatically only when the recovery action is safe and well-defined.

Otherwise:

- fail closed for trading
- continue safe observation
- emit alerts
- preserve evidence
- require operator intervention


# 46. Failure Recovery Procedures

## 46.1 Exchange Disconnect

- mark data stale
- block new orders
- preserve local state
- reconnect
- resubscribe
- obtain snapshots
- reconcile
- unblock only after health checks pass

## 46.2 Database Unavailable

- stop durable consumers from acknowledging events
- buffer within limits
- block live trading if audit durability is required
- alert
- reconnect
- replay buffered events
- verify checksums

## 46.3 Strategy Crash

- isolate strategy
- block its intents
- cancel its orders according to policy
- persist crash metadata
- restart only under configured policy

## 46.4 Unknown Order State

- mark order LOST or UNKNOWN
- block conflicting new orders
- query exchange
- reconcile
- require manual review if unresolved

## 46.5 Stale Market Data

- mark market stale
- stop new quotes
- cancel exposed passive orders according to policy
- retain historical state
- resume after freshness threshold and snapshot validation


# 47. Backpressure and Capacity Management

Every queue must be bounded.

Every queue must expose:

- current depth
- maximum depth
- oldest message age
- enqueue failures
- consumer throughput

Backpressure policy is consumer-specific.

Critical durable paths:

- raw storage
- canonical storage
- order events
- fill events
- risk decisions
- portfolio events

Noncritical paths may sample:

- debug telemetry
- high-cardinality analytics
- experimental diagnostics

Capacity planning should model:

- markets subscribed
- messages per market
- event burst size
- retention period
- storage growth
- replay throughput
- concurrent strategies


# 48. Performance Targets

Initial targets are operational, not ultra-low-latency.

Suggested service-level objectives:

- no silent loss of order or fill events
- deterministic replay of supported datasets
- adapter recovery after transient disconnect
- order submission path measured end to end
- strategy event processing p99 below configured budget
- bounded memory under sustained load
- replay speed at least 10x real time for standard datasets
- health detection of stale feeds within configured threshold

Performance budgets are configuration and deployment dependent.

All optimization must be driven by profiling.


# 49. Scalability Strategy

Scaling order:

1. improve algorithms
2. reduce unnecessary allocations
3. batch storage writes
4. use efficient serialization
5. partition workloads
6. add worker processes
7. add external broker
8. move selected services to Go or Rust only if justified

Likely future service boundaries:

- market-data gateway
- event router
- order gateway
- replay service
- feature service

Research, strategy logic, analytics, and model development should remain in
Python unless evidence strongly supports another choice.


# 50. Schema Evolution

Every canonical event has a schema version.

Compatibility policy:

- additive optional fields are backward compatible
- field removal requires a new major schema version
- semantic changes require a new version
- enum expansion requires tolerant readers
- storage migrations must be reversible where practical

Consumers should:

- reject unsupported major versions
- tolerate unknown optional fields
- record deserialization failures
- support explicit upcasters for historical events


# 51. Data Lineage

Every model prediction and order intent should be traceable to source data.

Lineage chain:

```text
raw records
    |
canonical events
    |
feature snapshot
    |
model prediction
    |
strategy signal
    |
order intent
    |
risk decision
    |
exchange order
    |
fill
    |
portfolio change
```

Lineage identifiers support:

- debugging
- research reproducibility
- audit
- model evaluation
- incident analysis


# 52. Experiment Architecture

An experiment records:

- experiment ID
- hypothesis
- dataset checksum
- code commit
- configuration hash
- strategy version
- model version
- seed
- start and end time
- result metrics
- generated artifacts
- notes
- approval status

Experiments must not silently read mutable live state.

Inputs should be pinned.

Outputs should be immutable or versioned.


# 53. Research Workflow

Recommended workflow:

1. define hypothesis
2. identify dataset
3. verify data quality
4. implement features
5. implement model or rule
6. run deterministic replay
7. run simulation
8. evaluate robustness
9. perform walk-forward validation
10. run paper mode
11. run shadow mode
12. perform risk review
13. enable limited live capital
14. monitor and review


# 54. Testing Architecture

Testing is part of architecture because the system depends on behavioral
contracts.

Test layers:

- unit tests
- property tests
- adapter contract tests
- integration tests
- replay determinism tests
- simulation scenario tests
- end-to-end paper tests
- controlled live smoke tests

Architectural invariants to test:

- strategies do not import concrete adapters
- financial values do not use float
- event models are immutable
- replay code does not call wall-clock time
- live execution cannot start without risk and reconciliation health
- duplicate fills are idempotent
- order state transitions are valid


# 55. Adapter Contract Testing

Every adapter must pass the same contract suite.

Contract categories:

- connect
- disconnect
- authentication failure
- market listing
- subscription
- snapshot parsing
- delta parsing
- trade parsing
- order submission
- cancellation
- open-order retrieval
- position retrieval
- balance retrieval
- reconnect
- sequence gap
- rate limit
- malformed payload

Fixtures must include real redacted payload shapes where licensing and policy
permit.


# 56. Replay Acceptance Tests

Replay acceptance tests verify:

- stable event order
- stable timestamps
- stable random behavior
- stable signals
- stable simulated fills
- stable PnL
- no external network calls
- no live database mutation
- correct pause and resume
- correct bounded time windows

Each golden replay fixture has an expected checksum.


# 57. Simulation Acceptance Tests

Simulation acceptance tests include:

- maker fill at queue front
- maker no-fill behind volume
- partial fill
- taker fill with slippage
- cancel before fill
- fill during cancel race
- latency-induced stale quote
- order rejection
- disconnect
- market halt
- settlement
- fee calculation
- multi-leg arbitrage imbalance


# 58. Deployment Environments

Recommended environments:

- local
- test
- development
- staging
- shadow
- production

Each environment has:

- explicit name
- separate credentials
- separate database
- separate storage namespace
- separate monitoring labels
- separate risk limits

Production configuration must not be reusable in local development by default.


# 59. Release Architecture

A release should include:

- semantic version
- source commit
- dependency lock
- database migration version
- canonical schema versions
- container image digest
- release notes
- rollback instructions

Deployment should support:

- preflight validation
- database migration checks
- configuration validation
- health verification
- controlled strategy restart
- rollback


# 60. Operational Runbooks

Required runbooks:

- exchange disconnect
- authentication failure
- sequence gap storm
- database outage
- disk exhaustion
- strategy crash
- unknown orders
- portfolio mismatch
- kill-switch activation
- market settlement correction
- bad deployment
- credential rotation
- live-mode disablement

Each runbook includes:

- symptoms
- detection
- immediate containment
- investigation
- recovery
- validation
- post-incident actions


# 61. Architecture Decision Records

Initial ADR set:

- ADR-001: Python-first implementation
- ADR-002: Modular monolith before microservices
- ADR-003: Canonical event model
- ADR-004: Raw payload preservation
- ADR-005: PostgreSQL as initial system of record
- ADR-006: Decimal for financial values
- ADR-007: Injected clock abstraction
- ADR-008: At-least-once durable delivery
- ADR-009: Strategy and model separation
- ADR-010: Fail-closed live trading
- ADR-011: LLM-assisted but deterministically validated market matching
- ADR-012: Shadow trading before live trading
- ADR-013: Versioned schemas and event envelopes
- ADR-014: Explicit operator kill switches
- ADR-015: Idempotent execution commands


# 62. Detailed Component Catalog

The following catalog defines the role of each major package.

## 62.1 app

Application composition and dependency injection.

Owns:

- startup
- shutdown
- service wiring
- runtime mode
- process lifecycle

Does not own domain logic.

## 62.2 domain

Pure domain models and invariants.

Owns:

- value objects
- aggregates
- domain services
- state transitions

## 62.3 events

Canonical event definitions and schema registry.

## 62.4 commands

Command definitions and handlers.

## 62.5 adapters

Exchange-specific connectivity and mapping.

## 62.6 normalization

Raw-to-canonical transformation.

## 62.7 ingestion

Subscription orchestration and ingestion pipelines.

## 62.8 bus

In-process and future external messaging implementations.

## 62.9 storage

Repositories, event store, raw store, and transaction management.

## 62.10 replay

Historical event loading, sorting, scheduling, and session control.

## 62.11 clock

Clock interfaces and implementations.

## 62.12 strategies

Strategy interfaces, registry, lifecycle, and built-in strategies.

## 62.13 models

Predictive model interfaces, metadata, loading, and inference.

## 62.14 matching

Cross-exchange market relationship analysis.

## 62.15 simulation

Simulated exchange behavior and scenario modeling.

## 62.16 execution

Order routing, state management, and reconciliation.

## 62.17 risk

Pre-trade, post-trade, limits, and kill switches.

## 62.18 portfolio

Positions, balances, PnL, and reconciliation projections.

## 62.19 analytics

Research metrics, reporting, and attribution.

## 62.20 monitoring

Logs, metrics, traces, health, and alerting.

## 62.21 config

Typed configuration and environment loading.

## 62.22 security

Secret redaction, authorization helpers, and audit support.

## 62.23 operator_api

Operational read and control endpoints.

## 62.24 cli

Research, replay, migration, and operations commands.


# 63. Key Sequence Diagrams

## 63.1 Live Market Data

```text
Exchange     Adapter     Raw Store     Normalizer     Event Bus     Strategy
   |            |             |             |             |             |
   |--message-->|             |             |             |             |
   |            |--persist--->|             |             |             |
   |            |-------------raw event---->|             |             |
   |            |             |             |--publish--->|             |
   |            |             |             |             |--event----->|
```

## 63.2 Live Order

```text
Strategy     Risk      Execution     Adapter     Exchange     Portfolio
   |          |            |            |            |            |
   |--intent->|            |            |            |            |
   |          |--approve-->|            |            |            |
   |          |            |--submit--->|            |            |
   |          |            |            |--request-->|            |
   |          |            |            |<--ack------|            |
   |          |            |<--event----|            |            |
   |          |            |            |<--fill-----|            |
   |          |            |<--fill-----|            |            |
   |          |            |------------------------------fill---->|
```

## 63.3 Replay

```text
Replay Store     Replay Engine     Replay Clock     Event Bus     Strategy
     |                 |                 |              |             |
     |--events-------->|                 |              |             |
     |                 |--advance------->|              |             |
     |                 |--------------------publish---->|             |
     |                 |                 |              |--event----->|
```

## 63.4 Reconciliation

```text
Scheduler     Reconciler     Adapter     Exchange     Portfolio     Risk
    |             |             |            |            |           |
    |--run------->|             |            |            |           |
    |             |--query----->|            |            |           |
    |             |             |--request-->|            |           |
    |             |             |<--state----|            |           |
    |             |<--state-----|            |            |           |
    |             |----------------compare-->|            |           |
    |             |----------------result---------------------------->|
```


# 64. State Ownership Matrix

```text
State                         Owner
--------------------------------------------------------
Raw exchange payloads         Raw store
Canonical event history       Event store
Current order book            Market-data projection
Strategy local state          Strategy instance
Order lifecycle               Execution engine
Exchange connection state     Adapter
Risk limits                   Risk engine
Kill-switch state             Risk engine
Positions                     Portfolio
Cash balances                 Portfolio
Market relationships          Matching subsystem
Replay session state          Replay engine
Model metadata                Model registry
Operational health            Monitoring subsystem
```

No state should have two authoritative owners.


# 65. Interface Design Rules

Interfaces should be:

- narrow
- asynchronous where I/O is involved
- explicit about timeouts
- explicit about idempotency
- typed
- versioned
- testable with fakes
- free of exchange-specific leakage

Avoid:

- generic dictionaries
- unbounded callbacks
- hidden global state
- singleton service locators
- magic environment reads inside domain code
- interfaces that expose database sessions to strategies


# 66. Numeric and Probability Semantics

Use explicit types for:

- price
- probability
- quantity
- money
- fee
- payout

Avoid ambiguous numeric fields named `value`.

Probability:

```text
0 <= probability <= 1
```

Price semantics must specify whether the value is:

- probability-like price
- currency amount
- cents
- decimal currency units
- payout-adjusted price

Conversions occur at adapter boundaries.


# 67. Time Semantics

Every timestamp field must identify its meaning.

Common timestamps:

- exchange event time
- local receive time
- normalization time
- publish time
- order submit time
- acknowledgement time
- fill time
- settlement time

All persisted timestamps use UTC.

Naive datetimes are prohibited.

Latency calculations should state the timestamp pair used.


# 68. Auditability Requirements

The platform must answer:

- why was this order submitted?
- which strategy created it?
- which signal caused it?
- which model version contributed?
- which risk rules approved it?
- which configuration was active?
- which exchange response was received?
- which fills changed the position?
- which data was visible at decision time?
- who enabled live trading?
- who changed a risk limit?


# 69. Privacy and Data Handling

The platform should minimize personal data.

Exchange account identifiers and credentials are sensitive.

Logs should avoid:

- authentication tokens
- private keys
- full account identifiers
- personally identifying metadata
- complete request headers

Support bundles must redact sensitive fields.


# 70. Open-Source Boundary

Recommended separation:

Open-source repository:

- domain models
- adapters using public APIs
- replay
- simulation
- strategy interfaces
- example strategies
- risk framework
- portfolio framework
- tests
- documentation

Private deployment repository or configuration:

- credentials
- proprietary strategies
- proprietary models
- account identifiers
- production limits
- private datasets
- production infrastructure details


# 71. Extension Guide

## 71.1 Adding an Exchange

1. implement adapter interface
2. define raw payload models
3. implement mapper
4. declare capabilities
5. add fixtures
6. pass adapter contract suite
7. add reconciliation support
8. document precision and fees
9. add rate-limit configuration
10. add operational runbook

## 71.2 Adding a Strategy

1. implement strategy interface
2. define typed configuration
3. define subscribed events
4. define state model
5. emit signals
6. emit order intents
7. add unit tests
8. add replay tests
9. add simulation scenarios
10. document risk assumptions

## 71.3 Adding a Model

1. define feature schema
2. register model metadata
3. pin training dataset
4. implement prediction interface
5. add calibration tests
6. add deterministic inference tests
7. document limitations
8. version model artifact


# 72. Initial Implementation Roadmap

## Phase 0: Repository Foundation

- Python project
- uv
- package layout
- CI
- logging
- configuration
- base domain types

## Phase 1: Canonical Domain

- identifiers
- event envelope
- market models
- order models
- portfolio models
- risk models

## Phase 2: Exchange Connectivity

- Kalshi adapter
- Polymarket adapter
- fixtures
- contract tests

## Phase 3: Ingestion and Storage

- raw store
- canonical event store
- market catalog
- order-book projections

## Phase 4: Replay

- replay clock
- dataset loader
- deterministic sorting
- session metadata
- golden tests

## Phase 5: Strategy Runtime

- registry
- lifecycle
- context
- signal model
- baseline strategies

## Phase 6: Simulation

- simulated exchange
- latency
- fills
- fees
- scenarios

## Phase 7: Risk and Portfolio

- pre-trade checks
- limits
- kill switches
- positions
- PnL
- reconciliation

## Phase 8: Paper and Shadow

- live data
- hypothetical orders
- outcome comparison
- operational dashboards

## Phase 9: Limited Live

- live gateway
- low limits
- manual approval
- incident runbooks
- post-trade review

## Phase 10: Scale and Expansion

- more exchanges
- distributed messaging
- advanced models
- improved market matching
- selected compiled services


# 73. Architecture Acceptance Criteria

The architecture implementation is acceptable when all of the following are
true.

## 73.1 Exchange Independence

- strategies import no concrete exchange modules
- adapters pass common contracts
- canonical events hide exchange payload shape

## 73.2 Replay

- the same dataset produces stable result checksums
- replay uses injected time
- replay cannot submit live orders
- replay metadata captures code and configuration

## 73.3 Execution

- order commands are idempotent
- order transitions are validated
- ambiguous orders trigger reconciliation
- fills are applied once

## 73.4 Risk

- every live order has a recorded risk decision
- stale risk state blocks trading
- kill switches operate by scope
- operator changes are audited

## 73.5 Portfolio

- positions and balances reconcile
- PnL uses Decimal
- settlement is represented explicitly
- unknown mismatches block live trading

## 73.6 Observability

- critical flows include correlation IDs
- queue depth is measurable
- adapter state is visible
- strategy state is visible
- live readiness is distinguishable from process liveness

## 73.7 Security

- secrets are never logged
- environments use separate credentials
- live mode requires explicit activation
- dangerous operator actions are audited


# 74. Architectural Invariants

These invariants are non-negotiable unless superseded by an ADR.

1. Strategy code does not call exchange APIs directly.
2. Financial accounting does not use binary floating-point values.
3. Domain time comes from an injected clock.
4. Published canonical events are immutable.
5. Raw payloads are preserved when available.
6. Live orders require pre-trade risk approval.
7. Unknown accounting or order state blocks new risk.
8. Reconciliation is mandatory after adapter reconnect.
9. LLM output alone cannot establish tradable market equivalence.
10. Replay and live runtimes share canonical event contracts.
11. Every order and fill is traceable to strategy and signal lineage.
12. Every dangerous operator action is audited.
13. Queues are bounded.
14. Consumers are idempotent where delivery may repeat.
15. Infrastructure dependencies do not leak into the domain layer.


# 75. Glossary

Adapter:
An exchange-specific component that translates between external APIs and
canonical platform interfaces.

Canonical event:
An exchange-independent immutable fact represented using a versioned schema.

Command:
A request for a component to perform an action.

Event:
A record that something occurred.

Fill:
An executed quantity against an order.

Order intent:
A strategy's desired trade before risk approval.

Paper trading:
Live market data with simulated execution.

Replay:
Deterministic playback of historical canonical events.

Shadow trading:
Live decisioning and hypothetical execution without exchange submission.

Strategy:
A stateful policy that consumes events and emits signals or order intents.

Signal:
A research or trading opinion produced by a strategy or model.

Kill switch:
A control that blocks or stops trading at a defined scope.

Reconciliation:
Comparison of local state with exchange-authoritative state.

Canonical market:
An internal market identity used across exchanges.

Market relationship:
A typed logical or economic relationship between markets or outcomes.

Projection:
A current-state view derived from events.

Raw event:
An original exchange payload plus transport metadata.


# 76. Final Design Position

PMRP should begin as a disciplined Python modular monolith.

The platform should not begin as a collection of microservices.

It should not begin with a high-performance language rewrite.

It should not begin with live trading.

The correct sequence is:

- define canonical contracts
- collect trustworthy data
- build deterministic replay
- validate strategies
- simulate execution
- establish accounting
- enforce risk
- run paper and shadow modes
- then enable limited live trading

The system's competitive advantage should come from better data, better
research, better models, better market understanding, and safer execution.

The architecture exists to make those advantages reproducible.


# Appendix A. Canonical Interface Sketches

The following sketches are architectural, not final implementation code.

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Price:
    value: Decimal

    def __post_init__(self) -> None:
        if self.value < Decimal("0"):
            raise ValueError("price must be non-negative")


@dataclass(frozen=True)
class Probability:
    value: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.value <= Decimal("1"):
            raise ValueError("probability must be between zero and one")


@dataclass(frozen=True)
class Quantity:
    value: Decimal

    def __post_init__(self) -> None:
        if self.value < Decimal("0"):
            raise ValueError("quantity must be non-negative")


@dataclass(frozen=True)
class MarketRef:
    canonical_market_id: str
    exchange: str
    exchange_market_id: str


@dataclass(frozen=True)
class OrderIntent:
    intent_id: UUID
    strategy_id: str
    market: MarketRef
    side: Side
    quantity: Quantity
    limit_price: Price
    created_at: datetime
    expires_at: datetime | None
    correlation_id: UUID


class RiskService(Protocol):
    async def evaluate(
        self,
        intent: OrderIntent,
    ) -> "RiskDecision":
        ...


class PortfolioView(Protocol):
    async def position_for(
        self,
        market_id: str,
    ) -> "PositionSnapshot":
        ...


class SignalPublisher(Protocol):
    async def publish(
        self,
        signal: "Signal",
    ) -> None:
        ...


class OrderIntentPublisher(Protocol):
    async def publish(
        self,
        intent: OrderIntent,
    ) -> None:
        ...
```


# Appendix B. Event Processing Rules

For every durable event consumer:

1. receive event
2. validate schema version
3. check idempotency store
4. begin transaction
5. apply domain transition
6. update projection
7. record processed event ID
8. commit
9. acknowledge delivery

On failure:

1. roll back
2. classify error
3. retry if safe
4. send to dead-letter storage after policy threshold
5. alert if critical

Consumers must not acknowledge before durable state is committed.


# Appendix C. Order Transition Table

```text
Current State       Input Event                Next State
---------------------------------------------------------------
CREATED             risk_requested             RISK_PENDING
RISK_PENDING        risk_approved              APPROVED
RISK_PENDING        risk_rejected              REJECTED
APPROVED            submit_started             SUBMITTING
SUBMITTING          submitted                  SUBMITTED
SUBMITTING          submit_failed              FAILED
SUBMITTED           accepted                   ACCEPTED
SUBMITTED           rejected                   REJECTED
SUBMITTED           timeout_unknown            LOST
ACCEPTED            partial_fill               PARTIALLY_FILLED
ACCEPTED            full_fill                  FILLED
ACCEPTED            cancel_requested           CANCEL_REQUESTED
PARTIALLY_FILLED    partial_fill               PARTIALLY_FILLED
PARTIALLY_FILLED    full_fill                  FILLED
PARTIALLY_FILLED    cancel_requested           CANCEL_REQUESTED
CANCEL_REQUESTED    cancel_started             CANCELLING
CANCELLING          cancelled                  CANCELLED
CANCELLING          partial_fill               PARTIALLY_FILLED
CANCELLING          full_fill                  FILLED
ACCEPTED            expired                    EXPIRED
PARTIALLY_FILLED    expired                    EXPIRED
```


# Appendix D. Risk Rule Catalog

Recommended initial rule identifiers:

- RISK-001 strategy_enabled
- RISK-002 exchange_enabled
- RISK-003 market_enabled
- RISK-004 market_open
- RISK-005 market_data_fresh
- RISK-006 order_price_valid
- RISK-007 order_quantity_limit
- RISK-008 order_notional_limit
- RISK-009 market_position_limit
- RISK-010 portfolio_gross_limit
- RISK-011 portfolio_net_limit
- RISK-012 strategy_capital_limit
- RISK-013 exchange_capital_limit
- RISK-014 daily_loss_limit
- RISK-015 open_order_limit
- RISK-016 duplicate_order_guard
- RISK-017 balance_available
- RISK-018 reconciliation_healthy
- RISK-019 kill_switch_clear
- RISK-020 arbitrage_leg_risk
- RISK-021 stale_model_guard
- RISK-022 settlement_window_guard


# Appendix E. Metric Catalog

Recommended metric names:

- pmrp_adapter_connected
- pmrp_adapter_reconnect_total
- pmrp_adapter_sequence_gap_total
- pmrp_market_event_total
- pmrp_raw_event_write_latency_seconds
- pmrp_canonical_event_write_latency_seconds
- pmrp_event_bus_queue_depth
- pmrp_event_consumer_lag_seconds
- pmrp_strategy_event_latency_seconds
- pmrp_strategy_error_total
- pmrp_signal_total
- pmrp_order_intent_total
- pmrp_risk_approval_total
- pmrp_risk_rejection_total
- pmrp_order_submission_latency_seconds
- pmrp_order_ack_latency_seconds
- pmrp_fill_total
- pmrp_fill_latency_seconds
- pmrp_cancel_latency_seconds
- pmrp_open_orders
- pmrp_position_notional
- pmrp_realized_pnl
- pmrp_unrealized_pnl
- pmrp_reconciliation_mismatch_total
- pmrp_kill_switch_active
- pmrp_replay_events_per_second
- pmrp_replay_determinism_failure_total


# Appendix F. Health Model

A component health report contains:

```text
component
status
since
summary
last_success
last_error
dependencies
metrics
trading_impact
```

Example trading impact values:

- none
- strategy_only
- exchange_only
- account_only
- global

Readiness for live trading requires:

- configuration valid
- clock healthy
- database writable
- event bus healthy
- adapter connected
- market data fresh
- order state reconciled
- positions reconciled
- balances reconciled
- risk engine healthy
- kill switch clear


# Appendix G. Configuration Example

```toml
[app]
environment = "shadow"
service_name = "pmrp-trader"
live_trading_enabled = false

[database]
dsn_env = "PMRP_DATABASE_DSN"
pool_min_size = 2
pool_max_size = 20

[exchanges.kalshi]
enabled = true
account = "shadow"
api_key_env = "KALSHI_API_KEY"
private_key_env = "KALSHI_PRIVATE_KEY"

[exchanges.polymarket]
enabled = true
account = "shadow"
api_key_env = "POLYMARKET_API_KEY"
secret_env = "POLYMARKET_SECRET"

[risk]
global_kill_switch = false
max_order_notional = "100.00"
max_market_notional = "500.00"
max_daily_loss = "250.00"
max_open_orders = 100
max_data_age_seconds = 5

[replay]
default_speed = 20.0
deterministic = true

[monitoring]
json_logs = true
metrics_enabled = true
tracing_enabled = false
```


# Appendix H. Example Strategy Configuration

```toml
[strategies.market_maker_fed]
class = "pmrp.strategies.market_making:MarketMakingStrategy"
enabled = true
capital_allocation = "1000.00"
markets = ["canonical:fed_decision_2026_09"]

[strategies.market_maker_fed.parameters]
base_spread_bps = "75"
max_position = "200"
quote_size = "10"
refresh_interval_ms = 500
stale_after_ms = 1500
inventory_skew_bps = "20"
```


# Appendix I. Data Quality Policy

Severity levels:

- INFO
- WARNING
- ERROR
- CRITICAL

Examples:

INFO:
- duplicate ignored
- optional field absent

WARNING:
- delayed message
- inferred timestamp
- temporary gap recovered

ERROR:
- payload failed normalization
- book invalidated
- unsupported schema

CRITICAL:
- order update cannot be reconciled
- balance mismatch
- corrupted event archive
- wrong-environment credential use

Critical data-quality issues block live trading where relevant.


# Appendix J. Definition of Done for Architectural Components

A component is done when:

- interface is documented
- implementation is typed
- errors are classified
- logs are structured
- metrics are exposed
- configuration is validated
- unit tests exist
- integration tests exist where applicable
- failure modes are tested
- no secrets are logged
- shutdown is graceful
- idempotency is addressed
- replay behavior is defined
- operational runbook exists for critical components
