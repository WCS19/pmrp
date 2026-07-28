# Prediction Market Research Platform

## Engineering Standards and Development Handbook

- Document: `02_ENGINEERING.md`
- Version: 1.0
- Status: Governing engineering specification
- Related document: `01_ARCHITECTURE.md`
- Primary language: Python 3.13
- Package manager: uv
- Character set: ASCII only
- Intended audience: maintainers, contributors, quantitative researchers, reviewers, operators, and coding agents

---

## Document Authority

This document defines the engineering standards for the Prediction Market
Research Platform, abbreviated as PMRP.

It describes how the architecture in `01_ARCHITECTURE.md` shall be implemented,
tested, reviewed, released, operated, and maintained.

This document is normative. The terms MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT,
SHOULD, SHOULD NOT, and MAY are used in their ordinary engineering sense.

When this document conflicts with an approved Architecture Decision Record, the
newer approved decision governs. The conflicting section of this document
should then be updated in the same pull request.

The engineering goal is not merely to produce working code. The goal is to
produce code that remains understandable, testable, reproducible, observable,
and safe as the platform grows from research to live execution.

---

# 1. Executive Summary

PMRP is a financial research and trading platform. Engineering errors can affect
research validity, simulated results, live orders, balances, and capital.

The engineering approach therefore emphasizes:

- explicit contracts
- deterministic behavior
- strong typing
- exact numeric handling
- bounded concurrency
- reproducible environments
- comprehensive testing
- auditable changes
- conservative failure behavior
- incremental delivery
- operational readiness

The initial implementation is Python-first.

Python is selected because it provides the strongest combination of:

- research velocity
- scientific computing libraries
- statistical tooling
- machine learning tooling
- developer accessibility
- rapid iteration
- coding-agent compatibility
- production-capable asynchronous I/O

Python is not assumed to be the final language for every high-throughput
infrastructure component.

If measured bottlenecks justify a rewrite, isolated services such as an exchange
gateway, order gateway, or event router may later be implemented in Go or Rust.
The research, strategy, replay, simulation, analytics, and model layers should
remain in Python unless profiling and operational evidence justify otherwise.

The project shall use:

- Python 3.13
- uv for dependency and environment management
- `pyproject.toml` as the primary project configuration file
- `uv.lock` as the committed dependency lock
- Ruff for formatting and linting
- mypy for static type checking
- pytest for tests
- pytest-asyncio for asynchronous tests
- pytest-cov and coverage.py for coverage
- Hypothesis for property-based testing
- Pydantic for runtime validation at system boundaries
- Decimal for financial values
- structured logging
- pre-commit hooks
- automated continuous integration

No single metric, including code coverage, replaces sound design and review.


# 2. Engineering Objectives

## 2.1 Correctness

The system shall prefer a correct, explainable implementation over a clever,
fragile implementation.

Correctness includes:

- valid domain transitions
- exact arithmetic
- deterministic replay
- idempotent event handling
- correct time semantics
- complete accounting
- safe error handling
- explicit assumptions

## 2.2 Reproducibility

A contributor shall be able to reproduce:

- the dependency environment
- a replay result
- a simulation result
- a model prediction
- a test failure
- a release artifact

Reproducibility requires pinned dependencies, stable datasets, configuration
hashes, random seeds, code revisions, and recorded schema versions.

## 2.3 Maintainability

A new contributor should be able to identify:

- where a responsibility belongs
- which interface to implement
- which tests are required
- which commands validate a change
- which component owns a state transition
- which documentation governs behavior

## 2.4 Safety

The engineering system shall make unsafe behavior difficult.

Examples:

- live mode is disabled by default
- credentials are separated by environment
- order flow is risk checked
- secrets are redacted
- stale state blocks trading
- database migrations are reviewed
- order and fill processing are idempotent
- dangerous operator actions are audited

## 2.5 Observability

Components shall expose sufficient information to diagnose:

- what happened
- when it happened
- why it happened
- which inputs were involved
- which version produced the behavior
- whether trading safety was affected

## 2.6 Delivery Speed

The standards should improve delivery speed by reducing ambiguity and
regressions.

The project should avoid process for its own sake. Every required artifact,
check, or review step should protect correctness, safety, maintainability, or
reproducibility.


# 3. Scope and Non-Scope

This document governs:

- source code
- tests
- dependency management
- configuration
- database migrations
- command-line tools
- containers
- continuous integration
- releases
- logging
- metrics
- security hygiene
- documentation
- code review
- contribution workflow
- operational readiness

This document does not define:

- individual strategy profitability
- model-selection policy
- legal eligibility to trade
- exchange-specific business rules
- production capital limits
- tax treatment
- final cloud-provider selection

Those topics belong in strategy, compliance, operations, or deployment
documents.


# 4. Normative Engineering Principles

## 4.1 Make Illegal States Difficult to Represent

Use explicit types, enums, constructors, and validators.

Avoid generic dictionaries for schema-defined business objects.

Prefer:

```python
order.side
order.quantity
order.limit_price
```

over:

```python
order["side"]
order["qty"]
order["px"]
```

## 4.2 Separate Pure Logic from Side Effects

Business calculations should be pure functions where practical.

Network calls, database writes, clock reads, file writes, and message
publication belong behind interfaces.

## 4.3 Depend on Abstractions

Application and domain code depend on protocols or abstract interfaces.

Concrete exchange clients, SQLAlchemy sessions, and HTTP clients stay in the
infrastructure layer.

## 4.4 Validate at Boundaries

Validate external data when it enters the platform.

Examples:

- exchange payload
- operator command
- configuration
- database row converted to a domain model
- model artifact metadata
- replay manifest

Internal functions should receive already validated types whenever practical.

## 4.5 Fail Closed for Live Side Effects

If required data, risk state, or reconciliation state is uncertain, block live
orders.

Do not silently assume that missing state is safe.

## 4.6 Prefer Explicitness

Prefer explicit constructor arguments, named types, named result objects, and
documented state transitions.

Avoid hidden globals and implicit environment reads.

## 4.7 Optimize After Measurement

Do not introduce concurrency, caching, binary serialization, a broker, or a
language rewrite without evidence.

Measure before and after every performance change.

## 4.8 Preserve Evidence

Errors and corrections must preserve enough context for diagnosis.

Do not discard raw payloads or overwrite immutable audit events.

## 4.9 Keep Changes Reviewable

Prefer focused pull requests that make one coherent change.

Large mechanical changes should be separated from behavior changes when
possible.

## 4.10 Treat Tests as Product Code

Tests shall be readable, deterministic, maintained, and reviewed.


# 5. Language and Runtime Standard

## 5.1 Python Version

The project shall target Python 3.13.

The version shall be pinned in:

```text
.python-version
pyproject.toml
continuous-integration configuration
container images
```

Example `.python-version`:

```text
3.13
```

Example `pyproject.toml` requirement:

```toml
[project]
requires-python = ">=3.13,<3.14"
```

A future Python upgrade requires:

- an approved change
- dependency compatibility verification
- full test execution
- replay checksum review
- performance comparison
- documentation update

## 5.2 Interpreter Assumptions

Code shall not depend on implementation details that are unique to a local
interpreter build.

The supported production interpreter is CPython unless an ADR approves another
runtime.

## 5.3 Standard Library Preference

Use the standard library when it provides a clear, maintained solution.

Do not add a dependency for trivial functionality.

However, do not reimplement mature functionality merely to avoid a justified
dependency.


# 6. Dependency and Environment Management

## 6.1 Package Manager

Use uv.

Do not use Poetry, Pipenv, Conda, or manually maintained `requirements.txt`
files as the primary project dependency system.

## 6.2 Source of Truth

The dependency source of truth is:

```text
pyproject.toml
uv.lock
```

The lock file shall be committed.

## 6.3 Common Commands

Create or synchronize the environment:

```bash
uv sync --locked
```

Synchronize all development groups:

```bash
uv sync --locked --all-groups
```

Run a command:

```bash
uv run pytest
```

Add a runtime dependency:

```bash
uv add package-name
```

Add a development dependency:

```bash
uv add --group dev package-name
```

Upgrade a selected dependency:

```bash
uv lock --upgrade-package package-name
```

## 6.4 Dependency Groups

Recommended groups:

- dev
- test
- lint
- docs
- notebooks
- optional infrastructure integrations

Example:

```toml
[dependency-groups]
dev = [
  "pre-commit",
  "ruff",
  "mypy",
]
test = [
  "pytest",
  "pytest-asyncio",
  "pytest-cov",
  "pytest-mock",
  "hypothesis",
]
```

## 6.5 Lock Discipline

CI and production builds shall use `--locked`.

A pull request that changes declared dependencies shall include the updated
lock file.

A lock-file-only change should explain why it is required.

## 6.6 Dependency Selection Criteria

Before adding a dependency, evaluate:

- active maintenance
- license compatibility
- security history
- type annotations
- API stability
- transitive dependency size
- release cadence
- Python 3.13 support
- operational complexity
- whether the standard library is sufficient

## 6.7 Dependency Removal

Remove unused dependencies promptly.

Unused dependencies increase:

- supply-chain exposure
- environment resolution time
- image size
- compatibility risk
- reviewer uncertainty


# 7. Recommended Dependency Baseline

The baseline may include the following categories.

Runtime:

- pydantic
- pydantic-settings
- httpx
- websockets
- sqlalchemy
- alembic
- asyncpg
- orjson
- structlog
- tenacity
- numpy
- pandas
- scipy
- scikit-learn

Development:

- pytest
- pytest-asyncio
- pytest-cov
- pytest-mock
- hypothesis
- ruff
- mypy
- pre-commit

Optional infrastructure:

- redis
- aiokafka
- prometheus-client
- opentelemetry-api
- opentelemetry-sdk

Dependencies should not be added merely because they appear in this list.

Each package should be added only when the implementation uses it.


# 8. Project Configuration

`pyproject.toml` shall contain central configuration for:

- build metadata
- Python requirement
- dependency groups
- Ruff
- mypy
- pytest
- coverage
- packaging

Avoid duplicating configuration across multiple files when the tool supports
`pyproject.toml`.

Exceptions are allowed when a tool's native file is clearer or required.

The project shall use the `src` layout:

```text
src/
  pmrp/
```

This prevents accidental imports from the repository working directory and
improves packaging correctness.


# 9. Repository Conventions

## 9.1 Top-Level Layout

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
+-- data/
+-- pyproject.toml
+-- uv.lock
+-- .python-version
+-- .pre-commit-config.yaml
+-- README.md
+-- CONTRIBUTING.md
+-- SECURITY.md
+-- LICENSE
```

## 9.2 Package Naming

Use lowercase snake_case for Python modules and packages.

Use descriptive names.

Avoid abbreviations unless they are standard domain terms.

Good:

```text
order_state_machine.py
portfolio_reconciliation.py
market_data_subscription.py
```

Avoid:

```text
osm.py
recon2.py
utils_new.py
helpers_misc.py
```

## 9.3 Test Mirroring

Unit tests should approximately mirror the source layout.

Example:

```text
src/pmrp/execution/order_state_machine.py
tests/unit/execution/test_order_state_machine.py
```

## 9.4 General Utility Modules

Avoid broad `utils.py` modules.

Place functions in the package that owns the concept.

If a utility is genuinely cross-cutting, give it a precise name such as:

- decimal_math.py
- time_parsing.py
- id_generation.py
- secret_redaction.py


# 10. Module and Package Boundaries

## 10.1 Domain Layer

May depend on:

- Python standard library
- lightweight validation types where approved

Must not depend on:

- HTTP clients
- WebSocket clients
- SQLAlchemy
- cloud SDKs
- exchange SDKs
- CLI frameworks
- monitoring exporters

## 10.2 Application Layer

Coordinates domain services and interfaces.

May depend on:

- domain
- protocols
- command and event definitions

Should not contain exchange payload parsing.

## 10.3 Infrastructure Layer

Implements:

- database repositories
- exchange clients
- message buses
- secret providers
- monitoring exporters
- file stores

## 10.4 Strategy Layer

May depend on:

- canonical domain models
- strategy interfaces
- feature interfaces
- model interfaces
- approved math libraries

Must not depend on:

- concrete exchange adapters
- database sessions
- environment variables
- secret providers
- raw exchange payloads

## 10.5 Enforcing Boundaries

Boundary rules should be checked through:

- code review
- import-lint tooling if adopted
- architectural tests
- package design

Example architectural test concept:

```python
def test_strategies_do_not_import_exchange_adapters() -> None:
    ...
```


# 11. Source File Standards

## 11.1 File Size

There is no absolute line limit.

A file should represent one coherent responsibility.

Consider splitting a file when:

- unrelated concepts coexist
- testing requires excessive setup
- navigation becomes difficult
- classes exist only to support separate responsibilities
- change conflicts occur frequently
- the public interface is unclear

## 11.2 Public API

Each package should expose a deliberate public API.

Avoid importing every internal symbol from `__init__.py`.

Prefer explicit imports from stable modules.

## 11.3 Module Docstrings

Use module docstrings when the module's purpose, invariants, or operational
behavior is not obvious from its name.

Do not add empty boilerplate docstrings.

## 11.4 Import Order

Ruff shall organize imports into:

1. standard library
2. third-party packages
3. local project packages

## 11.5 Wildcard Imports

Wildcard imports are prohibited.

## 11.6 Circular Imports

Circular imports indicate a boundary problem.

Resolve them by:

- moving shared types to a lower-level module
- using protocols
- extracting an interface
- changing ownership

Do not hide circular imports with local imports unless the import is genuinely
runtime-conditional and documented.


# 12. Naming Standards

## 12.1 Classes

Use PascalCase.

Examples:

- ReplayClock
- OrderStateMachine
- KalshiMarketDataAdapter
- PortfolioReconciler

## 12.2 Functions and Variables

Use snake_case.

Examples:

- calculate_fair_probability
- remaining_quantity
- reconciliation_result

## 12.3 Constants

Use uppercase snake case.

Examples:

- DEFAULT_REPLAY_SPEED
- MAX_SCHEMA_VERSION
- ZERO_MONEY

## 12.4 Protocols

Use domain names, optionally with a descriptive suffix.

Examples:

- Clock
- EventBus
- OrderRepository
- ExchangeAdapter
- RiskPolicy

Avoid prefixing protocols with `I`.

## 12.5 Boolean Names

Boolean names should read as predicates.

Good:

- is_live
- has_sequence_gap
- can_submit
- should_cancel

Avoid:

- live_flag
- status
- check

## 12.6 Units in Names

Include units when the type does not encode them.

Examples:

- timeout_seconds
- latency_ms
- notional_usd

Prefer typed durations and money values when practical.


# 13. Type Safety

## 13.1 General Rule

All production functions and methods shall have type annotations.

Public APIs require complete annotations.

Tests should also use annotations when they improve clarity.

## 13.2 Static Checker

Use mypy in strict or near-strict mode.

Initial configuration may introduce targeted exceptions while legacy or
third-party boundaries are stabilized.

Exceptions must be narrow and documented.

## 13.3 Avoid Any

`Any` should be confined to untyped external boundaries.

Convert unknown data into validated models promptly.

Do not use `Any` to silence design problems.

## 13.4 Typed Collections

Prefer precise types.

Good:

```python
Sequence[OrderBookLevel]
Mapping[str, Decimal]
AsyncIterator[CanonicalEvent]
```

Avoid:

```python
list
dict
object
```

when a more precise type is known.

## 13.5 NewType and Value Objects

Use value objects or `NewType` to prevent identifier confusion.

Example:

```python
from typing import NewType

OrderId = NewType("OrderId", str)
MarketId = NewType("MarketId", str)
StrategyId = NewType("StrategyId", str)
```

For values with invariants, prefer a dataclass or Pydantic type.

## 13.6 Optional Values

Use `T | None`.

Do not use sentinel strings such as `"N/A"` to represent missing typed values.

## 13.7 Type Ignores

A `# type: ignore` comment shall include an error code when supported.

Example:

```python
result = library_call()  # type: ignore[no-untyped-call]
```

Each ignore should be explainable in review.


# 14. Runtime Validation and Pydantic

## 14.1 Use Cases

Use Pydantic for:

- external API payloads
- configuration
- event envelopes
- command envelopes
- operator API requests
- persisted JSON schemas
- model artifact metadata

## 14.2 Frozen Models

Canonical events should be immutable.

Example:

```python
from pydantic import BaseModel, ConfigDict


class CanonicalEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
```

## 14.3 Strictness

Prefer strict validation at external boundaries.

Do not silently coerce dangerous values such as:

- malformed prices
- invalid timestamps
- unexpected enum strings
- negative quantities
- nonintegral sequence numbers

## 14.4 Validation Errors

Validation errors should be:

- classified
- logged with redaction
- measured
- retained in dead-letter storage when appropriate

## 14.5 Domain Types Versus Transport Models

Transport models describe external payloads.

Domain models describe internal meaning.

Do not reuse raw transport models as canonical domain objects.


# 15. Dataclasses, Pydantic Models, and Plain Classes

Use frozen dataclasses for small internal immutable value objects.

Use Pydantic models when runtime parsing, serialization, or schema generation is
required.

Use plain classes for stateful services and aggregates with behavior.

Decision guide:

```text
Need external parsing or JSON schema?
  yes -> Pydantic

Need a small immutable internal value?
  yes -> frozen dataclass

Need lifecycle, state, or services?
  yes -> plain class
```

Avoid classes that contain only fields and no invariants if a dataclass or
Pydantic model is clearer.


# 16. Financial Numeric Standards

## 16.1 Decimal Requirement

Use `Decimal` for:

- prices
- probabilities represented as exact decimal values
- quantities when fractional contracts are possible
- money
- fees
- rebates
- PnL
- balances
- notional exposure

Do not use `float` for accounting or order values.

## 16.2 Decimal Construction

Construct Decimal values from strings or integers.

Good:

```python
Decimal("0.15")
Decimal(15) / Decimal(100)
```

Avoid:

```python
Decimal(0.15)
```

because the float has already introduced binary approximation.

## 16.3 Decimal Context

Do not change the global Decimal context in arbitrary modules.

Define explicit quantization and rounding functions.

## 16.4 Rounding

Rounding rules are exchange-specific and must be applied at adapter boundaries.

Examples:

- tick-size rounding
- fee rounding
- payout rounding
- minimum quantity rounding

A rounding function shall state:

- input unit
- output unit
- increment
- rounding mode

## 16.5 Invariants

Test:

- price bounds
- probability bounds
- nonnegative quantity
- fill quantity limits
- fee signs
- PnL reconciliation
- exact round trips through serialization


# 17. Time and Clock Standards

## 17.1 UTC

Persist timestamps in UTC.

Use timezone-aware `datetime` objects.

Naive datetimes are prohibited in production code.

## 17.2 Injected Clock

Domain, strategy, replay, simulation, execution timeout, and risk code must use
an injected clock interface.

Direct calls to:

```python
datetime.now()
datetime.utcnow()
time.time()
asyncio.sleep()
```

are prohibited outside approved clock and scheduling infrastructure.

## 17.3 Timestamp Semantics

Field names must identify meaning.

Examples:

- exchange_occurred_at
- received_at
- normalized_at
- published_at
- submitted_at
- acknowledged_at
- filled_at
- settled_at

Avoid generic fields named `timestamp` in complex schemas unless the event
envelope defines the meaning.

## 17.4 Durations

Prefer `timedelta` for in-process duration values.

Configuration may use explicit unit names such as:

- timeout_seconds
- refresh_interval_ms

## 17.5 Monotonic Time

Use a monotonic clock for elapsed-duration measurement.

Wall-clock timestamps remain necessary for audit records.


# 18. Identifier Standards

Identifiers should be opaque and immutable.

Recommended internal identifiers:

- UUIDv7
- ULID
- prefixed ULID

Prefixes improve operational readability.

Examples:

```text
evt_
cmd_
ord_
fill_
mkt_
strat_
rpl_
exp_
```

Do not encode mutable business information into identifiers.

External exchange identifiers should be stored separately.

Every event shall carry correlation and causation identifiers according to the
architecture specification.


# 19. Enumerations and State Machines

Use enums for closed business vocabularies.

Examples:

- OrderSide
- OrderStatus
- MarketStatus
- RiskDecisionStatus
- StrategyLifecycleState

Enum values persisted externally must be stable lowercase strings.

Do not rely on enum member order.

State transitions must be implemented through one explicit state machine or
aggregate method.

Avoid arbitrary status assignment.

Good:

```python
order.apply_acceptance(event)
```

Avoid:

```python
order.status = OrderStatus.ACCEPTED
```

State-machine tests shall cover every valid and invalid transition.


# 20. Function and Class Design

## 20.1 Functions

A function should do one conceptual job.

Prefer functions with few parameters.

When many related parameters are required, introduce a request or context type.

## 20.2 Return Types

Use explicit result objects for operations with multiple outcomes.

Example:

```python
@dataclass(frozen=True)
class RiskEvaluation:
    approved: bool
    reasons: tuple[RiskReason, ...]
    calculated_notional: Decimal
```

## 20.3 Exceptions Versus Results

Use exceptions for unexpected failures.

Use typed result objects for expected business outcomes.

Examples of expected outcomes:

- risk rejection
- order validation rejection
- market closed
- unsupported capability

Examples of exceptional outcomes:

- corrupted persisted state
- database driver failure
- impossible state transition
- programming invariant violation

## 20.4 Constructors

Constructors should establish valid state.

Avoid objects that require a sequence of undocumented setter calls before use.

## 20.5 Inheritance

Prefer composition and protocols.

Use inheritance only for a genuine subtype relationship.

Deep inheritance trees are prohibited.


# 21. Asynchronous Programming

## 21.1 Async Boundary

Use async for I/O-bound operations:

- HTTP
- WebSocket
- database access
- message publication
- file or object-store access where supported

Do not make pure calculations async.

## 21.2 Structured Concurrency

Tasks should have an owner and lifecycle.

Avoid untracked `asyncio.create_task()` calls.

Use task groups or managed task registries.

## 21.3 Cancellation

Components shall handle cancellation explicitly.

On cancellation:

- stop accepting new work
- finish or safely abort current work
- flush required buffers
- close connections
- persist critical state
- emit shutdown health information

## 21.4 Timeouts

All external I/O requires timeouts.

Timeouts should be configuration values with safe defaults.

## 21.5 Bounded Queues

Async queues must be bounded.

Queue saturation must be observable and handled according to criticality.

## 21.6 Locks

Minimize shared mutable state.

When a lock is necessary:

- keep the critical section small
- never perform slow network I/O while holding it
- document the protected invariant
- test cancellation behavior

## 21.7 CPU-Bound Work

CPU-heavy feature generation or model inference should not block the event loop.

Options:

- batch efficiently
- use optimized numerical libraries
- use worker processes
- use a separate model service when justified


# 22. Concurrency Safety

Each mutable aggregate must have a single logical owner or serialized update
path.

Examples:

- one order state machine owns an order
- one portfolio projection applies fills for an account partition
- one order-book builder applies deltas for a market partition

Do not update the same state from unrelated tasks without explicit
synchronization.

Use partition keys to preserve ordering.

Concurrency tests should include:

- duplicate events
- reordered events
- cancellation during I/O
- simultaneous fill and cancel
- reconnect during reconciliation
- queue saturation


# 23. Error Taxonomy

Define a project exception hierarchy.

Example:

```text
PmrpError
|
+-- ConfigurationError
+-- ValidationError
+-- AdapterError
|   +-- AuthenticationError
|   +-- RateLimitError
|   +-- TransportError
|   +-- ProtocolError
|
+-- StorageError
|   +-- ConcurrencyConflict
|   +-- PersistenceUnavailable
|
+-- ExecutionError
|   +-- AmbiguousSubmission
|   +-- UnsupportedOrder
|
+-- ReconciliationError
+-- InvariantViolation
```

Errors should include structured context, not formatted secrets.

Expected business rejections should not be represented as generic exceptions.

Never catch `Exception` merely to ignore it.

A broad catch is acceptable at a process or task boundary when it:

- logs the failure
- records metrics
- changes health state
- applies a defined recovery policy
- preserves cancellation semantics


# 24. Retry Engineering

Retries are permitted only for classified transient failures.

Retry policy must specify:

- eligible exception types or status codes
- maximum attempts
- backoff
- jitter
- deadline
- idempotency assumptions
- final failure behavior

Do not retry validation errors.

Do not blindly retry ambiguous order submissions.

Do not create nested uncontrolled retry loops.

Retry events should emit metrics and structured logs.

Use a library such as Tenacity when it improves consistency, but keep retry
policy visible and testable.


# 25. Idempotency Standards

Idempotency is mandatory for:

- order commands
- fill application
- event consumption
- reconciliation corrections
- operator commands
- database migrations
- replay imports

Common techniques:

- unique event identifiers
- idempotency keys
- processed-event tables
- unique database constraints
- compare-and-set aggregate versions
- natural exchange identifiers

Tests shall apply the same event or command more than once and verify that the
business result occurs once.


# 26. Logging Standards

## 26.1 Structured Logging

Use structured logs.

Recommended library: structlog or a standard-library logging configuration that
produces equivalent structured output.

## 26.2 Required Fields

Where applicable:

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

## 26.3 Event Names

Use stable machine-readable event names.

Examples:

- adapter.connected
- order.submit.started
- order.submit.failed
- risk.intent.rejected
- replay.session.completed

## 26.4 Message Style

The human message should add useful context but not duplicate every structured
field.

## 26.5 Secret Redaction

Redact:

- API keys
- tokens
- signatures
- private keys
- cookies
- authorization headers
- database passwords

## 26.6 Logging Exceptions

Use exception logging at the boundary that owns recovery.

Avoid logging the same exception at every stack layer.

## 26.7 Log Levels

DEBUG:

- diagnostic detail
- disabled or sampled in production

INFO:

- normal lifecycle events
- important business milestones

WARNING:

- recoverable degradation
- stale data
- retry
- sequence recovery

ERROR:

- failed operation
- lost capability
- dead-letter event

CRITICAL:

- global trading safety issue
- unreconciled live state
- corrupted durable data


# 27. Metrics Standards

Metrics must have bounded cardinality.

Do not place raw order IDs, market titles, exception messages, or user-provided
text in metric labels.

Use stable labels such as:

- exchange
- component
- strategy_type
- environment
- result
- reason_code

High-cardinality detail belongs in logs or traces.

Every latency histogram must define:

- start event
- end event
- unit
- expected range

Counters use `_total`.

Durations use seconds for Prometheus-style metrics.

Metrics should support service-level objectives and incident diagnosis.


# 28. Tracing Standards

Tracing is optional in early local development but should be supported by the
architecture.

Trace propagation should follow:

```text
market event
  -> strategy processing
  -> signal
  -> order intent
  -> risk decision
  -> execution
  -> adapter
  -> exchange acknowledgement
  -> fill
  -> portfolio update
```

Do not attach sensitive payloads to spans.

Sampling policy should be configurable.

Errors that affect live trading should be traceable even under normal sampling
through explicit retention or error sampling.


# 29. Configuration Engineering

## 29.1 Typed Settings

Use Pydantic Settings.

Configuration must be validated before service startup.

## 29.2 Configuration Ownership

A component receives configuration through dependency injection.

It should not read environment variables throughout its methods.

## 29.3 Environment Variables

Environment variables are appropriate for:

- secrets
- deployment-specific endpoints
- top-level overrides

They are not a substitute for a coherent typed configuration model.

## 29.4 Configuration Dumps

The system may log a redacted configuration summary and configuration hash.

Never log secret values.

## 29.5 Dynamic Configuration

Dynamic live configuration must be:

- scoped
- validated
- versioned
- auditable
- reversible
- applied atomically where possible

Risk-limit changes require special review and audit.


# 30. Secret Management

Secrets shall not be committed.

The repository shall contain `.env.example`, not `.env`.

Recommended secret sources:

- environment injection
- operating-system credential store
- cloud secret manager
- encrypted development secret store

Secret rotation should not require source-code changes.

Production credentials should use the least permissions available.

Withdrawal permissions should be disabled when the exchange allows it.

Secret scanners should run in CI or repository hosting.

A suspected secret leak requires:

1. revoke or rotate the credential
2. remove it from active configuration
3. investigate access logs
4. clean repository history only if justified
5. document the incident


# 31. Database Engineering

## 31.1 Access Pattern

Use SQLAlchemy for database abstraction and asyncpg for PostgreSQL access where
appropriate.

Repositories expose domain-oriented methods.

Strategies shall not receive database sessions.

## 31.2 Transactions

Transaction boundaries belong in the application or storage service that owns
the use case.

Avoid hidden commits inside low-level helper methods.

## 31.3 Connection Pools

Pool sizes must be configured by deployment and measured.

Do not create one pool per request or strategy.

## 31.4 Query Safety

Use parameterized queries.

Do not construct SQL with untrusted string interpolation.

## 31.5 Indexes

Add indexes based on query patterns and explain them in migrations.

Every high-volume table should have an explicit retention and partitioning
strategy.

## 31.6 N+1 Queries

Review data access paths for N+1 behavior.

Batch reads and writes when safe.

## 31.7 Database Time

Use application timestamps from the approved clock for domain events.

Database-generated timestamps may be used for storage audit fields when their
meaning is explicit.


# 32. Database Migration Standards

Use Alembic.

Every schema change requires a migration.

A migration shall be:

- deterministic
- reviewed
- tested on a representative database
- backward-aware
- documented when operationally significant

Avoid destructive changes in one deployment step.

Preferred expand-and-contract process:

1. add new nullable column or table
2. deploy code that writes both representations if needed
3. backfill
4. deploy code that reads the new representation
5. verify
6. remove the old representation in a later release

Large backfills should be separate operational jobs, not blocking migration
transactions.

Migration pull requests should include:

- purpose
- expected runtime
- lock behavior
- rollback or recovery plan
- data backfill plan


# 33. Event Store Engineering

The event store is append-only.

Event payloads require:

- stable serialization
- schema version
- event ID
- payload hash
- timestamp semantics

Consumers should not depend on database row order.

Event replay ordering is explicit.

Event corrections create new events.

Do not update historical event payloads in place except for tightly controlled
administrative repair with an audit trail and checksum verification.


# 34. Serialization Standards

Canonical JSON should use stable field names and explicit schema versions.

Datetime serialization uses ISO 8601 with UTC offset.

Decimal values should serialize as strings unless a schema explicitly defines
another exact representation.

Do not serialize Decimal through float.

Binary raw payloads may be stored as bytes with content type and compression
metadata.

Serialization round-trip tests are required for canonical events.


# 35. Exchange Adapter Engineering

Every adapter shall implement the common adapter contract.

Adapter code shall be divided into:

- authentication
- transport
- raw models
- mapping
- rate limiting
- capability declaration
- errors
- reconciliation queries

The adapter shall not contain strategy policy.

Every external endpoint requires:

- timeout
- error mapping
- retry classification
- request correlation
- structured logging
- metrics

WebSocket implementations require:

- heartbeat
- reconnect
- resubscription
- sequence validation where available
- snapshot recovery
- bounded queues
- graceful shutdown

Adapters should preserve raw payload fixtures for contract tests.


# 36. API Client Standards

HTTP clients should be long-lived and pooled.

Use explicit base URLs, timeouts, and headers.

Do not create a new HTTP client for every request.

Request and response logs must redact sensitive headers and bodies.

Error mapping should preserve:

- HTTP status
- exchange error code
- retryability
- request ID
- safe response excerpt
- endpoint category

Rate limiting should be centralized per adapter, not scattered across call
sites.


# 37. WebSocket Standards

WebSocket readers should:

- parse frames promptly
- avoid heavy work in the reader loop
- place validated raw messages on bounded queues
- detect heartbeat failure
- detect protocol errors
- measure receive lag
- reconnect through one controlled supervisor

Writers should be serialized.

Subscription state should be explicit and replayable after reconnect.

A reconnect should not automatically reopen trading until reconciliation is
complete.


# 38. Event Bus Engineering

Initial in-process event bus requirements:

- typed subscription
- bounded queue
- deterministic test mode
- consumer naming
- health reporting
- graceful close
- partition ordering
- backpressure metrics

Consumer exceptions must not terminate unrelated consumers.

Durable consumers need an acknowledgement and retry model.

If an external broker is adopted, adapters around the broker should preserve
the same application-level event interface.


# 39. Strategy Engineering Standards

Strategies shall be deterministic with respect to:

- input events
- configuration
- clock
- model artifacts
- random seed
- portfolio snapshot

Strategies shall not:

- read environment variables
- call wall-clock time
- call exchange APIs
- write directly to databases
- bypass risk
- mutate canonical events

Strategy configuration must be typed and versioned.

A strategy should expose:

- name
- version
- configuration schema
- subscribed event types
- lifecycle state
- health
- metrics

Every strategy requires:

- unit tests
- replay tests
- simulation tests
- risk assumptions
- failure behavior
- parameter documentation


# 40. Model Engineering Standards

A model artifact must include metadata:

- model name
- model version
- training code commit
- training dataset identifier
- dataset checksum
- feature schema version
- target definition
- training timestamp
- evaluation metrics
- calibration metadata
- random seed
- library versions

Inference should be deterministic unless the model explicitly requires
stochastic behavior.

Stochastic inference must use an injected seed source and record the seed.

Models do not submit orders.

Strategies convert model outputs into signals and order intents.

Model loading failures must degrade the owning strategy safely.


# 41. Feature Engineering Standards

Features require:

- descriptive name
- version
- input event types
- window definition
- null behavior
- warm-up requirement
- units
- leakage analysis
- tests

A feature must not read future data in replay.

Rolling calculations should define:

- inclusive or exclusive boundaries
- event-time or receive-time basis
- minimum observations
- behavior across market gaps
- reset behavior

Feature snapshots should be traceable to source events where practical.


# 42. Replay Engineering Standards

Replay code must be deterministic.

Replay shall not:

- make network calls
- use live credentials
- write to live operational tables
- call system time directly
- depend on unordered dictionary iteration for business ordering
- use an unseeded random generator

Replay manifests include:

- dataset checksum
- code commit
- configuration hash
- strategy versions
- model versions
- random seed
- event ordering policy version

Golden replay tests shall compare stable result checksums.

Changes that alter expected replay output require explanation and reviewed
golden-file updates.


# 43. Simulation Engineering Standards

Simulation assumptions must be explicit and versioned.

Every simulator configuration should identify:

- fill model
- queue model
- latency model
- fee model
- rejection model
- slippage model
- settlement model
- random seed

The simulator must distinguish:

- observed facts
- inferred behavior
- stochastic assumptions

Simulation results shall not be presented as historical fact.

Scenario tests should cover cancellation races, partial fills, stale orders,
disconnects, and multi-leg execution risk.


# 44. Execution Engineering Standards

Execution code is high risk.

Required characteristics:

- explicit order state machine
- idempotency keys
- timeout handling
- ambiguous-state handling
- reconciliation
- audit events
- bounded retries
- capability checks
- risk approval evidence

No call site may submit an exchange order without an approved order object.

Execution errors must distinguish:

- rejected
- failed before submission
- ambiguous after submission
- accepted
- partially filled
- terminal

Unknown order state blocks conflicting activity until reconciled.


# 45. Risk Engineering Standards

Risk rules should be small, independently testable components.

Each rule has:

- stable identifier
- version
- inputs
- output
- reason code
- configuration
- tests

Risk decisions are immutable records.

Do not log only a boolean.

Record calculated exposure and compared limit.

Risk calculations use Decimal.

Stale or missing required inputs reject live order intents.

Kill-switch code requires dedicated tests and operational review.


# 46. Portfolio and Accounting Engineering

Portfolio accounting must be deterministic and idempotent.

Every fill is applied once.

Fee treatment is explicit.

Position calculations must define:

- average-cost method
- realized PnL
- unrealized PnL
- settlement
- corrections
- transfers

All portfolio changes are traceable to source events.

Reconciliation tests should include:

- duplicate fills
- missing fills
- manual exchange activity
- fee differences
- settlement corrections
- partial fills
- out-of-order updates


# 47. Testing Philosophy

Tests exist to reduce uncertainty.

A useful test protects:

- a business invariant
- an interface contract
- a failure mode
- a calculation
- a state transition
- a compatibility guarantee
- a previously observed defect

Avoid tests that merely restate implementation line by line.

Prefer behavior-focused tests.

Tests must be:

- deterministic
- isolated
- readable
- fast enough for their layer
- explicit about fixtures
- independent of execution order

Flaky tests are defects.


# 48. Test Pyramid and Categories

## 48.1 Unit Tests

Fast, isolated tests of:

- value objects
- calculations
- state machines
- mapping functions
- validators
- risk rules
- feature functions

## 48.2 Property Tests

Generate many inputs to validate invariants.

## 48.3 Contract Tests

Validate every exchange adapter against the same expected behavior.

## 48.4 Integration Tests

Exercise component boundaries with real infrastructure such as PostgreSQL.

## 48.5 Replay Tests

Verify deterministic historical processing.

## 48.6 Simulation Tests

Verify fills, latency, cancellation, and failure scenarios.

## 48.7 End-to-End Tests

Exercise complete workflows in safe non-live environments.

## 48.8 Live Smoke Tests

Only for tightly controlled production validation.

They require explicit approval and minimal risk.


# 49. Unit Test Standards

Unit tests should not require:

- network access
- real database
- external clock
- live credentials
- nondeterministic sleeps

Use fakes and frozen clocks.

Naming pattern:

```python
def test_<behavior>_<condition>_<expected_result>() -> None:
    ...
```

Example:

```python
def test_fill_application_duplicate_fill_is_idempotent() -> None:
    ...
```

A unit test should generally follow:

1. arrange
2. act
3. assert

Do not overabstract test setup.

Use helper builders only when they improve readability.


# 50. Async Test Standards

Use pytest-asyncio.

Async tests should avoid real sleeps.

Use:

- fake clocks
- manually advanced queues
- test task groups
- deterministic events

Every async component should have tests for:

- normal completion
- cancellation
- timeout
- dependency failure
- shutdown
- queue saturation where relevant

Tests must clean up tasks and clients.

A leaked task warning is a test failure.


# 51. Property-Based Testing

Use Hypothesis for mathematically rich and stateful domains.

Recommended properties:

- probability remains within zero and one
- quantity never becomes negative
- order filled quantity never decreases
- duplicate fills do not change state twice
- serialization round trips preserve values
- replay output is deterministic
- fee calculations follow published rules
- PnL reconciles
- order book deltas preserve sorted sides
- arbitrage profit is positive only after fees and slippage
- state machines reject invalid transitions

Use stateful rule-based tests for order and portfolio state machines where
valuable.

Property tests should use reproducible seeds when diagnosing failures.


# 52. Adapter Contract Tests

The common contract suite should test:

- connection lifecycle
- health reporting
- authentication failure
- market listing
- subscription
- snapshot parsing
- delta parsing
- trade parsing
- order submission
- cancellation
- open-order query
- position query
- balance query
- reconnect
- sequence gap
- malformed payload
- rate limit
- timeout
- idempotency support

Each adapter provides fixtures and a contract harness.

A new adapter is not complete until it passes the suite.


# 53. Fixture Standards

Fixtures should be:

- minimal
- realistic
- redacted
- versioned
- named by behavior

Recommended layout:

```text
tests/fixtures/
  kalshi/
    market_snapshot/
    order_book/
    trades/
    orders/
    errors/
  polymarket/
    market_snapshot/
    order_book/
    trades/
    orders/
    errors/
```

Include fixtures for:

- normal payloads
- optional fields absent
- malformed values
- duplicates
- out-of-order data
- sequence gaps
- unknown enum values
- authentication failures
- rate limits
- service errors

Do not place live secrets or personal account data in fixtures.


# 54. Integration Test Standards

Integration tests may use:

- PostgreSQL
- local object storage
- broker containers
- simulated exchange servers

They should be runnable locally and in CI.

Use isolated databases or schemas per test session.

Migrations should be applied in the integration environment.

Integration tests shall not rely on production services.

Network access to the public internet should be disabled unless a test is
explicitly designated and excluded from normal CI.


# 55. Replay Test Standards

Each replay fixture should include:

- manifest
- event archive
- dataset checksum
- expected output checksum
- strategy configuration
- model metadata
- seed

Tests should verify:

- event order
- clock progression
- signal output
- order intent output
- simulated fills
- final portfolio
- result checksum

When a valid behavior change updates a golden result, the pull request must
explain the difference.


# 56. Simulation Test Standards

Simulation tests must distinguish deterministic scenario tests from stochastic
calibration tests.

Deterministic scenarios use fixed seeds and expected outcomes.

Stochastic tests should verify distributions or statistical bounds without
becoming flaky.

Required scenarios:

- maker fill
- no fill
- partial fill
- taker slippage
- cancellation before fill
- fill during cancellation
- reject
- disconnect
- stale quote
- market halt
- settlement
- multi-leg imbalance


# 57. End-to-End Test Standards

End-to-end tests should exercise:

```text
raw payload
  -> normalization
  -> event storage
  -> strategy
  -> risk
  -> paper execution
  -> fill
  -> portfolio
  -> metrics
```

End-to-end tests are fewer and slower than unit tests.

They should focus on critical workflows and production-like integration, not
duplicate every edge case already covered below.


# 58. Test Data Management

Test datasets should have:

- stable identifier
- checksum
- license or origin note
- redaction status
- schema version
- expected time range
- size classification

Large datasets should not be committed directly to Git unless appropriate.

Use artifact storage with a manifest and retrieval script.

A test must not silently download mutable data.


# 59. Coverage Standards

Use pytest-cov and coverage.py.

Initial repository threshold:

```text
80 percent line coverage
```

Long-term target:

```text
90 percent line coverage for core domain and execution packages
```

Branch coverage should be enabled.

Coverage is a floor, not the goal.

Critical code requires strong behavioral tests even if overall coverage passes.

Packages that should receive especially high scrutiny:

- execution
- risk
- portfolio
- replay
- normalization
- adapter mapping
- order state machine

Excluded code must be justified.


# 60. Mutation and Robustness Testing

Mutation testing may be introduced for critical pure logic.

Good candidates:

- fee calculations
- PnL
- risk checks
- order transitions
- probability bounds
- matching validation

Mutation testing is not required for every pull request.

It may run on a schedule or before major releases.


# 61. Test Markers

Recommended pytest markers:

- unit
- integration
- contract
- replay
- simulation
- end_to_end
- slow
- live
- postgres
- broker

Markers must be registered.

Normal pull-request CI should run all non-live required suites.

Live tests are never run by default.


# 62. Formatting and Linting

Use Ruff for both formatting and linting.

Developers should run:

```bash
uv run ruff format .
uv run ruff check . --fix
```

CI runs:

```bash
uv run ruff format --check .
uv run ruff check .
```

Do not manually fight the formatter.

Lint suppressions must be narrow.

File-wide suppressions require explanation.

Generated files may be excluded explicitly.


# 63. Static Type Checking

Run mypy against production source and selected test code.

CI command:

```bash
uv run mypy src
```

Desired direction:

- strict checks for domain, execution, risk, portfolio, and replay
- targeted overrides for third-party integrations
- no untyped public APIs
- no implicit optional values
- no unchecked generic collections

Mypy configuration changes require review because they can weaken repository
guarantees.


# 64. Pre-Commit Standards

Pre-commit should run fast local checks:

- trailing whitespace
- end-of-file fixer
- YAML validation
- TOML validation
- large-file check
- secret detection
- Ruff formatter
- Ruff linter
- optional mypy subset

Hooks should complete quickly enough that contributors keep them enabled.

Slower integration tests belong in CI.

Installation:

```bash
uv run pre-commit install
```

Run all hooks:

```bash
uv run pre-commit run --all-files
```


# 65. Continuous Integration

## 65.1 Pull Request Pipeline

Required jobs:

1. repository validation
2. dependency lock verification
3. formatting
4. linting
5. static typing
6. unit and property tests
7. integration tests
8. adapter contract tests
9. replay determinism tests
10. coverage
11. security scanning
12. package build

Jobs may run in parallel where dependencies allow.

## 65.2 Main Branch Pipeline

In addition to pull-request checks:

- build release artifacts
- publish development container if configured
- run extended tests
- archive test reports
- update documentation artifacts

## 65.3 Scheduled Pipeline

Recommended scheduled jobs:

- dependency vulnerability scan
- dependency update proposal
- extended replay suite
- mutation tests
- long-running simulation suite
- flaky-test detection

## 65.4 Required Checks

The protected main branch shall require passing checks and review.


# 66. CI Determinism and Caching

CI should use the committed lock file.

Cache keys must include relevant files such as:

- uv.lock
- Python version
- operating system

Caching must not hide dependency or build problems.

Tests should not depend on execution order.

Parallel test execution may be enabled only after isolation is verified.


# 67. Git Workflow

Use a protected main branch.

Normal work occurs on short-lived branches.

Recommended branch names:

```text
feature/kalshi-order-stream
fix/duplicate-fill-idempotency
docs/replay-runbook
refactor/portfolio-projection
```

Avoid long-running integration branches.

Rebase or merge according to repository policy, but keep history understandable.

Force pushes to shared branches should be avoided.


# 68. Commit Standards

Commits should be coherent and buildable where practical.

Commit messages should explain intent.

Recommended format:

```text
component: concise imperative summary

Optional body explaining why, constraints, and consequences.
```

Examples:

```text
execution: reject duplicate fill identifiers
replay: add stable tie-break ordering
kalshi: map sequence gaps to canonical events
```

Do not commit:

- secrets
- local environments
- generated caches
- unreviewed large datasets
- editor-specific state
- temporary debugging output


# 69. Pull Request Standards

A pull request should include:

- problem or goal
- design summary
- tests
- operational impact
- migration impact
- risk impact
- replay impact
- screenshots or sample output when useful
- linked issue or ADR when applicable

Keep pull requests focused.

Large pull requests should explain why they could not be split safely.

Draft pull requests are encouraged for early design feedback.


# 70. Code Review Standards

Reviewers should evaluate:

- correctness
- architectural boundaries
- state ownership
- failure modes
- idempotency
- numeric precision
- time semantics
- security
- observability
- tests
- migration safety
- documentation
- operational behavior

Review comments should distinguish:

- blocking issue
- suggestion
- question
- optional cleanup

Authors should respond to every substantive comment.

Approval does not transfer ownership of correctness away from the author.


# 71. Review Requirements by Risk

Low-risk examples:

- documentation correction
- isolated test improvement
- internal refactor with unchanged behavior

Normal-risk examples:

- new strategy feature
- adapter endpoint
- database query
- feature calculation

High-risk examples:

- live execution
- authentication
- risk limits
- portfolio accounting
- settlement
- database migration on high-volume tables
- kill switches
- secret handling

High-risk changes should receive additional domain review and stronger evidence.


# 72. Architecture Decision Records

Use ADRs for decisions that:

- affect multiple packages
- create long-term constraints
- add major infrastructure
- change canonical schemas
- change delivery semantics
- change supported runtime
- alter risk behavior
- alter storage architecture

ADR format:

```text
Title
Status
Date
Context
Decision
Alternatives
Consequences
Migration
References
```

ADRs are immutable after acceptance except for status and clarifying notes.

A superseding ADR should reference the older decision.


# 73. Documentation Standards

Documentation should be stored near its audience.

Repository-level:

- README.md
- CONTRIBUTING.md
- SECURITY.md
- architecture
- engineering standards

Package-level:

- package README or module docs
- public interface examples

Operational:

- runbooks
- deployment notes
- incident procedures

Code comments should explain why, constraints, and nonobvious invariants.

Do not comment obvious syntax.

Public interfaces should have docstrings describing:

- behavior
- parameters
- result
- exceptions
- side effects
- time and unit semantics where relevant


# 74. Notebook Standards

Notebooks are research tools, not the production runtime.

Notebooks should:

- use pinned datasets
- record environment information
- avoid hidden state
- use deterministic seeds
- call library code rather than duplicate it
- document assumptions
- produce exportable results

Production logic discovered in a notebook must be moved into tested source
modules before use in replay, shadow, or live modes.

Clear outputs before committing when they contain sensitive or excessive data.


# 75. Script Standards

Scripts under `scripts/` should be thin wrappers around library functions.

A script should:

- parse arguments
- load configuration
- call a library service
- return meaningful exit codes
- log structured output
- handle errors at the process boundary

Avoid placing reusable business logic only in scripts.


# 76. Command-Line Interface Standards

CLI commands should be safe by default.

Dangerous commands require explicit flags.

Example:

```bash
pmrp trade start --environment production --confirm-live
```

CLI output should support:

- human-readable mode
- structured JSON mode where useful

Exit codes should distinguish:

- success
- validation failure
- operational failure
- partial failure
- unsafe state

Commands should be idempotent when feasible.


# 77. Container Standards

Containers should:

- use a pinned Python base image
- install from `uv.lock`
- run as a non-root user
- contain only required runtime files
- expose health checks
- avoid embedded secrets
- use immutable tags or digests in production
- produce reproducible builds

Use multi-stage builds if they reduce runtime size or build dependencies.

The container entrypoint should handle signals and graceful shutdown.


# 78. Docker Compose Standards

Docker Compose is recommended for local integration.

Services may include:

- PostgreSQL
- optional Redis
- collector
- trader
- operator API
- metrics system

Compose configuration should:

- use named volumes
- expose only necessary ports
- use development credentials only
- include health checks
- support deterministic startup
- document cleanup commands

Do not treat local Compose configuration as production deployment configuration.


# 79. Supply-Chain Security

The project should implement:

- dependency lock
- vulnerability scanning
- secret scanning
- license review
- container scanning
- protected branches
- signed commits or releases when practical
- minimal publishing credentials
- trusted release workflow

Dependency updates should be reviewed, not merged solely because a bot opened
them.

Security fixes receive prioritized handling.


# 80. Static Security Analysis

Security tooling may include:

- Bandit or equivalent Python security checks
- dependency vulnerability scans
- secret scanners
- container scanners
- infrastructure checks

Static analysis findings require triage.

Suppressions must include:

- reason
- scope
- reviewer approval
- expiration or follow-up when applicable


# 81. Performance Engineering

Performance work begins with a written problem statement and measurement.

Required before optimization:

- workload
- baseline
- bottleneck evidence
- target
- correctness constraints

Possible tools:

- cProfile
- py-spy
- scalene
- memory_profiler
- database query plans
- event-lag metrics

Optimization order:

1. remove unnecessary work
2. improve algorithm
3. batch operations
4. optimize data structures
5. use vectorized libraries
6. use multiprocessing
7. use compiled extensions
8. isolate a service in another language

Every optimization requires regression tests.


# 82. Benchmark Standards

Benchmarks should define:

- hardware
- Python version
- dependency lock
- dataset
- warm-up
- repetitions
- metric
- variance
- baseline commit

Benchmarks must not replace correctness tests.

Microbenchmarks are useful only when they represent a measured bottleneck.

Store benchmark results for significant performance-sensitive changes.


# 83. Memory Engineering

High-volume event systems must control memory.

Practices:

- bounded queues
- streaming reads
- batch sizes
- avoid retaining raw payloads indefinitely in memory
- release replay chunks
- avoid accidental DataFrame copies
- monitor heap growth
- test sustained workloads

Memory leaks or unbounded growth are release blockers for long-running services.


# 84. DataFrame and Numerical Computing Standards

Pandas is appropriate for research and batch analytics.

It should not automatically be used in latency-sensitive event loops.

For production numerical code:

- define dtypes
- avoid implicit object columns
- avoid chained assignment
- test missing-value behavior
- document index assumptions
- profile copies
- preserve exact financial values outside float-based operations

If a calculation uses float for statistical reasons, conversion back to
financial values must use explicit, reviewed rounding.


# 85. Randomness Standards

Random behavior must be injectable and seedable.

Do not use process-global random state in replay or simulation.

Record seeds in experiment and replay manifests.

Different stochastic subsystems should use derived independent streams where
appropriate.

Tests use fixed seeds.

A failure produced by property or stochastic testing must be reproducible.


# 86. Determinism Standards

Determinism requires attention to:

- event ordering
- random seeds
- time source
- dependency versions
- thread or process scheduling
- stable serialization
- database query ordering
- floating-point behavior
- model versions

Every query whose order affects behavior requires an explicit `ORDER BY`.

Never rely on set iteration order for business decisions.

Replay result checksums should be based on canonical stable serialization.


# 87. Data Quality Engineering

Data-quality rules should produce structured findings.

Each finding includes:

- rule ID
- severity
- exchange
- market
- event ID
- safe payload reference
- detected time
- recommended action

Examples:

- missing timestamp
- invalid probability
- negative quantity
- sequence gap
- stale snapshot
- duplicate trade
- unknown market
- unsupported status
- crossed book
- timestamp reversal

Critical findings may invalidate projections and block trading.


# 88. Schema Evolution Engineering

Canonical schemas use explicit versions.

Readers should tolerate additive optional fields.

Semantic changes require version changes.

Historical events should be read through upcasters when necessary.

Schema changes require:

- updated models
- migration if persisted shape changes
- compatibility tests
- fixture updates
- replay test review
- documentation
- release note

Do not silently reinterpret an existing field.


# 89. Backward Compatibility

Stable public plugin interfaces should follow a compatibility policy.

Breaking changes require:

- version increment
- migration instructions
- deprecation period when practical
- examples
- tests

Internal modules may change more freely but should still avoid unnecessary churn.

Deprecations should emit warnings in development and have a removal target.


# 90. Release Versioning

Use semantic versioning for the platform package.

Before version 1.0, breaking changes may occur but still require documentation.

Release notes should include:

- features
- fixes
- schema changes
- migration requirements
- configuration changes
- security changes
- replay-impacting changes
- known issues

Model and strategy versions are independent from the platform package version.


# 91. Build and Packaging

The package must build from a clean checkout using the lock file.

CI should run:

```bash
uv build
```

The built artifact should be installable into a clean environment.

Do not depend on untracked repository files.

Package metadata should include:

- name
- version
- description
- license
- Python requirement
- project URLs
- classifiers where useful


# 92. Release Process

Recommended release steps:

1. verify main branch
2. run full CI
3. review migrations
4. review canonical schema changes
5. run extended replay suite
6. build package and container
7. generate release notes
8. sign or attest artifacts where practical
9. publish
10. deploy to staging
11. verify health
12. deploy to production under change policy
13. monitor
14. record release outcome

Emergency releases may shorten timing but not bypass essential safety checks.


# 93. Rollback and Recovery

Every production release should have a rollback plan.

Rollback complexity increases when:

- database migrations are destructive
- schemas are incompatible
- events are emitted in a new format
- order state changes
- model artifacts change

Prefer forward-compatible changes that allow application rollback.

When rollback is unsafe, document a forward-fix plan.


# 94. Operational Readiness Review

A component that affects live trading requires an operational readiness review.

Checklist:

- health checks
- metrics
- logs
- alerts
- timeouts
- retries
- shutdown
- reconciliation
- capacity
- security
- runbook
- rollback
- test evidence
- owner

A feature may be code-complete but not operationally ready.


# 95. Runbook Standards

A runbook should include:

- purpose
- scope
- symptoms
- alerts
- immediate containment
- diagnosis
- commands
- recovery
- validation
- escalation
- post-incident tasks

Commands should be copyable and clearly mark destructive actions.

Runbooks should be tested during exercises or real incidents and updated.


# 96. Incident Engineering

Incidents should produce:

- timeline
- customer or trading impact
- detection
- contributing factors
- root causes
- containment
- recovery
- corrective actions

Post-incident reviews are blameless and evidence based.

Corrective actions should address system design, testing, monitoring, or process,
not only individual behavior.


# 97. Deprecation and Removal

Deprecated code should have:

- reason
- replacement
- warning
- removal version or date
- migration instructions

Do not maintain two paths indefinitely without a plan.

Remove dead flags, unused configuration, and compatibility adapters after the
approved window.


# 98. Feature Flags

Feature flags may control:

- experimental strategies
- new adapter paths
- new reconciliation logic
- shadow behavior
- staged rollouts

Flags must have:

- owner
- default
- environment scope
- expiration
- audit behavior if safety relevant

A feature flag must not bypass mandatory risk controls.


# 99. Environment Separation

Environments:

- local
- test
- development
- staging
- shadow
- production

Each environment has separate:

- credentials
- databases
- storage namespaces
- monitoring labels
- risk limits
- operator permissions

Code should display the environment prominently in logs and operator interfaces.

Production should reject known development credentials and unsafe configuration.


# 100. Live Trading Safeguards

Live mode requires:

- explicit environment
- explicit `live_trading_enabled`
- valid production credentials
- successful adapter connection
- fresh market data
- successful order reconciliation
- successful position reconciliation
- successful balance reconciliation
- healthy risk engine
- clear kill switch
- operator authorization where configured

A test or replay process must be structurally unable to submit live orders.

Use separate dependency injection graphs for live and non-live gateways.


# 101. Coding Agent Usage

Coding agents may scaffold and implement work, but all output remains subject to
the same engineering standards.

Agent tasks should provide:

- governing documents
- exact scope
- package boundaries
- interfaces
- acceptance criteria
- required tests
- prohibited changes

Agents should not be asked to implement an entire platform in one unreviewed
change.

Recommended sequence:

1. create interfaces and tests
2. implement one component
3. run checks
4. review diff
5. refine
6. commit intentionally

Never give an agent production secrets.

Agent-generated code must be reviewed for:

- invented APIs
- false assumptions
- silent exception handling
- missing idempotency
- numeric errors
- concurrency leaks
- weak tests
- architecture violations


# 102. Definition of Ready

A work item is ready when it has:

- problem statement
- scope
- non-scope
- owning package
- interface impact
- data and schema impact
- risk impact
- acceptance criteria
- test expectations
- operational considerations

Small defects may require less formal detail, but the expected behavior must be
clear.


# 103. Definition of Done

A change is done when applicable requirements are complete.

Code:

- implementation is complete
- boundaries are respected
- types are complete
- formatting and linting pass
- static typing passes
- errors are classified
- logs and metrics are appropriate
- secrets are protected

Tests:

- unit tests pass
- property tests exist where valuable
- integration tests pass
- replay or simulation tests pass where applicable
- coverage threshold passes
- failure modes are tested

Data:

- migrations exist
- schema versions are updated
- fixtures are updated
- rollback or recovery is documented

Documentation:

- public behavior is documented
- configuration is documented
- ADR exists if required
- runbook exists if operationally critical
- release notes are updated when appropriate

Operations:

- health behavior is defined
- alerts are considered
- deployment is safe
- live safeguards remain intact


# 104. Mandatory Pull Request Checklist

```text
[ ] Scope is clear and focused.
[ ] Architecture boundaries are respected.
[ ] Financial values use Decimal where required.
[ ] Time uses the approved clock abstraction.
[ ] External input is validated.
[ ] Errors are classified and observable.
[ ] Idempotency is addressed.
[ ] Concurrency and cancellation are addressed.
[ ] Tests cover normal and failure paths.
[ ] Replay determinism impact is reviewed.
[ ] Database migration impact is reviewed.
[ ] Security and secret handling are reviewed.
[ ] Documentation is updated.
[ ] CI passes.
[ ] Live-trading safety is unchanged or explicitly reviewed.
```


# 105. Recommended Developer Workflow

Initial setup:

```bash
uv sync --locked --all-groups
uv run pre-commit install
```

Create a branch:

```bash
git switch -c feature/example
```

During development:

```bash
uv run ruff format .
uv run ruff check . --fix
uv run mypy src
uv run pytest tests/unit
```

Before opening a pull request:

```bash
uv run pre-commit run --all-files
uv run pytest --cov=src/pmrp --cov-branch
uv build
```

Integration tests may require:

```bash
docker compose up -d postgres
uv run pytest -m integration
```


# 106. Makefile or Task Runner Interface

A Makefile may provide discoverable wrappers.

Example targets:

```makefile
.PHONY: sync format lint typecheck test test-unit test-integration coverage build check

sync:
	uv sync --locked --all-groups

format:
	uv run ruff format .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src

test:
	uv run pytest

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

coverage:
	uv run pytest --cov=src/pmrp --cov-branch

build:
	uv build

check: format lint typecheck test build
```

The task runner is a convenience layer.

The underlying commands remain authoritative and usable directly.


# 107. Reference pyproject.toml

The following is a recommended starting configuration. Exact dependency
versions are resolved and pinned by `uv.lock`.

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "prediction-market-research-platform"
version = "0.1.0"
description = "Exchange-agnostic prediction-market research and trading platform"
readme = "README.md"
requires-python = ">=3.13,<3.14"
license = { text = "Apache-2.0" }
authors = [
  { name = "PMRP Contributors" },
]
dependencies = [
  "alembic",
  "asyncpg",
  "httpx",
  "numpy",
  "orjson",
  "pandas",
  "pydantic",
  "pydantic-settings",
  "scikit-learn",
  "scipy",
  "sqlalchemy",
  "structlog",
  "tenacity",
  "websockets",
]

[dependency-groups]
dev = [
  "mypy",
  "pre-commit",
  "ruff",
]
test = [
  "hypothesis",
  "pytest",
  "pytest-asyncio",
  "pytest-cov",
  "pytest-mock",
]

[tool.hatch.build.targets.wheel]
packages = ["src/pmrp"]

[tool.ruff]
target-version = "py313"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = [
  "A",
  "ARG",
  "ASYNC",
  "B",
  "C4",
  "DTZ",
  "E",
  "F",
  "FA",
  "FBT",
  "FLY",
  "FURB",
  "I",
  "ICN",
  "INP",
  "LOG",
  "N",
  "PERF",
  "PIE",
  "PL",
  "PT",
  "PTH",
  "RET",
  "RSE",
  "RUF",
  "S",
  "SIM",
  "SLOT",
  "T10",
  "T20",
  "TRY",
  "UP",
  "W",
]
ignore = [
  "PLR0913",
]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = [
  "S101",
  "PLR2004",
]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
line-ending = "lf"

[tool.mypy]
python_version = "3.13"
strict = true
mypy_path = "src"
packages = ["pmrp"]
warn_unused_configs = true
show_error_codes = true
pretty = true

[[tool.mypy.overrides]]
module = [
  "some_untyped_dependency.*",
]
ignore_missing_imports = true

[tool.pytest.ini_options]
minversion = "8.0"
addopts = [
  "--strict-config",
  "--strict-markers",
  "-ra",
]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
  "unit: fast isolated tests",
  "integration: tests using local infrastructure",
  "contract: exchange adapter contract tests",
  "replay: deterministic replay tests",
  "simulation: simulated execution tests",
  "end_to_end: full safe workflow tests",
  "slow: tests excluded from quick local runs",
  "live: explicitly authorized live tests",
]

[tool.coverage.run]
branch = true
source = ["pmrp"]
parallel = true

[tool.coverage.report]
fail_under = 80
show_missing = true
skip_covered = false
exclude_also = [
  "if TYPE_CHECKING:",
  "raise NotImplementedError",
  "@overload",
]

[tool.coverage.paths]
source = [
  "src/pmrp",
  "*/site-packages/pmrp",
]
```


# 108. Reference pre-commit Configuration

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: check-toml
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.0.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

The placeholder revision must be replaced with an approved current pinned
revision when the repository is created.

Never use an unpinned moving branch in pre-commit configuration.


# 109. Reference GitHub Actions Workflow

The exact action versions should be pinned to approved tags or commit SHAs.

```yaml
name: ci

on:
  pull_request:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true

      - name: Set up Python
        run: uv python install 3.13

      - name: Synchronize environment
        run: uv sync --locked --all-groups

      - name: Check formatting
        run: uv run ruff format --check .

      - name: Lint
        run: uv run ruff check .

      - name: Type check
        run: uv run mypy src

      - name: Test
        run: >
          uv run pytest
          --cov=src/pmrp
          --cov-branch
          --cov-report=term-missing
          --cov-report=xml

      - name: Build
        run: uv build
```

Production repositories should pin third-party actions more strictly according
to the supply-chain policy.


# 110. Reference Dockerfile

```dockerfile
FROM python:3.13-slim AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --locked --no-dev

FROM python:3.13-slim AS runtime

RUN useradd --create-home --uid 10001 pmrp

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:${PATH}"
ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

USER pmrp

CMD ["python", "-m", "pmrp.cli"]
```

Production should pin the uv image by digest rather than use `latest`.
The example is intentionally readable and must be hardened before release.


# 111. Reference Logging Setup

```python
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(*, json_logs: bool, level: str) -> None:
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer()
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        cache_logger_on_first_use=True,
    )
```

The production implementation should include centralized secret redaction and
validated log-level parsing.


# 112. Reference Exception Hierarchy

```python
class PmrpError(Exception):
    # Base class for platform errors.
    pass


class ConfigurationError(PmrpError):
    # Configuration is invalid or incomplete.
    pass


class AdapterError(PmrpError):
    # Base class for exchange-adapter errors.
    pass


class AdapterAuthenticationError(AdapterError):
    # Authentication failed and should not be retried blindly.
    pass


class AdapterRateLimitError(AdapterError):
    # The exchange rate limit was reached.
    pass


class AdapterTransportError(AdapterError):
    # A transient network or transport operation failed.
    pass


class StorageError(PmrpError):
    # A storage operation failed.
    pass


class ConcurrencyConflict(StorageError):
    # Optimistic concurrency detected a conflicting update.
    pass


class ExecutionError(PmrpError):
    # An execution operation failed.
    pass


class AmbiguousOrderSubmission(ExecutionError):
    # The client cannot determine whether the exchange accepted an order.
    pass


class InvariantViolation(PmrpError):
    # The platform entered or observed an impossible domain state.
    pass
```


# 113. Reference Clock Interface

```python
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        # Return the current timezone-aware UTC time.
        ...

    async def sleep(self, duration: timedelta) -> None:
        # Wait according to this clock's time model.
        ...
```

Production code should use separate monotonic measurement support where elapsed
time accuracy is required.


# 114. Reference Repository Protocol

```python
from __future__ import annotations

from typing import Protocol

from pmrp.domain.orders import Order
from pmrp.domain.types import OrderId


class OrderRepository(Protocol):
    async def get(self, order_id: OrderId) -> Order | None:
        ...

    async def add(self, order: Order) -> None:
        ...

    async def save(
        self,
        order: Order,
        *,
        expected_version: int,
    ) -> None:
        ...
```

Repository protocols expose domain operations rather than database details.


# 115. Reference Unit Test

```python
from decimal import Decimal

from pmrp.domain.orders import Fill, Order, OrderId
from pmrp.domain.types import Price, Quantity


def test_apply_fill_duplicate_fill_is_idempotent() -> None:
    order = Order.accepted(
        order_id=OrderId("ord_test"),
        quantity=Quantity(Decimal("10")),
        limit_price=Price(Decimal("0.45")),
    )
    fill = Fill(
        fill_id="fill_1",
        quantity=Quantity(Decimal("3")),
        price=Price(Decimal("0.44")),
    )

    order.apply_fill(fill)
    order.apply_fill(fill)

    assert order.filled_quantity == Quantity(Decimal("3"))
    assert order.remaining_quantity == Quantity(Decimal("7"))
```

The exact domain constructors will be defined in `03_SCHEMAS.md`.


# 116. Reference Property Test

```python
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from pmrp.domain.types import Probability


@given(
    st.decimals(
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_probability_accepts_values_in_closed_unit_interval(
    value: Decimal,
) -> None:
    probability = Probability(value)

    assert Decimal("0") <= probability.value <= Decimal("1")
```


# 117. Reference Test Fixture Builder

```python
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from pmrp.domain.market_data import OrderBookSnapshot


def an_order_book_snapshot(**changes: object) -> OrderBookSnapshot:
    base = OrderBookSnapshot(
        market_id="mkt_test",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        bids=((Decimal("0.40"), Decimal("10")),),
        asks=((Decimal("0.42"), Decimal("8")),),
        sequence=1,
    )
    return replace(base, **changes)
```

Builders should make the important test difference visible at the call site.


# 118. Reference ADR Template

```text
# ADR-NNN: Decision Title

- Status: Proposed
- Date: YYYY-MM-DD
- Owners: Names or team
- Related issues: Links or identifiers

## Context

Describe the problem, constraints, and forces.

## Decision

State the decision precisely.

## Alternatives Considered

Describe viable alternatives and why they were not selected.

## Consequences

Describe positive, negative, and neutral consequences.

## Migration

Describe implementation and compatibility steps.

## Validation

Describe how the decision will be tested or measured.
```


# 119. Reference Pull Request Template

```text
## Summary

What does this change do?

## Motivation

Why is it needed?

## Architecture

Which components and interfaces are affected?

## Risk and Safety

Does this affect execution, risk, accounting, secrets, or live trading?

## Data and Migration

Are schemas, migrations, fixtures, or backfills involved?

## Replay and Determinism

Does expected replay output change?

## Testing

What tests were added or run?

## Operations

Are metrics, logs, alerts, runbooks, or deployment steps required?

## Checklist

- [ ] Formatting and linting pass.
- [ ] Static typing passes.
- [ ] Tests pass.
- [ ] Documentation is updated.
- [ ] No secrets are included.
```


# 120. Reference Security Policy Outline

`SECURITY.md` should include:

- supported versions
- private reporting channel
- expected response process
- disclosure policy
- excluded public issue content
- secret-leak instructions
- dependency vulnerability process
- safe-harbor statement if adopted

Do not ask security reporters to publish exploit details in a public issue.


# 121. Reference Code Owners

High-risk areas may require designated reviewers.

Example conceptual ownership:

```text
/src/pmrp/execution/      execution maintainers
/src/pmrp/risk/           risk maintainers
/src/pmrp/portfolio/      accounting maintainers
/src/pmrp/adapters/       adapter maintainers
/migrations/              database maintainers
/.github/workflows/       repository maintainers
/docs/adr/                architecture maintainers
```

The actual CODEOWNERS syntax should use repository usernames or teams.


# 122. Review Heuristics for Financial Logic

For every financial calculation, reviewers should ask:

- What are the units?
- What is the sign convention?
- What is the rounding rule?
- Where does precision change?
- How are fees treated?
- What happens at zero?
- What happens at limits?
- Is the calculation idempotent?
- Does the result reconcile?
- Is float involved?
- Is there a property test?
- Is there a realistic fixture?


# 123. Review Heuristics for Async Code

For every asynchronous component, reviewers should ask:

- Who owns this task?
- How is it stopped?
- What happens on cancellation?
- Is the queue bounded?
- Is there a timeout?
- Can work be duplicated?
- Is ordering required?
- Can a slow dependency block unrelated work?
- What health metric exposes failure?
- Are tasks leaked in tests?


# 124. Review Heuristics for Exchange Code

For every exchange integration, reviewers should ask:

- Is the raw payload preserved?
- Are timestamps correctly mapped?
- Are units explicit?
- Are enums complete?
- Are unknown values handled?
- Is rate limiting centralized?
- Are retries safe?
- Is submission ambiguity handled?
- Is reconnect followed by reconciliation?
- Are secrets redacted?
- Are fixtures realistic?
- Does the adapter pass the common contract?


# 125. Review Heuristics for Replay

For replay changes, reviewers should ask:

- Is ordering stable?
- Is time injected?
- Is randomness seeded?
- Is serialization stable?
- Are database queries ordered?
- Does the change alter golden output?
- Is the dataset checksum pinned?
- Are live side effects impossible?
- Can the result be reproduced from the manifest?


# 126. Review Heuristics for Risk

For risk changes, reviewers should ask:

- What input can be stale?
- What happens when input is missing?
- Is the rule fail closed?
- Are units exact?
- Is the reason code stable?
- Is the decision recorded?
- Is the limit scoped correctly?
- Can concurrent orders exceed the limit?
- Is the check repeated at the right stage?
- Are kill-switch interactions tested?


# 127. Engineering Anti-Patterns

Prohibited or strongly discouraged patterns:

- strategy code importing an exchange SDK
- money represented as float
- direct `datetime.now()` in replayable logic
- unbounded async queues
- broad `except Exception: pass`
- retry loops without deadlines
- status fields mutated outside a state machine
- database sessions passed into strategies
- configuration read from environment throughout the codebase
- global mutable service singletons
- live mode inferred from credentials
- secret values in exceptions or logs
- tests that sleep for timing
- unordered database reads affecting behavior
- unchecked dictionaries for canonical schemas
- one giant `utils.py`
- silent normalization coercion
- editing historical events in place
- generating duplicate orders on retry


# 128. Exception Process

A standard may be temporarily violated only when:

- the reason is documented
- the scope is narrow
- risk is understood
- tests protect the exception
- an owner is assigned
- removal criteria are defined

Use:

- ADR for architectural exceptions
- issue for bounded technical debt
- code comment for local unavoidable workaround

Do not normalize exceptions into permanent undocumented behavior.


# 129. Governance and Maintenance

This document should be reviewed:

- before the first live release
- after major incidents
- when the runtime or core tooling changes
- when a major architecture change is approved
- at least annually while the project is active

Changes to this document should be reviewed by maintainers responsible for the
affected areas.

Engineering standards should evolve from evidence, not fashion.


# 130. Final Engineering Position

The engineering system should make the platform boring in the best possible
sense.

Market-data ingestion should be predictable.

Replay should be deterministic.

Order transitions should be explicit.

Risk decisions should be explainable.

Portfolio state should reconcile.

Deployments should be repeatable.

Failures should be observable.

Contributors should know how to validate their work.

The platform's research value depends on trustworthy infrastructure.

The platform's live-trading safety depends on disciplined engineering.

These standards exist to protect both.
