# Prediction Market Research Platform
## Testing and Validation Specification
- Document: `07_TESTING.md`
- Version: 1.0
- Status: Governing testing specification
- Related documents:
  - `01_ARCHITECTURE.md`
  - `02_ENGINEERING.md`
  - `03_SCHEMAS.md`
  - `04_IMPLEMENTATION.md`
  - `05_API_SPEC.md`
  - `06_DATABASE.md`
- Primary test framework: pytest
- Property-based testing: Hypothesis
- Async testing: pytest-asyncio
- Coverage: coverage.py and pytest-cov
- Character set: ASCII only
---
## Document Authority
This document defines how PMRP is tested, validated, and qualified for release.
It governs test strategy, fixtures, unit tests, property tests, integration tests,
contract tests, replay tests, simulation tests, end-to-end tests, performance,
security, continuous integration, coverage, flake control, and release gates.
Tests are part of the product. A feature is incomplete when its invariants and
failure modes are not protected by the appropriate test layers.
# 1. Executive Summary
PMRP is a financial research and trading platform. A defect can invalidate
research, corrupt simulation, submit an unintended order, misstate a position,
or miscalculate PnL.
The required test stack is layered:
```text
unit
property
contract
integration
database
API
replay
simulation
end-to-end
performance
security
operational validation
```
No single layer is sufficient. Unit tests provide speed and precision. Property
tests protect mathematical invariants. Contract tests enforce common adapter
behavior. Integration tests validate real boundaries. Replay tests protect
determinism. Simulation tests protect execution assumptions. End-to-end tests
protect complete workflows. Operational validation protects deployment and
recovery behavior.
# 2. Testing Objectives
The test system must provide confidence that:
- schemas reject invalid data
- exchange payloads normalize correctly
- events persist and replay exactly
- duplicate delivery does not duplicate business effects
- order state transitions are legal
- fills update orders and portfolios exactly once
- risk limits cannot be bypassed
- portfolio accounting reconciles
- simulation assumptions are explicit
- live and non-live environments remain separated
- failures degrade safely
- migrations preserve data
- APIs enforce authorization and idempotency
- releases are reproducible
# 3. Core Principles
## 3.1 Test Behavior
Assert externally meaningful behavior and invariants rather than private method
calls or implementation trivia.
## 3.2 Deterministic by Default
Tests must not depend on real wall-clock time, uncontrolled randomness, public
internet access, local timezone, execution order, or production credentials.
## 3.3 Exact Financial Assertions
Use Decimal and exact comparisons for prices, quantities, fees, balances, and
PnL.
## 3.4 Failure Paths Are First-Class
Every critical component requires tests for timeout, cancellation, duplicate
input, malformed input, stale state, dependency failure, restart, and partial
completion.
## 3.5 One Defect, One Regression Test
Every significant defect should add a test that fails before the fix and passes
after it.
# 4. Test Taxonomy
Recommended pytest markers:
```text
unit
property
asyncio
contract
integration
database
api
replay
simulation
end_to_end
performance
security
slow
live
postgres
websocket
```
Markers are registered centrally and used consistently in local and CI
commands.
# 5. Test Layout
```text
tests/
  unit/
  property/
  contract/
  integration/
  database/
  api/
  replay/
  simulation/
  end_to_end/
  performance/
  security/
  fixtures/
  factories/
  helpers/
  conftest.py
```
Unit tests should roughly mirror source package structure.
# 6. Naming and Structure
Use:
```python
def test_<behavior>_<condition>_<expected_result>() -> None:
    ...
```
Examples:
```python
def test_probability_above_one_is_rejected() -> None:
    ...
def test_duplicate_fill_does_not_change_position_twice() -> None:
    ...
```
Use Arrange, Act, Assert. Multiple assertions are acceptable when they verify
one coherent result.
# 7. Pytest Configuration
Recommended configuration:
```toml
[tool.pytest.ini_options]
minversion = "8.0"
addopts = ["--strict-config", "--strict-markers", "-ra"]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
  "unit: isolated tests",
  "property: property-based tests",
  "contract: interface conformance tests",
  "integration: component integration tests",
  "database: PostgreSQL tests",
  "api: HTTP and streaming API tests",
  "replay: deterministic replay tests",
  "simulation: simulated exchange tests",
  "end_to_end: safe full workflow tests",
  "performance: benchmark and capacity tests",
  "security: security validation tests",
  "slow: long-running tests",
  "live: explicitly authorized external tests",
]
```
# 8. Standard Commands
```bash
uv run pytest -m "unit or property"
uv run pytest -m integration
uv run pytest -m database
uv run pytest -m replay
uv run pytest -m "not live"
uv run pytest --cov=src/pmrp --cov-branch --cov-report=term-missing
```
Normal CI never runs live tests.
# 9. Fixture Standards
Fixtures must be minimal, realistic, redacted, versioned, deterministic, and
local.
Fixture directories should include a README describing source, capture date,
redaction, schema version, and intended tests.
Good names:
```text
order_book_snapshot_valid.json
order_book_delta_sequence_gap.json
order_rejected_insufficient_balance.json
trade_duplicate_exchange_id.json
market_unknown_status.json
```
# 10. Fixture Capture
Captured fixtures must remove credentials, authorization headers, personal
account details, and private strategy information.
They should preserve original field names, numeric strings, and timestamp
strings. Captured payloads must pass secret scanning.
# 11. Test Factories
Factories should make the important difference visible.
```python
def an_order(**changes: object) -> Order:
    base = Order(
        order_id=OrderId("ord_test"),
        quantity=Decimal("10"),
        filled_quantity=Decimal("0"),
        remaining_quantity=Decimal("10"),
        status=OrderStatus.ACCEPTED,
        ...
    )
    return replace(base, **changes)
```
Use domain-specific names such as `a_market`, `an_order`, `a_fill`, and
`a_risk_decision`.
# 12. Time and Randomness
Use FrozenClock, AdvancingTestClock, and ReplayClock.
Do not use real sleeps for business time.
All stochastic tests receive an explicit seed and report that seed on failure.
# 13. Unit Test Scope
Unit tests cover value objects, validators, mapping functions, calculations,
state machines, risk rules, feature functions, serialization, redaction, retry
classification, and cursor encoding.
They require no network, PostgreSQL, public service, wall-clock sleep, or secret.
# 14. Schema Unit Tests
Every canonical schema requires tests for:
- minimum valid payload
- full valid payload
- missing required field
- unknown extra field
- invalid enum
- invalid Decimal
- float rejection
- negative quantity
- naive datetime
- exact serialization round trip
- JSON Schema generation
- schema registry lookup
# 15. Decimal Tests
```python
def test_price_rejects_float() -> None:
    with pytest.raises(TypeError):
        Price(value=0.42)
```
Round-trip tests must assert exact Decimal equality.
# 16. Time Tests
Test UTC-aware acceptance, naive datetime rejection, frozen time stability,
replay clock progression, duration boundaries, and daylight-saving independence.
# 17. State Machine Tests
Every valid and invalid order transition must be covered.
Valid examples include creation, risk approval, submission, acceptance, partial
fill, final fill, cancel request, cancellation, rejection, and expiry.
Invalid terminal transitions must raise an explicit invariant error.
# 18. Mapping Tests
Adapter mapping tests verify external ID preservation, timestamp semantics,
Decimal conversion, side mapping, status mapping, optional fields, unknown enum
behavior, quality flags, source metadata, and sequence mapping.
# 19. Error Classification Tests
Examples:
```text
HTTP 401          AdapterAuthenticationError
HTTP 429          AdapterRateLimitError
timeout           AdapterTransportError
unique violation  idempotent result or duplicate error
serialization     ConcurrencyConflict
malformed payload ProtocolError or data-quality finding
```
# 20. Property-Based Testing
Use Hypothesis where input spaces are large and invariants are strong.
Priority areas:
- probability bounds
- order quantities
- order-book deltas
- order state machines
- fill idempotency
- portfolio accounting
- fee calculations
- serialization
- replay ordering
- pagination
# 21. Probability Properties
- accepted value remains in the closed interval zero through one
- complement remains in the same interval
- complement of complement returns the original value
- invalid values are rejected
# 22. Order Quantity Properties
- filled quantity is never negative
- remaining quantity is never negative
- filled plus remaining equals original quantity
- filled quantity never decreases
- remaining quantity never increases after a fill
# 23. Fill Idempotency Properties
- applying each unique fill once produces expected state
- applying each fill twice produces the same final state
- cumulative fill quantity never exceeds order quantity without an explicit finding
# 24. Portfolio Properties
- duplicate fill does not change position twice
- journal lines balance by currency
- fees reduce net PnL
- rebates increase net PnL
- settlement is idempotent
# 25. Order Book Properties
- bids remain descending
- asks remain ascending
- duplicate prices are resolved
- delete removes a level
- sequence gap invalidates the projection
# 26. Serialization Properties
- model to JSON to model preserves equality
- stable serialization produces stable hash
- Decimal never passes through float
- timestamps remain timezone-aware
# 27. Stateful Property Tests
Use Hypothesis state machines for order lifecycle, portfolio fill application,
order-book delta application, kill-switch lifecycle, and replay control.
Each state machine defines initial state, commands, preconditions, invariants,
and terminal states.
# 28. Async Testing
Async tests verify normal completion, cancellation, timeout, dependency failure,
shutdown, task cleanup, queue saturation, ordering, and backpressure.
Leaked task warnings are test failures.
# 29. Async Queue Tests
Test enqueue, dequeue, bounded capacity, full-queue policy, blocked cancellation,
shutdown with pending items, consumer failure isolation, and partition ordering.
# 30. Timeout and Cancellation
Use fake clocks or short deterministic test timeouts.
Test cancellation before work, during queue wait, during database I/O, during
reconnect, during shutdown, and after partial state change.
# 31. Event Bus Contract
Common contract:
- subscribe
- publish
- unsubscribe
- multiple subscribers
- typed filtering
- partition ordering
- bounded queue
- slow consumer handling
- consumer failure isolation
- graceful close
- deterministic mode
# 32. Adapter Contract Tests
Every adapter passes the same suite covering connection, disconnection, health,
authentication failure, market listing, order-book snapshot, deltas, trades,
reconnect, sequence gaps, rate limits, timeouts, malformed payloads, order
submission, cancellation, open orders, positions, balances, and fills.
# 33. Adapter Transport Tests
HTTP tests cover base URL, headers, timeout, retry classification, rate-limit
headers, and safe logging.
WebSocket tests cover connect, authenticate, subscribe, heartbeat, reconnect,
resubscribe, malformed frames, and close codes.
# 34. Adapter Fixture Matrix
Each exchange requires fixtures for normal payloads, all optional fields, missing
optional fields, unknown statuses, malformed Decimals, invalid timestamps,
duplicate messages, out-of-order messages, sequence gaps, rate limits, and
service errors.
# 35. Database Tests
Database tests use real PostgreSQL, not SQLite, for NUMERIC, TIMESTAMPTZ, JSONB,
partitions, SKIP LOCKED, advisory locks, transaction isolation, and Alembic.
# 36. Migration Tests
Test upgrade from empty database, upgrade from previous release, required
schemas, extensions, constraints, indexes, representative inserts, supported
downgrade, re-upgrade, and SQLAlchemy metadata alignment.
# 37. Database Constraint Tests
Required direct tests:
- duplicate event ID rejected
- duplicate fill ID rejected
- order quantity invariant
- negative quantity rejected
- invalid probability rejected
- cash balance identity
- duplicate client order ID rejected
- stale aggregate version rejected
# 38. Transaction Tests
Verify atomic rollback when an order transition, position update, journal insert,
outbox insert, risk reservation, or reconciliation correction fails.
No partial business state may remain after rollback.
# 39. Concurrency Tests
Use concurrent sessions for two fills on one order, duplicate fill arrival,
simultaneous risk approvals, two cancels, outbox workers using SKIP LOCKED,
optimistic conflicts, and one reconciliation per account.
# 40. Repository Contracts
Repositories must support tests for missing lookup, add, duplicate add behavior,
expected-version save, stale-version conflict, stream ordering, rollback, and
exact domain mapping.
# 41. API Tests
API tests cover authentication, authorization, validation, response schemas,
errors, correlation IDs, idempotency, pagination, ETags, rate limiting, audit,
WebSocket, SSE, and environment safety.
# 42. Authentication Tests
Test missing, malformed, expired, wrong-audience, wrong-environment, revoked,
viewer, operator, and service tokens.
# 43. Authorization Tests
For every mutating endpoint, test viewer denial, insufficient operator denial,
correct-scope success, wrong-environment denial, audit actor, and sensitive field
redaction.
# 44. API Idempotency Tests
```text
same key + same request        original response
same key + different request   409 conflict
concurrent duplicate request   one business effect
missing required key           400
restart between requests       original result retained
expired record                 documented behavior
```
# 45. Pagination Tests
Test first page, next page, stable order, no duplicates, invalid cursor, cursor
with changed filters, maximum limit, empty result, and snapshot consistency.
# 46. WebSocket and SSE Tests
WebSocket tests include authenticated connect, hello, subscription, forbidden
channel, heartbeat, missed heartbeat, sequence progression, slow consumer,
unsubscribe, and graceful shutdown.
SSE tests include event format, event ID, Last-Event-ID reconnect,
authorization, heartbeat comments, and slow-client handling.
# 47. OpenAPI Tests
Validate OpenAPI 3.1, stable operation IDs, security schemes, request schemas,
response schemas, error schemas, examples, Decimal strings, and UTC timestamps.
# 48. Replay Tests
Replay is a release gate.
Tests cover manifest validation, dataset checksum, deterministic ordering,
injected clock, fixed seed, no network, no live gateway, stable output checksum,
pause, resume, seek, cancel, and fault injection.
# 49. Golden Replay Dataset
```text
tests/fixtures/replay/basic_market/
  manifest.json
  events.jsonl
  expected_signals.jsonl
  expected_intents.jsonl
  expected_orders.jsonl
  expected_fills.jsonl
  expected_portfolio.json
  result_checksum.txt
```
# 50. Replay Determinism
Run the same replay twice in one process, in separate processes, with randomized
input file order before sorting, and at different wall-clock times.
All runs must produce the same checksum.
# 51. Replay Isolation
Architectural and runtime tests must prove that replay has no live order gateway,
requires no production credential, makes no network call, writes only approved
replay data, and tags events with replay_session_id.
# 52. Simulation Tests
Simulation tests validate fill, queue, latency, fee, rejection, slippage, and
settlement models. A fixed archive, configuration, code version, and seed must
produce the same orders, fills, portfolio, metrics, and checksum.
# 53. Simulation Scenario Catalog
- SIM-001: immediately marketable limit
- SIM-002: passive order no fill
- SIM-003: passive partial fill
- SIM-004: passive full fill
- SIM-005: cancel before activation
- SIM-006: fill during cancel race
- SIM-007: stale quote after latency
- SIM-008: market closes before activation
- SIM-009: insufficient balance
- SIM-010: post-only would cross
- SIM-011: maker fee
- SIM-012: taker fee
- SIM-013: rebate
- SIM-014: settlement win
- SIM-015: settlement loss
- SIM-016: disconnect with open order
- SIM-017: duplicate market event
- SIM-018: multi-leg imbalance
# 54. Strategy Tests
Strategies must be deterministic with respect to events, configuration, clock,
model artifacts, seed, and portfolio snapshot.
Required tests cover initialization, subscriptions, signal generation, intent
generation, no-action conditions, stale data, missing features, invalid
configuration, stop, restart, and health degradation.
# 55. Strategy Replay Tests
Every production strategy should have a small golden replay, a no-trade replay,
a stale-data replay, a risk-rejection replay, and a restart/checkpoint replay
when stateful.
# 56. Strategy Isolation
A failed strategy must change its health state, stop producing intents, leave
other strategies running, leave collection running, emit metrics, and preserve
diagnostic context.
# 57. Feature Tests
Every feature requires tests for formula, units, warm-up, missing data, window
boundary, event-time basis, market gap, reset behavior, leakage prevention, and
versioned deterministic output.
# 58. Model Tests
Verify artifact checksum, metadata completeness, feature compatibility, approved
version resolution, deterministic inference, prediction bounds, calibration,
missing artifact failure, and safe strategy degradation.
# 59. Matching Tests
Use fixtures for equivalent, complement, subset, false positive, different date,
different threshold, different jurisdiction, different settlement source,
ambiguous rules, and human-review state.
# 60. Risk Tests
Every rule requires a stable ID and version, pass case, fail case, exact boundary,
missing input, stale input where relevant, stable reason code, observed value,
and limit value.
# 61. Risk Rule Matrix
- RISK-001: test below, equal, above, missing, and stale states for strategy enabled.
- RISK-002: test below, equal, above, missing, and stale states for exchange enabled.
- RISK-003: test below, equal, above, missing, and stale states for market enabled.
- RISK-004: test below, equal, above, missing, and stale states for market open.
- RISK-005: test below, equal, above, missing, and stale states for market data fresh.
- RISK-006: test below, equal, above, missing, and stale states for price valid.
- RISK-007: test below, equal, above, missing, and stale states for quantity limit.
- RISK-008: test below, equal, above, missing, and stale states for notional limit.
- RISK-009: test below, equal, above, missing, and stale states for position limit.
- RISK-010: test below, equal, above, missing, and stale states for gross exposure.
- RISK-011: test below, equal, above, missing, and stale states for net exposure.
- RISK-012: test below, equal, above, missing, and stale states for strategy capital.
- RISK-013: test below, equal, above, missing, and stale states for exchange capital.
- RISK-014: test below, equal, above, missing, and stale states for daily loss.
- RISK-015: test below, equal, above, missing, and stale states for open order count.
- RISK-016: test below, equal, above, missing, and stale states for duplicate guard.
- RISK-017: test below, equal, above, missing, and stale states for available balance.
- RISK-018: test below, equal, above, missing, and stale states for reconciliation healthy.
- RISK-019: test below, equal, above, missing, and stale states for kill switch clear.
- RISK-020: test below, equal, above, missing, and stale states for arbitrage leg risk.
# 62. Risk Concurrency
Simultaneous intents competing for the same limit must never exceed the limit.
Reservations must be atomic, idempotent, expirable, and releasable on cancel.
# 63. Risk Fail Closed
Required state that is missing, stale, invalid, unreconciled, ambiguous, or
unavailable must produce rejection and a stable reason code.
# 64. Kill-Switch Tests
Test global, exchange, account, strategy, and market scopes; duplicate activation;
release; release precondition failure; audit; event publication; intent blocking;
and cancellation policy.
# 65. Portfolio Tests
Portfolio tests protect quantity, average cost, realized PnL, unrealized PnL,
fees, rebates, balances, journals, settlement, correction, and reconciliation.
# 66. Position and PnL Scenarios
Required scenarios:
- first buy
- additional buy
- partial sell
- full close
- reversal
- multiple fills
- duplicate fill
- out-of-order fill
- maker fee
- taker fee
- rebate
- settlement
- correction
# 67. Journal Tests
Every financial event must produce balanced lines per currency.
Test buy fill, sell fill, fee, rebate, settlement, transfer, and correction.
# 68. Reconciliation Tests
Test exact match, missing local order, missing external order, missing fill,
quantity mismatch, balance mismatch, manual exchange activity, settlement
mismatch, stale reconciliation, and failed dependency.
# 69. Execution Tests
Execution tests cover approved order input, state machine, idempotency, submit,
acknowledgement, rejection, partial fill, full fill, cancel, replace, timeout,
ambiguous submission, reconnect, reconciliation, and kill switch.
# 70. Ambiguous Submission
When acceptance is unknown, the order enters a safe unknown state, no blind retry
occurs, reconciliation starts, conflicting activity is blocked, and audit and
alerts are emitted.
# 71. Cancel-Fill Races
Test cancel before fill, fill before cancel, partial fill during cancel, full fill
during cancel, cancel rejection after fill, and duplicate cancel acknowledgement.
# 72. Reconnect Tests
After reconnect, subscriptions restore but trading remains gated until open
orders, fills, positions, and balances reconcile successfully.
# 73. Data Quality Tests
Test findings for missing timestamp, invalid probability, negative quantity,
sequence gap, stale snapshot, duplicate trade, unknown market, unsupported
status, crossed book, and timestamp reversal.
# 74. Data Quality Actions
Verify accept, accept with flag, quarantine, drop, invalidate projection, and
block trading. Critical findings must affect health and risk state.
# 75. End-to-End Tests
End-to-end tests validate complete safe workflows. Normal E2E tests never submit
live orders.
Fixture flow:
```text
raw fixture -> raw store -> normalization -> canonical event -> event bus ->
strategy -> risk -> simulation -> fill -> portfolio -> API read
```
# 76. Paper E2E
Verify live-like data, strategy signal, risk approval, simulated fill, portfolio
update, API visibility, kill-switch stop, session archive, and replay.
# 77. Shadow E2E
Verify exact hypothetical request, zero calls to adapter place-order, persisted
shadow request, hypothetical outcome evaluation, and explicit shadow labeling.
# 78. Live Gating E2E
Using a fake adapter, fail each precondition: live disabled, wrong environment,
missing credential reference, stale data, unhealthy risk, unhealthy
reconciliation, active kill switch, and missing authorization.
# 79. Security Tests
Security validation covers authentication, authorization, environment separation,
secret redaction, input validation, SQL injection resistance, path traversal,
unsafe deserialization, dependency vulnerabilities, container configuration,
and audit immutability.
# 80. Secret Redaction
Inject secrets into headers, URLs, bodies, exceptions, nested metadata, and
connection strings. Assert they never appear in logs, errors, traces, audit
payloads, or snapshots.
# 81. Abuse Tests
Test oversized JSON, deeply nested JSON, unknown fields, invalid Decimal, invalid
timestamp, malformed identifier, unsupported media type, malformed cursor,
header injection, and unauthorized horizontal access.
# 82. Performance Tests
Every benchmark defines workload, hardware, dependency lock, dataset, warm-up,
repetitions, metric, target, and variance.
Correctness tests remain separate.
# 83. Performance Inventory
Measure raw insert throughput, event append throughput, order transaction latency,
fill transaction latency, replay events per second, peak replay memory, API
latency, WebSocket delivery lag, pool wait, WAL growth, and sustained queue depth.
# 84. Capacity and Soak
Test expected load, two times expected load, and burst load across markets,
events, strategies, open orders, database rows, replay duration, and API clients.
Soak tests detect memory growth, task leaks, connection leaks, file descriptor
leaks, queue growth, outbox backlog, and reconnect instability.
# 85. Failure Injection
Inject network timeout, connection reset, database outage, slow database, queue
saturation, malformed payload, sequence gap, clock jump, duplicate event,
process cancellation, and outbox failure.
# 86. Mutation Testing
Recommended targets are risk rules, fee calculations, PnL, order transitions,
quantity invariants, serialization, and matching validators.
Run on a schedule or before major releases.
# 87. Coverage Policy
Repository floor:
```text
80 percent line coverage with branch coverage enabled
```
Core execution, risk, portfolio, replay, normalization, and adapter mapping
packages should target 90 percent or higher.
Coverage is a floor, not proof of correctness.
# 88. Golden Files and Snapshots
Golden files are appropriate for replay outputs, OpenAPI, JSON Schema bundles,
canonical serialization, migration snapshots, and structured reports.
Golden updates require explanation and review.
# 89. Test Data Versioning
Every large dataset includes dataset ID, checksum, source, time range, schema
versions, redaction status, usage note, and expected results.
Tests never silently download mutable data.
# 90. Flaky-Test Policy
A flaky test is a defect.
Required response:
1. reproduce
2. identify cause
3. fix
4. add deterministic control
5. monitor
Blind retries are prohibited.
# 91. Quarantine
Temporary quarantine requires an issue, owner, expiry, visible CI reporting, and
non-safety-critical classification.
Risk, execution, portfolio, and replay determinism tests should not be silently
quarantined.
# 92. Parallel Execution
Parallel tests require isolated databases or schemas, unique ports, unique temp
paths, no shared mutable globals, deterministic fixtures, and thread-safe caches.
# 93. Pull Request CI
Required jobs:
1. formatting
2. linting
3. type checking
4. unit tests
5. property tests
6. database tests
7. adapter contract tests
8. API tests
9. replay tests
10. simulation tests
11. coverage
12. security scans
13. package build
# 94. Scheduled CI
Scheduled jobs include extended replay, long simulation, mutation tests,
dependency scans, container scans, benchmarks, soak tests, flake detection, and
backup restore tests.
# 95. Release Gates
A release does not proceed with failing required CI, unexpected replay checksum,
accounting mismatch, risk failure, migration failure, security blocker, live
safety failure, kill-switch failure, or known flaky safety test.
# 96. Pre-Live Qualification
Before live release:
- shadow run reviewed
- adapter contract complete
- state machine complete
- risk concurrency complete
- fill idempotency complete
- portfolio reconciliation complete
- kill-switch drill complete
- restore tested
- runbooks exercised
# 97. Test Evidence
High-risk pull requests attach commands, reports, coverage, replay checksum
comparison, migration results, benchmark comparison, failure-injection results,
and operational review notes.
# 98. Severity and Regression
S0 and S1 defects require immediate containment, a regression test, incident
review, and release blocking until resolved.
# 99. Component Test Template
Every stateful component requires lifecycle, health, shutdown, cancellation,
dependency failure, restart, metrics, and structured logging tests where
relevant.
# 100. Schemas Test Requirements
- valid minimum and full payloads
- invalid required and extra fields
- exact round trip
- JSON Schema generation
- compatibility
# 101. Adapters Test Requirements
- transport
- mapping
- fixtures
- contract suite
- reconnect
- sequence recovery
- rate limits
- timeouts
- safe logging
# 102. Strategies Test Requirements
- configuration
- determinism
- signals
- no-action
- stale data
- replay
- simulation
- lifecycle
# 103. Risk Test Requirements
- rule boundaries
- missing state
- stale state
- reason codes
- reservations
- kill switches
# 104. Portfolio Test Requirements
- exact Decimal
- duplicate protection
- journal balance
- reconciliation
- corrections
- lineage
# 105. Execution Test Requirements
- approval
- idempotency
- timeouts
- ambiguity
- reconnect
- reconciliation
- state transitions
- audit
# 106. API Test Requirements
- success
- authentication
- authorization
- validation
- not found
- conflict
- idempotency
- audit
- OpenAPI
# 107. Database Test Requirements
- migration
- constraints
- indexes
- types
- queries
- rollback
- integration
# 108. Logging Tests
Critical logs should include stable event name, correlation ID, order or market
context, and error classification while excluding secrets and duplicate stack
traces.
# 109. Metrics Tests
Verify counter increments, histogram observations, bounded labels, no raw IDs as
labels, health transitions, and backlog measurements.
# 110. Health Tests
Test healthy, degraded, unhealthy, dependency unavailable, stale data, trading
impact, readiness, liveness, and recovery.
# 111. Configuration Tests
Test valid configuration, missing required values, invalid Decimal, invalid URL,
unknown field, secret redaction, hash stability, environment override, and safe
production defaults.
# 112. CLI Tests
Test help, validation errors, exit codes, JSON output, human output, dangerous
flag requirements, environment mismatch, and idempotency.
# 113. Container Tests
Validate build, non-root user, startup command, health check, graceful signals,
absence of secrets, locked dependencies, and Python version.
# 114. Backup and Restore Tests
Scheduled validation creates a backup, restores an isolated instance, verifies
schema revision and event hashes, checks positions, runs a replay sample, and
records actual duration.
# 115. Operational Drills
Exercise adapter disconnect, sequence gap, database outage, stale data, unknown
order, missing fill, portfolio mismatch, kill switch, bad deployment, and
credential rotation.
# 116. Test Reporting
CI retains JUnit XML, coverage XML, replay checksums, migration logs, benchmark
results, security reports, and restore reports, all associated with commit and
environment.
# 117. Coding-Agent Test Instructions
Agent work packets must define exact test files, layer, fixtures, acceptance
criteria, prohibited network access, commands, and coverage expectations.
Agents must never remove or weaken tests merely to make CI pass.
# 118. Coding-Agent Packet: Order State Machine
- every valid transition
- terminal invalid transitions
- partial and final fill
- fill during cancellation
- duplicate fill
- quantity properties
# 119. Coding-Agent Packet: Risk Freshness Rule
- below boundary
- equal boundary
- above boundary
- missing timestamp
- future timestamp
- stable reason codes
# 120. Coding-Agent Packet: Adapter Contract
- connect
- disconnect
- health
- listing
- stream
- sequence gap
- reconnect
- rate limit
- timeout
- malformed payload
# 121. Coding-Agent Packet: Fill Transaction
- first fill
- duplicate fill
- partial fill
- final fill
- rollback after journal failure
- concurrent duplicate
# 122. Initial Test Inventory
```text
T-001 package import
T-002 canonical strictness
T-003 Decimal float rejection
T-004 UTC datetime validation
T-005 event serialization
T-006 event ID uniqueness
T-007 event bus delivery
T-008 event bus cancellation
T-009 raw record round trip
T-010 replay ordering
T-011 market mapping
T-012 sequence gap
T-013 order transitions
T-014 fill idempotency
T-015 risk freshness boundary
T-016 risk reservation concurrency
T-017 portfolio fill application
T-018 journal balance
T-019 replay determinism
T-020 simulation partial fill
T-021 API authorization
T-022 API idempotency
T-023 kill-switch E2E
T-024 migration upgrade
T-025 backup restore sample
```
# 123. Release Qualification Matrix
```text
Release Type       Required Suites
---------------------------------------------------------------
documentation      lint and documentation validation
schema-only        unit, property, compatibility
adapter market     unit, contract, integration, replay
strategy           unit, replay, simulation, risk
database           migration, database, integration, restore sample
risk               unit, property, concurrency, E2E
portfolio          unit, property, database, reconciliation
execution          all non-live plus shadow validation
live               all suites plus operational readiness
```
# 124. Stop-Ship Conditions
Stop release for a failing safety-critical test, unexpected replay checksum,
accounting mismatch, unreviewed schema break, migration data loss, failed live
gating, failed kill switch, secret exposure, duplicate-fill defect, or ambiguous
order retry defect.
# 125. Test Review Checklist
```text
[ ] Test name describes behavior.
[ ] Scenario is minimal.
[ ] Inputs are explicit.
[ ] Time is controlled.
[ ] Randomness is seeded.
[ ] Financial assertions are exact.
[ ] Failure path is covered.
[ ] Idempotency is considered.
[ ] Cleanup is complete.
[ ] No production secret is used.
[ ] Test does not depend on order.
[ ] Assertion protects a real invariant.
```
# 126. Definition of Done
A test change is complete when the test fails before the intended fix where
applicable, passes after implementation, uses the correct layer, documents
fixtures, introduces no flake, preserves coverage, uses correct markers, and
runs in CI.
# 127. Local Developer Workflow
```bash
uv run pytest path/to/test_file.py -q
uv run pytest -m "unit or property"
uv run pytest -m "not live" --cov=src/pmrp --cov-branch
```
High-risk changes also run targeted integration, replay, and failure suites.
# 128. Pull Request Test Summary
Every pull request should state tests added or changed, commands run, fixtures
added, replay output impact, migration impact, coverage impact, and known
limitations.
# 129. Test Data Privacy
Do not include production account details, API credentials, personal data,
private strategy secrets, or private model artifacts.
Use synthetic or redacted data.
# 130. Live Tests
Live tests are disabled by default and require an explicit marker, environment
flag, bounded account, minimal risk, audit, and operator approval.
Normal CI never runs live tests.
# 131. Live Smoke Rules
Use one approved market, minimal quantity, explicit order type, short timeout,
cancellation where possible, reconciliation afterward, complete ID capture, and
immediate stop on ambiguity.
# 132. Test Environment Matrix
```text
Environment   Network   PostgreSQL   Exchange Orders
---------------------------------------------------------------
unit          no        no           no
integration   local     yes          no
replay        no        optional     no
simulation    no        optional     no
paper         market    yes          no
shadow        market    yes          no
staging live  yes       yes          controlled
production    yes       yes          explicit only
```
# 133. Test Ownership
Package owners own test coverage, fixtures, golden files, flake resolution,
release qualification, and incident regressions.
Quality remains a shared engineering responsibility.
# 134. Anti-Patterns
Avoid real sleeps, public network calls, production data, float expected money,
one giant fixture, overmocking domain logic, snapshotting everything, private
method assertions, retries hiding flakes, test-order dependence, and unseeded
simulation.
# 135. Exception Process
A temporary testing exception requires narrow scope, documented risk, owner,
issue, expiry, and preserved safety coverage.
No exception may bypass mandatory live safety validation.
# 136. Governance
Review this document before first live release, after major incidents, after
major test-tool changes, when adding an exchange, when changing replay semantics,
and at least annually.
# 137. Final Testing Position
The purpose of testing is not to prove that PMRP has no defects.
The purpose is to make important defects difficult to introduce, easy to detect,
and safe to recover from.
Testing must protect evidence, determinism, state transitions, financial
arithmetic, risk limits, idempotency, reconciliation, environment separation,
and operator control.
A release is trustworthy only when relevant behavior has been exercised at the
correct layers and the evidence is reproducible.
# Appendix A. Detailed Test Case Catalog

The following catalogs define the minimum named cases expected for each major test domain. Each case should be implemented at the lowest test layer that can protect the behavior without hiding important integration risk.

## A.1. Schema Boundary Validation

Required cases:

- `SCHEMA_BOUNDARY_VALIDATION_01`: minimum valid payload.
- `SCHEMA_BOUNDARY_VALIDATION_02`: full valid payload.
- `SCHEMA_BOUNDARY_VALIDATION_03`: missing required field.
- `SCHEMA_BOUNDARY_VALIDATION_04`: unknown field.
- `SCHEMA_BOUNDARY_VALIDATION_05`: wrong enum.
- `SCHEMA_BOUNDARY_VALIDATION_06`: float in Decimal field.
- `SCHEMA_BOUNDARY_VALIDATION_07`: negative quantity.
- `SCHEMA_BOUNDARY_VALIDATION_08`: naive datetime.
- `SCHEMA_BOUNDARY_VALIDATION_09`: invalid identifier prefix.
- `SCHEMA_BOUNDARY_VALIDATION_10`: oversized text.
- `SCHEMA_BOUNDARY_VALIDATION_11`: round-trip serialization.
- `SCHEMA_BOUNDARY_VALIDATION_12`: stable schema version.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.2. Event Envelope

Required cases:

- `EVENT_ENVELOPE_01`: event ID required.
- `EVENT_ENVELOPE_02`: event type required.
- `EVENT_ENVELOPE_03`: schema version positive.
- `EVENT_ENVELOPE_04`: occurred time UTC.
- `EVENT_ENVELOPE_05`: received time UTC.
- `EVENT_ENVELOPE_06`: published time UTC.
- `EVENT_ENVELOPE_07`: correlation ID required.
- `EVENT_ENVELOPE_08`: causation optional.
- `EVENT_ENVELOPE_09`: quality flags stable.
- `EVENT_ENVELOPE_10`: replay session lineage.
- `EVENT_ENVELOPE_11`: simulation session lineage.
- `EVENT_ENVELOPE_12`: stable payload hash.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.3. Command Envelope

Required cases:

- `COMMAND_ENVELOPE_01`: command ID required.
- `COMMAND_ENVELOPE_02`: command type required.
- `COMMAND_ENVELOPE_03`: issuer required.
- `COMMAND_ENVELOPE_04`: issued time UTC.
- `COMMAND_ENVELOPE_05`: idempotency key required.
- `COMMAND_ENVELOPE_06`: deadline before issue rejected.
- `COMMAND_ENVELOPE_07`: priority accepted.
- `COMMAND_ENVELOPE_08`: correlation propagation.
- `COMMAND_ENVELOPE_09`: causation propagation.
- `COMMAND_ENVELOPE_10`: attribute validation.
- `COMMAND_ENVELOPE_11`: duplicate command.
- `COMMAND_ENVELOPE_12`: expired command.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.4. Market Schema

Required cases:

- `MARKET_SCHEMA_01`: external ID uniqueness.
- `MARKET_SCHEMA_02`: positive payout.
- `MARKET_SCHEMA_03`: positive tick.
- `MARKET_SCHEMA_04`: positive quantity increment.
- `MARKET_SCHEMA_05`: close after open.
- `MARKET_SCHEMA_06`: resolve after close.
- `MARKET_SCHEMA_07`: unknown status policy.
- `MARKET_SCHEMA_08`: tag round trip.
- `MARKET_SCHEMA_09`: rules preservation.
- `MARKET_SCHEMA_10`: optional description.
- `MARKET_SCHEMA_11`: market update version.
- `MARKET_SCHEMA_12`: external ID mapping.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.5. Order Book

Required cases:

- `ORDER_BOOK_01`: sorted bids.
- `ORDER_BOOK_02`: sorted asks.
- `ORDER_BOOK_03`: duplicate bid aggregation.
- `ORDER_BOOK_04`: duplicate ask aggregation.
- `ORDER_BOOK_05`: zero level delete.
- `ORDER_BOOK_06`: negative quantity reject.
- `ORDER_BOOK_07`: crossed book policy.
- `ORDER_BOOK_08`: sequence increment.
- `ORDER_BOOK_09`: duplicate sequence.
- `ORDER_BOOK_10`: sequence gap.
- `ORDER_BOOK_11`: snapshot recovery.
- `ORDER_BOOK_12`: stale book flag.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.6. Trade Normalization

Required cases:

- `TRADE_NORMALIZATION_01`: exchange trade ID.
- `TRADE_NORMALIZATION_02`: positive quantity.
- `TRADE_NORMALIZATION_03`: exact price.
- `TRADE_NORMALIZATION_04`: UTC occurrence time.
- `TRADE_NORMALIZATION_05`: receive time.
- `TRADE_NORMALIZATION_06`: aggressor mapping.
- `TRADE_NORMALIZATION_07`: unknown liquidity role.
- `TRADE_NORMALIZATION_08`: duplicate trade.
- `TRADE_NORMALIZATION_09`: out-of-order trade.
- `TRADE_NORMALIZATION_10`: missing optional sequence.
- `TRADE_NORMALIZATION_11`: source event lineage.
- `TRADE_NORMALIZATION_12`: payload hash.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.7. Strategy Lifecycle

Required cases:

- `STRATEGY_LIFECYCLE_01`: create.
- `STRATEGY_LIFECYCLE_02`: initialize.
- `STRATEGY_LIFECYCLE_03`: start.
- `STRATEGY_LIFECYCLE_04`: event processing.
- `STRATEGY_LIFECYCLE_05`: degrade.
- `STRATEGY_LIFECYCLE_06`: drain.
- `STRATEGY_LIFECYCLE_07`: stop.
- `STRATEGY_LIFECYCLE_08`: restart.
- `STRATEGY_LIFECYCLE_09`: failure isolation.
- `STRATEGY_LIFECYCLE_10`: health transition.
- `STRATEGY_LIFECYCLE_11`: configuration change.
- `STRATEGY_LIFECYCLE_12`: shutdown cleanup.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.8. Signal Generation

Required cases:

- `SIGNAL_GENERATION_01`: buy signal.
- `SIGNAL_GENERATION_02`: sell signal.
- `SIGNAL_GENERATION_03`: neutral signal.
- `SIGNAL_GENERATION_04`: no signal.
- `SIGNAL_GENERATION_05`: expired signal.
- `SIGNAL_GENERATION_06`: confidence bounds.
- `SIGNAL_GENERATION_07`: fair probability bounds.
- `SIGNAL_GENERATION_08`: feature lineage.
- `SIGNAL_GENERATION_09`: model lineage.
- `SIGNAL_GENERATION_10`: reason code.
- `SIGNAL_GENERATION_11`: correlation ID.
- `SIGNAL_GENERATION_12`: deterministic repeat.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.9. Order Intent

Required cases:

- `ORDER_INTENT_01`: limit price required.
- `ORDER_INTENT_02`: market price optional.
- `ORDER_INTENT_03`: quantity positive.
- `ORDER_INTENT_04`: post-only market reject.
- `ORDER_INTENT_05`: expiry.
- `ORDER_INTENT_06`: signal lineage.
- `ORDER_INTENT_07`: idempotency key.
- `ORDER_INTENT_08`: strategy ownership.
- `ORDER_INTENT_09`: contract identity.
- `ORDER_INTENT_10`: side enum.
- `ORDER_INTENT_11`: urgency bounds.
- `ORDER_INTENT_12`: stable serialization.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.10. Order State Machine

Required cases:

- `ORDER_STATE_MACHINE_01`: created to risk pending.
- `ORDER_STATE_MACHINE_02`: risk pending to approved.
- `ORDER_STATE_MACHINE_03`: approved to submitting.
- `ORDER_STATE_MACHINE_04`: submitting to submitted.
- `ORDER_STATE_MACHINE_05`: submitted to accepted.
- `ORDER_STATE_MACHINE_06`: accepted to partial.
- `ORDER_STATE_MACHINE_07`: partial to filled.
- `ORDER_STATE_MACHINE_08`: accepted to cancel requested.
- `ORDER_STATE_MACHINE_09`: cancelling to cancelled.
- `ORDER_STATE_MACHINE_10`: rejected terminal.
- `ORDER_STATE_MACHINE_11`: expired terminal.
- `ORDER_STATE_MACHINE_12`: invalid terminal transition.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.11. Order Submission

Required cases:

- `ORDER_SUBMISSION_01`: approved order accepted.
- `ORDER_SUBMISSION_02`: unapproved rejected.
- `ORDER_SUBMISSION_03`: expired approval.
- `ORDER_SUBMISSION_04`: unsupported order type.
- `ORDER_SUBMISSION_05`: invalid precision.
- `ORDER_SUBMISSION_06`: duplicate client ID.
- `ORDER_SUBMISSION_07`: timeout before write.
- `ORDER_SUBMISSION_08`: timeout after possible write.
- `ORDER_SUBMISSION_09`: exchange rejection.
- `ORDER_SUBMISSION_10`: rate limit.
- `ORDER_SUBMISSION_11`: authentication failure.
- `ORDER_SUBMISSION_12`: audit lineage.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.12. Order Cancellation

Required cases:

- `ORDER_CANCELLATION_01`: accepted cancel.
- `ORDER_CANCELLATION_02`: partial cancel.
- `ORDER_CANCELLATION_03`: duplicate cancel.
- `ORDER_CANCELLATION_04`: cancel terminal order.
- `ORDER_CANCELLATION_05`: cancel unknown order.
- `ORDER_CANCELLATION_06`: cancel timeout.
- `ORDER_CANCELLATION_07`: cancel rejection.
- `ORDER_CANCELLATION_08`: fill before cancel.
- `ORDER_CANCELLATION_09`: fill during cancel.
- `ORDER_CANCELLATION_10`: full fill during cancel.
- `ORDER_CANCELLATION_11`: reconnect during cancel.
- `ORDER_CANCELLATION_12`: idempotent result.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.13. Fill Processing

Required cases:

- `FILL_PROCESSING_01`: first fill.
- `FILL_PROCESSING_02`: partial fill.
- `FILL_PROCESSING_03`: final fill.
- `FILL_PROCESSING_04`: duplicate fill.
- `FILL_PROCESSING_05`: unknown order.
- `FILL_PROCESSING_06`: price exactness.
- `FILL_PROCESSING_07`: fee exactness.
- `FILL_PROCESSING_08`: rebate exactness.
- `FILL_PROCESSING_09`: cumulative overfill.
- `FILL_PROCESSING_10`: out-of-order fill.
- `FILL_PROCESSING_11`: transaction rollback.
- `FILL_PROCESSING_12`: portfolio lineage.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.14. Position Accounting

Required cases:

- `POSITION_ACCOUNTING_01`: open long.
- `POSITION_ACCOUNTING_02`: add long.
- `POSITION_ACCOUNTING_03`: partial reduction.
- `POSITION_ACCOUNTING_04`: full close.
- `POSITION_ACCOUNTING_05`: reversal.
- `POSITION_ACCOUNTING_06`: average price.
- `POSITION_ACCOUNTING_07`: realized PnL.
- `POSITION_ACCOUNTING_08`: unrealized PnL.
- `POSITION_ACCOUNTING_09`: fee effect.
- `POSITION_ACCOUNTING_10`: rebate effect.
- `POSITION_ACCOUNTING_11`: duplicate fill.
- `POSITION_ACCOUNTING_12`: reconciliation correction.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.15. Cash Balance

Required cases:

- `CASH_BALANCE_01`: initial snapshot.
- `CASH_BALANCE_02`: available reserve identity.
- `CASH_BALANCE_03`: reservation.
- `CASH_BALANCE_04`: release.
- `CASH_BALANCE_05`: fill debit.
- `CASH_BALANCE_06`: settlement credit.
- `CASH_BALANCE_07`: fee debit.
- `CASH_BALANCE_08`: rebate credit.
- `CASH_BALANCE_09`: negative policy.
- `CASH_BALANCE_10`: duplicate update.
- `CASH_BALANCE_11`: stale snapshot.
- `CASH_BALANCE_12`: reconciliation mismatch.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.16. Journal Accounting

Required cases:

- `JOURNAL_ACCOUNTING_01`: balanced buy.
- `JOURNAL_ACCOUNTING_02`: balanced sell.
- `JOURNAL_ACCOUNTING_03`: balanced fee.
- `JOURNAL_ACCOUNTING_04`: balanced rebate.
- `JOURNAL_ACCOUNTING_05`: balanced settlement.
- `JOURNAL_ACCOUNTING_06`: balanced transfer.
- `JOURNAL_ACCOUNTING_07`: balanced correction.
- `JOURNAL_ACCOUNTING_08`: currency separation.
- `JOURNAL_ACCOUNTING_09`: duplicate source event.
- `JOURNAL_ACCOUNTING_10`: line numbering.
- `JOURNAL_ACCOUNTING_11`: reference lineage.
- `JOURNAL_ACCOUNTING_12`: rollback on imbalance.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.17. Risk Data Freshness

Required cases:

- `RISK_DATA_FRESHNESS_01`: below limit.
- `RISK_DATA_FRESHNESS_02`: equal limit.
- `RISK_DATA_FRESHNESS_03`: above limit.
- `RISK_DATA_FRESHNESS_04`: missing timestamp.
- `RISK_DATA_FRESHNESS_05`: future timestamp.
- `RISK_DATA_FRESHNESS_06`: clock unavailable.
- `RISK_DATA_FRESHNESS_07`: stale order book.
- `RISK_DATA_FRESHNESS_08`: stale portfolio.
- `RISK_DATA_FRESHNESS_09`: stale balance.
- `RISK_DATA_FRESHNESS_10`: stale reconciliation.
- `RISK_DATA_FRESHNESS_11`: stable reason code.
- `RISK_DATA_FRESHNESS_12`: exact age.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.18. Risk Exposure

Required cases:

- `RISK_EXPOSURE_01`: quantity below limit.
- `RISK_EXPOSURE_02`: quantity equal limit.
- `RISK_EXPOSURE_03`: quantity above limit.
- `RISK_EXPOSURE_04`: notional below limit.
- `RISK_EXPOSURE_05`: notional equal limit.
- `RISK_EXPOSURE_06`: notional above limit.
- `RISK_EXPOSURE_07`: position aggregation.
- `RISK_EXPOSURE_08`: open order aggregation.
- `RISK_EXPOSURE_09`: reservation aggregation.
- `RISK_EXPOSURE_10`: multi-strategy aggregation.
- `RISK_EXPOSURE_11`: multi-exchange aggregation.
- `RISK_EXPOSURE_12`: release capacity.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.19. Kill Switch

Required cases:

- `KILL_SWITCH_01`: global activate.
- `KILL_SWITCH_02`: exchange activate.
- `KILL_SWITCH_03`: account activate.
- `KILL_SWITCH_04`: strategy activate.
- `KILL_SWITCH_05`: market activate.
- `KILL_SWITCH_06`: duplicate activation.
- `KILL_SWITCH_07`: new intent blocked.
- `KILL_SWITCH_08`: existing cancel policy.
- `KILL_SWITCH_09`: release allowed.
- `KILL_SWITCH_10`: release denied.
- `KILL_SWITCH_11`: audit.
- `KILL_SWITCH_12`: event publication.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.20. Reconciliation

Required cases:

- `RECONCILIATION_01`: exact account match.
- `RECONCILIATION_02`: missing local order.
- `RECONCILIATION_03`: missing external order.
- `RECONCILIATION_04`: missing local fill.
- `RECONCILIATION_05`: duplicate local fill.
- `RECONCILIATION_06`: position mismatch.
- `RECONCILIATION_07`: balance mismatch.
- `RECONCILIATION_08`: manual activity.
- `RECONCILIATION_09`: settlement mismatch.
- `RECONCILIATION_10`: dependency failure.
- `RECONCILIATION_11`: trading gate hold.
- `RECONCILIATION_12`: trading gate release.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.21. Replay Manifest

Required cases:

- `REPLAY_MANIFEST_01`: dataset ID.
- `REPLAY_MANIFEST_02`: dataset checksum.
- `REPLAY_MANIFEST_03`: time range.
- `REPLAY_MANIFEST_04`: speed positive.
- `REPLAY_MANIFEST_05`: seed required.
- `REPLAY_MANIFEST_06`: ordering version.
- `REPLAY_MANIFEST_07`: strategy versions.
- `REPLAY_MANIFEST_08`: model versions.
- `REPLAY_MANIFEST_09`: configuration hash.
- `REPLAY_MANIFEST_10`: code commit.
- `REPLAY_MANIFEST_11`: lock hash.
- `REPLAY_MANIFEST_12`: creator metadata.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.22. Replay Engine

Required cases:

- `REPLAY_ENGINE_01`: load events.
- `REPLAY_ENGINE_02`: stable sort.
- `REPLAY_ENGINE_03`: clock advance.
- `REPLAY_ENGINE_04`: pause.
- `REPLAY_ENGINE_05`: resume.
- `REPLAY_ENGINE_06`: seek.
- `REPLAY_ENGINE_07`: cancel.
- `REPLAY_ENGINE_08`: filter.
- `REPLAY_ENGINE_09`: fault injection.
- `REPLAY_ENGINE_10`: no network.
- `REPLAY_ENGINE_11`: no live gateway.
- `REPLAY_ENGINE_12`: result checksum.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.23. Simulation Fill Model

Required cases:

- `SIMULATION_FILL_MODEL_01`: marketable limit.
- `SIMULATION_FILL_MODEL_02`: passive no fill.
- `SIMULATION_FILL_MODEL_03`: passive partial.
- `SIMULATION_FILL_MODEL_04`: passive full.
- `SIMULATION_FILL_MODEL_05`: trade-through.
- `SIMULATION_FILL_MODEL_06`: touch fill.
- `SIMULATION_FILL_MODEL_07`: queue ahead.
- `SIMULATION_FILL_MODEL_08`: latency activation.
- `SIMULATION_FILL_MODEL_09`: cancel race.
- `SIMULATION_FILL_MODEL_10`: fee calculation.
- `SIMULATION_FILL_MODEL_11`: slippage.
- `SIMULATION_FILL_MODEL_12`: deterministic seed.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.24. Matching Pipeline

Required cases:

- `MATCHING_PIPELINE_01`: metadata candidate.
- `MATCHING_PIPELINE_02`: entity extraction.
- `MATCHING_PIPELINE_03`: date extraction.
- `MATCHING_PIPELINE_04`: threshold extraction.
- `MATCHING_PIPELINE_05`: embedding score.
- `MATCHING_PIPELINE_06`: LLM structure.
- `MATCHING_PIPELINE_07`: deterministic validation.
- `MATCHING_PIPELINE_08`: settlement mismatch.
- `MATCHING_PIPELINE_09`: ambiguous rules.
- `MATCHING_PIPELINE_10`: human review.
- `MATCHING_PIPELINE_11`: approval.
- `MATCHING_PIPELINE_12`: rejection.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.25. Arbitrage Detection

Required cases:

- `ARBITRAGE_DETECTION_01`: equivalent markets.
- `ARBITRAGE_DETECTION_02`: complement markets.
- `ARBITRAGE_DETECTION_03`: gross edge.
- `ARBITRAGE_DETECTION_04`: fee deduction.
- `ARBITRAGE_DETECTION_05`: slippage deduction.
- `ARBITRAGE_DETECTION_06`: net edge.
- `ARBITRAGE_DETECTION_07`: stale quote.
- `ARBITRAGE_DETECTION_08`: insufficient capital.
- `ARBITRAGE_DETECTION_09`: relationship unapproved.
- `ARBITRAGE_DETECTION_10`: settlement mismatch.
- `ARBITRAGE_DETECTION_11`: opportunity expiry.
- `ARBITRAGE_DETECTION_12`: deterministic calculation.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.26. Arbitrage Execution

Required cases:

- `ARBITRAGE_EXECUTION_01`: reserve capital.
- `ARBITRAGE_EXECUTION_02`: submit both legs.
- `ARBITRAGE_EXECUTION_03`: first leg rejection.
- `ARBITRAGE_EXECUTION_04`: second leg rejection.
- `ARBITRAGE_EXECUTION_05`: partial first leg.
- `ARBITRAGE_EXECUTION_06`: partial second leg.
- `ARBITRAGE_EXECUTION_07`: hedge timeout.
- `ARBITRAGE_EXECUTION_08`: disconnect.
- `ARBITRAGE_EXECUTION_09`: kill switch.
- `ARBITRAGE_EXECUTION_10`: duplicate fill.
- `ARBITRAGE_EXECUTION_11`: release reservation.
- `ARBITRAGE_EXECUTION_12`: recovery audit.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.27. API Authentication

Required cases:

- `API_AUTHENTICATION_01`: missing token.
- `API_AUTHENTICATION_02`: malformed token.
- `API_AUTHENTICATION_03`: expired token.
- `API_AUTHENTICATION_04`: wrong issuer.
- `API_AUTHENTICATION_05`: wrong audience.
- `API_AUTHENTICATION_06`: wrong environment.
- `API_AUTHENTICATION_07`: revoked token.
- `API_AUTHENTICATION_08`: viewer token.
- `API_AUTHENTICATION_09`: operator token.
- `API_AUTHENTICATION_10`: service token.
- `API_AUTHENTICATION_11`: token redaction.
- `API_AUTHENTICATION_12`: authentication metric.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.28. API Authorization

Required cases:

- `API_AUTHORIZATION_01`: viewer read.
- `API_AUTHORIZATION_02`: viewer mutation denied.
- `API_AUTHORIZATION_03`: strategy control allowed.
- `API_AUTHORIZATION_04`: risk control allowed.
- `API_AUTHORIZATION_05`: admin allowed.
- `API_AUTHORIZATION_06`: wrong account denied.
- `API_AUTHORIZATION_07`: wrong environment denied.
- `API_AUTHORIZATION_08`: scope missing.
- `API_AUTHORIZATION_09`: audit actor.
- `API_AUTHORIZATION_10`: confidential redaction.
- `API_AUTHORIZATION_11`: dual approval.
- `API_AUTHORIZATION_12`: authorization metric.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.29. API Pagination

Required cases:

- `API_PAGINATION_01`: default limit.
- `API_PAGINATION_02`: custom limit.
- `API_PAGINATION_03`: max limit.
- `API_PAGINATION_04`: first cursor.
- `API_PAGINATION_05`: next cursor.
- `API_PAGINATION_06`: invalid cursor.
- `API_PAGINATION_07`: expired cursor.
- `API_PAGINATION_08`: filter mismatch.
- `API_PAGINATION_09`: stable tie-break.
- `API_PAGINATION_10`: no duplicate.
- `API_PAGINATION_11`: empty page.
- `API_PAGINATION_12`: concurrent insert policy.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.30. API Idempotency

Required cases:

- `API_IDEMPOTENCY_01`: first request.
- `API_IDEMPOTENCY_02`: same key same body.
- `API_IDEMPOTENCY_03`: same key changed body.
- `API_IDEMPOTENCY_04`: concurrent duplicate.
- `API_IDEMPOTENCY_05`: different subject.
- `API_IDEMPOTENCY_06`: different endpoint.
- `API_IDEMPOTENCY_07`: in-progress request.
- `API_IDEMPOTENCY_08`: completed request.
- `API_IDEMPOTENCY_09`: failed request policy.
- `API_IDEMPOTENCY_10`: expiry.
- `API_IDEMPOTENCY_11`: restart persistence.
- `API_IDEMPOTENCY_12`: audit key.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.31. WebSocket Streaming

Required cases:

- `WEBSOCKET_STREAMING_01`: hello.
- `WEBSOCKET_STREAMING_02`: authorized subscribe.
- `WEBSOCKET_STREAMING_03`: forbidden subscribe.
- `WEBSOCKET_STREAMING_04`: multiple channels.
- `WEBSOCKET_STREAMING_05`: event sequence.
- `WEBSOCKET_STREAMING_06`: unsubscribe.
- `WEBSOCKET_STREAMING_07`: heartbeat.
- `WEBSOCKET_STREAMING_08`: missed heartbeat.
- `WEBSOCKET_STREAMING_09`: slow consumer.
- `WEBSOCKET_STREAMING_10`: gap recovery.
- `WEBSOCKET_STREAMING_11`: server shutdown.
- `WEBSOCKET_STREAMING_12`: reconnect.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.32. Database Migration

Required cases:

- `DATABASE_MIGRATION_01`: empty upgrade.
- `DATABASE_MIGRATION_02`: previous upgrade.
- `DATABASE_MIGRATION_03`: constraint creation.
- `DATABASE_MIGRATION_04`: index creation.
- `DATABASE_MIGRATION_05`: partition creation.
- `DATABASE_MIGRATION_06`: representative insert.
- `DATABASE_MIGRATION_07`: downgrade supported.
- `DATABASE_MIGRATION_08`: re-upgrade.
- `DATABASE_MIGRATION_09`: long-lock review.
- `DATABASE_MIGRATION_10`: backfill resume.
- `DATABASE_MIGRATION_11`: metadata alignment.
- `DATABASE_MIGRATION_12`: revision validation.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.33. Outbox Delivery

Required cases:

- `OUTBOX_DELIVERY_01`: insert with state.
- `OUTBOX_DELIVERY_02`: pending claim.
- `OUTBOX_DELIVERY_03`: SKIP LOCKED.
- `OUTBOX_DELIVERY_04`: publish success.
- `OUTBOX_DELIVERY_05`: publish failure.
- `OUTBOX_DELIVERY_06`: backoff.
- `OUTBOX_DELIVERY_07`: duplicate event topic.
- `OUTBOX_DELIVERY_08`: worker crash.
- `OUTBOX_DELIVERY_09`: restart.
- `OUTBOX_DELIVERY_10`: oldest backlog.
- `OUTBOX_DELIVERY_11`: dead letter threshold.
- `OUTBOX_DELIVERY_12`: payload exactness.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.34. Security Redaction

Required cases:

- `SECURITY_REDACTION_01`: authorization header.
- `SECURITY_REDACTION_02`: API key.
- `SECURITY_REDACTION_03`: private key.
- `SECURITY_REDACTION_04`: database URL.
- `SECURITY_REDACTION_05`: cookie.
- `SECURITY_REDACTION_06`: nested token.
- `SECURITY_REDACTION_07`: query string secret.
- `SECURITY_REDACTION_08`: exception message.
- `SECURITY_REDACTION_09`: structured log.
- `SECURITY_REDACTION_10`: trace attribute.
- `SECURITY_REDACTION_11`: audit payload.
- `SECURITY_REDACTION_12`: test snapshot.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

## A.35. Operational Recovery

Required cases:

- `OPERATIONAL_RECOVERY_01`: adapter disconnect.
- `OPERATIONAL_RECOVERY_02`: database outage.
- `OPERATIONAL_RECOVERY_03`: database failover.
- `OPERATIONAL_RECOVERY_04`: sequence gap storm.
- `OPERATIONAL_RECOVERY_05`: unknown order.
- `OPERATIONAL_RECOVERY_06`: missing fill.
- `OPERATIONAL_RECOVERY_07`: portfolio mismatch.
- `OPERATIONAL_RECOVERY_08`: disk pressure.
- `OPERATIONAL_RECOVERY_09`: outbox backlog.
- `OPERATIONAL_RECOVERY_10`: bad deployment.
- `OPERATIONAL_RECOVERY_11`: credential rotation.
- `OPERATIONAL_RECOVERY_12`: restore and reconcile.

Acceptance rules:

- The case has a descriptive test name.
- Inputs and expected outputs are explicit.
- Time and randomness are controlled.
- Failure output includes stable error or reason codes where applicable.
- The case is deterministic in local and CI execution.

# Appendix B. CI Failure Triage

## B.1. Formatting failure

Primary action: run Ruff formatter; do not hand-format around the tool.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.2. Lint failure

Primary action: fix the underlying issue or add a narrow documented suppression.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.3. Type failure

Primary action: restore the declared interface rather than using broad Any.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.4. Unit failure

Primary action: reproduce locally with the exact node ID.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.5. Property failure

Primary action: preserve the minimized failing example and seed.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.6. Database failure

Primary action: inspect migration revision, transaction rollback, and PostgreSQL logs.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.7. Contract failure

Primary action: compare adapter capability and fixture assumptions.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.8. Replay failure

Primary action: compare event order, clock, seed, and checksum inputs.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.9. Simulation failure

Primary action: compare model version, configuration, and seed.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.10. API failure

Primary action: inspect response schema, authorization, and idempotency state.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.11. Security failure

Primary action: treat exposed credentials or authorization bypass as blocking.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

## B.12. Performance regression

Primary action: confirm environment and compare against baseline distribution.

Required evidence: failing command, commit, environment, relevant logs, fixture or dataset identifier, and owner.

# Appendix C. Release Test Sign-Off

```text
Release:
Commit:
Dependency lock hash:
Schema revision:
Test owner:

[ ] Formatting passed.
[ ] Linting passed.
[ ] Type checking passed.
[ ] Unit and property tests passed.
[ ] Database and migration tests passed.
[ ] Adapter contracts passed.
[ ] API tests passed.
[ ] Replay checksums were reviewed.
[ ] Simulation scenarios passed.
[ ] Risk and portfolio tests passed.
[ ] Security scans were triaged.
[ ] Performance impact was reviewed.
[ ] Operational drills required for this release passed.
[ ] Known limitations are documented.
[ ] Release is approved.
```
