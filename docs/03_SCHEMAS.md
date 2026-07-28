# Prediction Market Research Platform

## Canonical Schemas and Data Contracts

- Document: `03_SCHEMAS.md`
- Version: 1.0
- Status: Governing schema specification
- Related documents:
  - `01_ARCHITECTURE.md`
  - `02_ENGINEERING.md`
- Runtime: Python 3.13
- Validation library: Pydantic
- Financial numeric type: Decimal
- Character set: ASCII only
- Intended audience: maintainers, adapter developers, strategy developers, data engineers, reviewers, and coding agents

---

## Document Authority

This document defines the canonical data schemas for the Prediction Market
Research Platform, abbreviated as PMRP.

It governs:

- value objects
- identifiers
- enums
- canonical entities
- commands
- events
- snapshots
- state projections
- risk records
- portfolio records
- replay manifests
- simulation records
- model metadata
- API payloads
- serialization rules
- compatibility rules
- validation invariants

The schemas in this document are exchange independent.

Exchange-specific transport models belong inside adapter packages and must be
mapped into the canonical schemas defined here.

When a schema in this document conflicts with an approved Architecture Decision
Record, the newer approved decision governs and this document must be updated.

---

# 1. Executive Summary

PMRP uses canonical, versioned schemas to separate exchange-specific transport
details from platform-wide domain meaning.

Every external payload is treated as untrusted.

The canonical layer converts external data into validated, immutable objects
with explicit:

- identifiers
- timestamps
- units
- precision
- event versions
- correlation lineage
- quality flags
- ownership semantics

Canonical schemas serve four purposes:

1. runtime contracts
2. persistence contracts
3. replay contracts
4. integration contracts

The same schema definitions support:

- live ingestion
- paper trading
- shadow trading
- simulation
- historical replay
- research exports
- operator APIs
- tests

The schema system follows these core rules:

- Financial values use Decimal.
- Timestamps are timezone-aware UTC values.
- Canonical events are immutable.
- Every event has a schema version.
- Every event has an event ID.
- Every command has a command ID.
- Every business flow carries correlation and causation identifiers.
- External identifiers are preserved but never replace canonical identifiers.
- Unknown or unsupported external values are rejected or explicitly quarantined.
- Serialization is stable and exact.
- Schema evolution is explicit.


# 2. Schema Design Principles

## 2.1 Exchange Independence

A canonical schema must not embed exchange-specific field names, status strings,
or authentication details.

## 2.2 Exactness

Financial values must round-trip exactly through serialization.

## 2.3 Immutability

Events and value objects are immutable after construction.

## 2.4 Explicit Units

A field must make its unit obvious through:

- the type
- the field name
- the schema documentation

## 2.5 Explicit Time Semantics

A timestamp field must state what event it represents.

## 2.6 Versioned Contracts

Every public persisted or transmitted schema has a version.

## 2.7 Typed Absence

Use `None` for absent optional values.

Do not use:

- empty strings
- zero
- `"unknown"`
- sentinel numbers

unless those are valid domain values.

## 2.8 Stable Field Names

Persisted and transmitted field names are snake_case and stable.

## 2.9 No Hidden Coercion

Dangerous values should not be silently coerced.

Examples:

- `"abc"` must not become zero
- negative quantity must not become positive
- naive datetime must not silently become UTC
- float must not silently become Decimal

## 2.10 Domain Ownership

A schema should live in the package that owns its meaning.

Shared envelope types may live in a lower-level schema package.


# 3. Schema Package Layout

Recommended source layout:

```text
src/pmrp/schemas/
|
+-- base.py
+-- identifiers.py
+-- enums.py
+-- numeric.py
+-- time.py
+-- metadata.py
+-- markets.py
+-- market_data.py
+-- orders.py
+-- fills.py
+-- portfolio.py
+-- risk.py
+-- strategy.py
+-- models.py
+-- matching.py
+-- replay.py
+-- simulation.py
+-- system.py
+-- commands.py
+-- events.py
+-- api.py
+-- serialization.py
+-- versions.py
```

Recommended domain ownership:

```text
src/pmrp/domain/
  types/
  markets/
  orders/
  portfolio/
  risk/
  strategy/
```

Pydantic transport and event schemas may live under `pmrp.schemas`.

Behavior-rich aggregates live under `pmrp.domain`.

The two layers may share enums and value objects when dependency direction
remains valid.


# 4. Base Pydantic Configuration

All canonical persisted schemas should inherit from a common base model.

Recommended configuration:

```python
from pydantic import BaseModel, ConfigDict


class CanonicalModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=False,
        validate_assignment=False,
        validate_default=True,
    )
```

Rationale:

- `extra="forbid"` rejects unknown fields at strict boundaries.
- `frozen=True` prevents mutation.
- `populate_by_name=True` supports controlled aliases.
- `validate_default=True` validates all defaults.

Adapter transport models may use different extra-field behavior when an
exchange frequently adds fields, but canonical models remain strict.


# 5. Serialization Rules

## 5.1 JSON Field Names

Use snake_case.

## 5.2 Decimal

Serialize Decimal as a string.

Example:

```json
{
  "price": "0.4200",
  "quantity": "15",
  "fee": "0.12"
}
```

## 5.3 Datetime

Serialize datetime in ISO 8601 UTC form.

Example:

```text
2026-07-27T14:03:12.123456Z
```

## 5.4 UUID and ULID

Serialize identifiers as lowercase strings.

## 5.5 Enum

Serialize enum values using stable lowercase strings.

## 5.6 Sets

Do not expose unordered sets in canonical serialized schemas.

Use sorted lists or tuples.

## 5.7 Binary Data

Binary payloads are stored as bytes or base64 only in transport or archive
records.

Canonical business events should not contain raw binary payloads.

## 5.8 Stable Serialization

Canonical hashing requires:

- sorted object keys
- exact Decimal strings
- normalized UTC timestamps
- explicit enum values
- no transient fields
- stable list ordering


# 6. Common Scalar Types

Recommended scalar aliases:

```python
from decimal import Decimal
from typing import Annotated

from pydantic import Field

NonNegativeDecimal = Annotated[
    Decimal,
    Field(ge=Decimal("0")),
]

PositiveDecimal = Annotated[
    Decimal,
    Field(gt=Decimal("0")),
]

ProbabilityDecimal = Annotated[
    Decimal,
    Field(ge=Decimal("0"), le=Decimal("1")),
]

NonNegativeInt = Annotated[int, Field(ge=0)]

PositiveInt = Annotated[int, Field(gt=0)]

SchemaVersion = Annotated[int, Field(ge=1)]
```

Prefer named value objects when business semantics require more than a numeric
range.


# 7. Identifier Types

The platform uses typed identifiers.

Recommended definitions:

```python
from typing import NewType

EventId = NewType("EventId", str)
CommandId = NewType("CommandId", str)
CorrelationId = NewType("CorrelationId", str)
CausationId = NewType("CausationId", str)
TraceId = NewType("TraceId", str)

ExchangeId = NewType("ExchangeId", str)
AccountId = NewType("AccountId", str)
MarketId = NewType("MarketId", str)
OutcomeId = NewType("OutcomeId", str)
ContractId = NewType("ContractId", str)
OrderId = NewType("OrderId", str)
FillId = NewType("FillId", str)
PositionId = NewType("PositionId", str)
StrategyId = NewType("StrategyId", str)
SignalId = NewType("SignalId", str)
IntentId = NewType("IntentId", str)
RiskDecisionId = NewType("RiskDecisionId", str)
ReplaySessionId = NewType("ReplaySessionId", str)
SimulationSessionId = NewType("SimulationSessionId", str)
ExperimentId = NewType("ExperimentId", str)
ModelId = NewType("ModelId", str)
FeatureSnapshotId = NewType("FeatureSnapshotId", str)
RelationshipId = NewType("RelationshipId", str)
SettlementId = NewType("SettlementId", str)
```

Identifiers should be validated for:

- nonempty value
- supported prefix
- supported character set
- maximum length

Recommended prefixes:

```text
evt_
cmd_
corr_
cause_
xchg_
acct_
mkt_
out_
ctr_
ord_
fill_
pos_
strat_
sig_
intent_
risk_
rpl_
sim_
exp_
mdl_
feat_
rel_
set_
```


# 8. Exchange Identifier Schemas

```python
from pydantic import Field


class ExchangeRef(CanonicalModel):
    exchange: str = Field(min_length=1, max_length=64)
    environment: str = Field(min_length=1, max_length=32)


class ExchangeAccountRef(CanonicalModel):
    exchange: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=256)
    environment: str = Field(min_length=1, max_length=32)


class ExternalMarketRef(CanonicalModel):
    exchange: str
    exchange_market_id: str
    exchange_event_id: str | None = None


class ExternalOrderRef(CanonicalModel):
    exchange: str
    exchange_order_id: str
    client_order_id: str | None = None
```

External IDs are opaque strings.

The platform must not parse hidden semantics from them unless an adapter owns
that parsing.


# 9. Core Enums

Recommended core enums:

```python
from enum import StrEnum


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    DEVELOPMENT = "development"
    STAGING = "staging"
    SHADOW = "shadow"
    PRODUCTION = "production"


class ExchangeName(StrEnum):
    KALSHI = "kalshi"
    POLYMARKET = "polymarket"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class LiquidityRole(StrEnum):
    MAKER = "maker"
    TAKER = "taker"
    UNKNOWN = "unknown"


class OutcomeType(StrEnum):
    BINARY = "binary"
    CATEGORICAL = "categorical"
    NUMERIC_RANGE = "numeric_range"
    SCALAR = "scalar"


class MarketStatus(StrEnum):
    DISCOVERED = "discovered"
    OPEN = "open"
    HALTED = "halted"
    CLOSED = "closed"
    PENDING_RESOLUTION = "pending_resolution"
    RESOLVED = "resolved"
    FINALIZED = "finalized"
    SETTLED = "settled"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class OrderType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"


class TimeInForce(StrEnum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"
    DAY = "day"
    GTD = "gtd"


class OrderStatus(StrEnum):
    CREATED = "created"
    RISK_PENDING = "risk_pending"
    APPROVED = "approved"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    LOST = "lost"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class RiskDecisionStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


class StrategyState(StrEnum):
    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    DEGRADED = "degraded"
    DRAINING = "draining"
    STOPPED = "stopped"
    FAILED = "failed"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
```


# 10. Data Quality Enums

```python
class DataQualityFlag(StrEnum):
    DELAYED = "delayed"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    INFERRED = "inferred"
    SNAPSHOT_RECOVERY = "snapshot_recovery"
    INCOMPLETE = "incomplete"
    STALE = "stale"
    CORRECTED = "corrected"
    SIMULATED = "simulated"
    REPLAYED = "replayed"
    EXCHANGE_ESTIMATED = "exchange_estimated"


class DataQualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class DataQualityAction(StrEnum):
    ACCEPT = "accept"
    ACCEPT_WITH_FLAG = "accept_with_flag"
    QUARANTINE = "quarantine"
    DROP = "drop"
    INVALIDATE_PROJECTION = "invalidate_projection"
    BLOCK_TRADING = "block_trading"
```


# 11. Financial Value Objects

Recommended immutable value objects:

```python
from decimal import Decimal

from pydantic import Field, field_validator


class Price(CanonicalModel):
    value: Decimal = Field(ge=Decimal("0"))
    currency: str = "USD"

    @field_validator("value", mode="before")
    @classmethod
    def reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("float is not accepted for Price")
        return value


class Probability(CanonicalModel):
    value: Decimal = Field(
        ge=Decimal("0"),
        le=Decimal("1"),
    )

    @field_validator("value", mode="before")
    @classmethod
    def reject_float(cls, value: object) -> object:
        if isinstance(value, float):
            raise TypeError("float is not accepted for Probability")
        return value


class Quantity(CanonicalModel):
    value: Decimal = Field(ge=Decimal("0"))


class Money(CanonicalModel):
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)


class Fee(CanonicalModel):
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    fee_type: str


class BasisPoints(CanonicalModel):
    value: Decimal
```

The sign convention for Money and Fee must be documented by the containing
schema.

Example:

- cash change may be positive or negative
- charged fee is normally positive
- accounting journal line may use signed values


# 12. Tick and Precision Schemas

```python
class TickSize(CanonicalModel):
    value: Decimal = Field(gt=Decimal("0"))


class QuantityIncrement(CanonicalModel):
    value: Decimal = Field(gt=Decimal("0"))


class PrecisionRules(CanonicalModel):
    price_tick: Decimal = Field(gt=Decimal("0"))
    quantity_increment: Decimal = Field(gt=Decimal("0"))
    money_increment: Decimal = Field(gt=Decimal("0"))
    price_rounding_mode: str
    quantity_rounding_mode: str
    money_rounding_mode: str
```

Precision rules are exchange and market specific.

They should be attached to market metadata or exchange capabilities.


# 13. Common Metadata Schemas

```python
from datetime import datetime
from typing import Any


class SourceMetadata(CanonicalModel):
    producer: str
    source_type: str
    exchange: str | None = None
    connection_id: str | None = None
    endpoint: str | None = None
    channel: str | None = None
    parser_version: str | None = None
    mapper_version: str | None = None


class VersionMetadata(CanonicalModel):
    schema_version: int = Field(ge=1)
    code_version: str | None = None
    model_version: str | None = None
    strategy_version: str | None = None
    configuration_hash: str | None = None


class AuditMetadata(CanonicalModel):
    created_at: datetime
    created_by: str
    updated_at: datetime | None = None
    updated_by: str | None = None


class FlexibleMetadata(CanonicalModel):
    values: dict[str, Any] = Field(default_factory=dict)
```

Flexible metadata is not a substitute for required typed fields.

It should contain only noncritical extensibility data.


# 14. Event Envelope

Every canonical event uses the following envelope.

```python
from datetime import datetime
from typing import Any

from pydantic import Field


class EventEnvelope(CanonicalModel):
    event_id: str
    event_type: str = Field(min_length=1, max_length=128)
    schema_version: int = Field(ge=1)

    occurred_at: datetime
    received_at: datetime
    published_at: datetime

    producer: str
    exchange: str | None = None
    market_id: str | None = None
    account_id: str | None = None
    strategy_id: str | None = None
    order_id: str | None = None

    correlation_id: str
    causation_id: str | None = None
    trace_id: str | None = None

    replay_session_id: str | None = None
    simulation_session_id: str | None = None

    quality_flags: tuple[DataQualityFlag, ...] = ()
    attributes: dict[str, Any] = Field(default_factory=dict)
```

Event ordering does not rely on `published_at` alone.

The replay ordering policy is defined separately.


# 15. Command Envelope

```python
from datetime import datetime
from typing import Any


class CommandEnvelope(CanonicalModel):
    command_id: str
    command_type: str
    schema_version: int = Field(ge=1)

    issued_at: datetime
    issuer: str

    correlation_id: str
    causation_id: str | None = None
    trace_id: str | None = None

    idempotency_key: str
    deadline_at: datetime | None = None
    priority: int = 0

    attributes: dict[str, Any] = Field(default_factory=dict)
```

Command payloads should be represented by typed command models, not embedded
untyped dictionaries.


# 16. Raw Exchange Record

```python
class RawExchangeRecord(CanonicalModel):
    raw_record_id: str
    exchange: str
    environment: str

    connection_id: str | None = None
    endpoint: str | None = None
    channel: str | None = None
    message_type: str | None = None

    received_at: datetime
    exchange_occurred_at: datetime | None = None

    sequence: int | None = None
    content_type: str = "application/json"
    compression: str | None = None

    payload_text: str | None = None
    payload_bytes_b64: str | None = None
    payload_hash: str

    parser_version: str | None = None
    transport_metadata: dict[str, str] = Field(default_factory=dict)
```

Exactly one of `payload_text` or `payload_bytes_b64` should be populated.

A model validator should enforce this invariant.


# 17. Market Schema

```python
class Market(CanonicalModel):
    market_id: str
    canonical_event_id: str | None = None

    exchange: str
    exchange_market_id: str
    exchange_event_id: str | None = None

    title: str
    subtitle: str | None = None
    description: str | None = None
    category: str | None = None
    tags: tuple[str, ...] = ()

    outcome_type: OutcomeType
    status: MarketStatus

    opens_at: datetime | None = None
    closes_at: datetime | None = None
    resolves_at: datetime | None = None
    finalized_at: datetime | None = None

    currency: str = "USD"
    payout_per_unit: Decimal = Decimal("1")

    tick_size: Decimal
    quantity_increment: Decimal

    rules_text: str | None = None
    rules_url: str | None = None

    created_at: datetime
    updated_at: datetime
```

Market title and rules text are informational.

Trading equivalence must not be inferred from title alone.


# 18. Outcome Schema

```python
class Outcome(CanonicalModel):
    outcome_id: str
    market_id: str

    exchange_outcome_id: str | None = None

    name: str
    normalized_name: str
    index: int

    is_tradeable: bool = True
    is_winning: bool | None = None

    payout_per_unit: Decimal = Decimal("1")
    metadata: dict[str, str] = Field(default_factory=dict)
```

For binary markets, common normalized outcome names are:

- yes
- no

The canonical platform should still model outcomes explicitly.


# 19. Contract Schema

```python
class Contract(CanonicalModel):
    contract_id: str
    market_id: str
    outcome_id: str

    exchange_contract_id: str | None = None

    symbol: str | None = None
    display_name: str

    tick_size: Decimal
    quantity_increment: Decimal
    min_order_quantity: Decimal | None = None
    max_order_quantity: Decimal | None = None

    active: bool
    created_at: datetime
    updated_at: datetime
```

A contract represents the directly tradeable instrument associated with an
outcome.


# 20. Market Lifecycle Update

```python
class MarketLifecycleUpdate(CanonicalModel):
    market_id: str
    previous_status: MarketStatus | None
    current_status: MarketStatus

    effective_at: datetime
    reason_code: str | None = None
    reason_text: str | None = None

    exchange_status: str | None = None
```

A status transition should be validated against allowed lifecycle transitions.


# 21. Market Catalog Snapshot

```python
class MarketCatalogSnapshot(CanonicalModel):
    snapshot_id: str
    exchange: str
    captured_at: datetime

    markets: tuple[Market, ...]
    next_cursor: str | None = None

    source_count: int
    normalized_count: int
    rejected_count: int
```

Large production snapshots may be stored as a manifest plus object-store
reference rather than one serialized payload.


# 22. Order Book Level

```python
class OrderBookLevel(CanonicalModel):
    price: Decimal = Field(ge=Decimal("0"))
    quantity: Decimal = Field(ge=Decimal("0"))
    order_count: int | None = Field(default=None, ge=0)
```

Order-book levels must be sorted:

- bids descending by price
- asks ascending by price

Duplicate prices must be aggregated or rejected according to the normalizer
policy.


# 23. Order Book Snapshot

```python
class OrderBookSnapshot(CanonicalModel):
    market_id: str
    contract_id: str
    exchange: str

    sequence: int | None = None
    exchange_occurred_at: datetime | None = None
    received_at: datetime

    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]

    is_valid: bool = True
    snapshot_reason: str = "initial"
```

Invariants:

- bid prices are strictly descending
- ask prices are strictly ascending
- quantities are positive
- crossed books require an explicit quality flag or exchange rule


# 24. Order Book Delta

```python
class OrderBookDeltaAction(StrEnum):
    UPSERT = "upsert"
    DELETE = "delete"


class OrderBookDeltaLevel(CanonicalModel):
    side: Side
    price: Decimal
    quantity: Decimal
    action: OrderBookDeltaAction


class OrderBookDelta(CanonicalModel):
    market_id: str
    contract_id: str
    exchange: str

    sequence: int | None = None
    previous_sequence: int | None = None

    exchange_occurred_at: datetime | None = None
    received_at: datetime

    changes: tuple[OrderBookDeltaLevel, ...]
```

A delete action should normally use quantity zero.

The adapter mapper must document exchange-specific delta semantics.


# 25. Best Quote Schema

```python
class BestQuote(CanonicalModel):
    market_id: str
    contract_id: str
    exchange: str

    bid_price: Decimal | None = None
    bid_quantity: Decimal | None = None
    ask_price: Decimal | None = None
    ask_quantity: Decimal | None = None

    midpoint: Decimal | None = None
    spread: Decimal | None = None

    occurred_at: datetime
    book_sequence: int | None = None
```

Midpoint exists only when both bid and ask exist.

Spread must be nonnegative unless the exchange temporarily reports a crossed
book.


# 26. Trade Schema

```python
class Trade(CanonicalModel):
    trade_id: str
    exchange: str
    exchange_trade_id: str

    market_id: str
    contract_id: str
    outcome_id: str

    price: Decimal
    quantity: Decimal

    aggressor_side: Side | None = None
    liquidity_role: LiquidityRole = LiquidityRole.UNKNOWN

    exchange_occurred_at: datetime
    received_at: datetime

    sequence: int | None = None
```

A canonical trade represents an observed execution.

It does not imply that the local account participated.


# 27. Candle Schema

```python
class CandleInterval(StrEnum):
    ONE_SECOND = "1s"
    FIVE_SECONDS = "5s"
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"


class Candle(CanonicalModel):
    market_id: str
    contract_id: str
    exchange: str

    interval: CandleInterval
    starts_at: datetime
    ends_at: datetime

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal

    volume: Decimal
    trade_count: int
    vwap: Decimal | None = None

    is_complete: bool
```

Candles are derived projections, not source-of-truth market events.


# 28. Market Statistics Schema

```python
class MarketStatistics(CanonicalModel):
    market_id: str
    contract_id: str
    exchange: str
    measured_at: datetime

    last_price: Decimal | None = None
    volume_24h: Decimal | None = None
    open_interest: Decimal | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    midpoint: Decimal | None = None
    spread: Decimal | None = None
    volatility_estimate: Decimal | None = None
```

Derived statistics must include calculation version metadata when persisted.


# 29. Strategy Definition Schema

```python
class StrategyDefinition(CanonicalModel):
    strategy_type: str
    version: str

    implementation_path: str
    description: str | None = None

    configuration_schema_version: int
    subscribed_event_types: tuple[str, ...]

    supports_replay: bool
    supports_simulation: bool
    supports_paper: bool
    supports_shadow: bool
    supports_live: bool
```


# 30. Strategy Instance Schema

```python
class StrategyInstance(CanonicalModel):
    strategy_id: str
    strategy_type: str
    strategy_version: str

    name: str
    environment: Environment
    state: StrategyState

    configuration_version: int
    configuration_hash: str
    capital_allocation: Money | None = None

    created_at: datetime
    started_at: datetime | None = None
    stopped_at: datetime | None = None

    health_status: HealthStatus
    health_message: str | None = None
```


# 31. Strategy Configuration Record

```python
class StrategyConfigurationRecord(CanonicalModel):
    strategy_id: str
    configuration_version: int
    effective_at: datetime

    configuration: dict[str, object]
    configuration_hash: str

    created_by: str
    approved_by: str | None = None
    approval_required: bool = False
```

Configuration dictionaries are allowed here because the strategy-specific
Pydantic schema performs validation before the record is accepted.


# 32. Signal Schema

```python
class SignalDirection(StrEnum):
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"
    BUY = "buy"
    SELL = "sell"


class Signal(CanonicalModel):
    signal_id: str
    strategy_id: str

    market_id: str
    contract_id: str | None = None
    outcome_id: str | None = None

    signal_type: str
    direction: SignalDirection

    strength: Decimal | None = None
    fair_probability: Decimal | None = None
    confidence: Decimal | None = None

    valid_from: datetime
    valid_until: datetime | None = None

    model_id: str | None = None
    model_version: str | None = None
    feature_snapshot_id: str | None = None

    reason_code: str
    reason_text: str | None = None

    correlation_id: str
```

Signal strength semantics must be defined by the strategy.


# 33. Model Prediction Schema

```python
class ModelPrediction(CanonicalModel):
    prediction_id: str
    model_id: str
    model_version: str

    market_id: str
    outcome_id: str | None = None

    predicted_probability: Decimal | None = None
    predicted_value: Decimal | None = None
    confidence: Decimal | None = None

    feature_snapshot_id: str
    generated_at: datetime

    horizon_seconds: int | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
```


# 34. Feature Definition Schema

```python
class FeatureDefinition(CanonicalModel):
    feature_name: str
    feature_version: str

    description: str
    unit: str | None = None
    dtype: str

    input_event_types: tuple[str, ...]
    window_definition: str | None = None
    minimum_observations: int | None = None

    null_policy: str
    leakage_reviewed: bool
```


# 35. Feature Value and Snapshot

```python
class FeatureValue(CanonicalModel):
    name: str
    version: str
    value_decimal: Decimal | None = None
    value_integer: int | None = None
    value_text: str | None = None
    value_boolean: bool | None = None
    is_missing: bool = False


class FeatureSnapshot(CanonicalModel):
    feature_snapshot_id: str
    market_id: str
    strategy_id: str | None = None

    observed_at: datetime
    generated_at: datetime

    features: tuple[FeatureValue, ...]
    source_event_ids: tuple[str, ...]

    schema_version: int
    calculation_version: str
```

Exactly one typed value field should be populated unless `is_missing` is true.


# 36. Order Intent Schema

```python
class OrderIntent(CanonicalModel):
    intent_id: str
    strategy_id: str

    market_id: str
    contract_id: str
    outcome_id: str

    side: Side
    quantity: Decimal
    limit_price: Decimal | None = None

    order_type: OrderType = OrderType.LIMIT
    time_in_force: TimeInForce = TimeInForce.GTC

    post_only: bool = False
    reduce_only: bool = False

    urgency: Decimal | None = None

    created_at: datetime
    expires_at: datetime | None = None

    signal_ids: tuple[str, ...] = ()
    correlation_id: str
    idempotency_key: str
```

Invariants:

- limit orders require `limit_price`
- market orders must not require `limit_price`
- quantity must be positive
- post-only is invalid for market orders


# 37. Approved Order Schema

```python
class ApprovedOrder(CanonicalModel):
    order_id: str
    intent_id: str
    strategy_id: str

    risk_decision_id: str

    exchange: str
    account_id: str

    market_id: str
    contract_id: str
    outcome_id: str

    side: Side
    quantity: Decimal
    limit_price: Decimal | None

    order_type: OrderType
    time_in_force: TimeInForce

    post_only: bool
    reduce_only: bool

    approved_at: datetime
    approval_expires_at: datetime | None = None

    client_order_id: str
    idempotency_key: str
    correlation_id: str
```


# 38. Order Schema

```python
class Order(CanonicalModel):
    order_id: str
    intent_id: str | None = None
    strategy_id: str | None = None
    risk_decision_id: str | None = None

    exchange: str
    account_id: str

    market_id: str
    contract_id: str
    outcome_id: str

    side: Side
    quantity: Decimal
    filled_quantity: Decimal
    remaining_quantity: Decimal

    limit_price: Decimal | None
    average_fill_price: Decimal | None

    order_type: OrderType
    time_in_force: TimeInForce

    post_only: bool
    reduce_only: bool

    status: OrderStatus

    client_order_id: str
    exchange_order_id: str | None = None

    created_at: datetime
    submitted_at: datetime | None = None
    accepted_at: datetime | None = None
    last_updated_at: datetime

    expires_at: datetime | None = None

    aggregate_version: int = Field(ge=0)
```

Invariants:

```text
filled_quantity >= 0
remaining_quantity >= 0
filled_quantity + remaining_quantity == quantity
average_fill_price is required when filled_quantity > 0
```


# 39. Order Submission Request

```python
class ExchangeOrderRequest(CanonicalModel):
    order_id: str
    client_order_id: str

    exchange: str
    account_id: str

    exchange_market_id: str
    exchange_contract_id: str | None = None

    side: Side
    quantity: Decimal
    limit_price: Decimal | None

    order_type: OrderType
    time_in_force: TimeInForce

    post_only: bool
    reduce_only: bool

    idempotency_key: str
    submitted_at: datetime
```

This schema is canonical infrastructure input.

The adapter maps it to an exchange-specific request.


# 40. Order Acknowledgement

```python
class ExchangeOrderAcknowledgement(CanonicalModel):
    order_id: str
    client_order_id: str
    exchange_order_id: str | None = None

    exchange: str
    account_id: str

    accepted: bool
    exchange_status: str | None = None
    rejection_code: str | None = None
    rejection_message: str | None = None

    acknowledged_at: datetime
    exchange_occurred_at: datetime | None = None
```


# 41. Cancel Request and Acknowledgement

```python
class CancelOrderRequest(CanonicalModel):
    cancel_request_id: str
    order_id: str

    exchange: str
    account_id: str

    client_order_id: str
    exchange_order_id: str | None = None

    requested_at: datetime
    idempotency_key: str
    correlation_id: str


class CancelOrderAcknowledgement(CanonicalModel):
    cancel_request_id: str
    order_id: str

    exchange: str
    account_id: str

    accepted: bool
    exchange_status: str | None = None
    rejection_code: str | None = None
    rejection_message: str | None = None

    acknowledged_at: datetime
```


# 42. Replace Order Request

```python
class ReplaceOrderRequest(CanonicalModel):
    replace_request_id: str
    order_id: str

    new_quantity: Decimal | None = None
    new_limit_price: Decimal | None = None
    new_expires_at: datetime | None = None

    requested_at: datetime
    idempotency_key: str
    correlation_id: str
```

If an exchange does not support atomic replacement, the execution engine may
implement cancel-and-new behavior while preserving lineage.


# 43. Fill Schema

```python
class Fill(CanonicalModel):
    fill_id: str
    exchange_fill_id: str

    order_id: str
    exchange_order_id: str | None = None
    client_order_id: str

    exchange: str
    account_id: str

    market_id: str
    contract_id: str
    outcome_id: str

    side: Side
    price: Decimal
    quantity: Decimal

    liquidity_role: LiquidityRole
    fee: Money | None = None
    rebate: Money | None = None

    exchange_occurred_at: datetime
    received_at: datetime

    trade_id: str | None = None
```

A fill quantity must be positive.

A fill ID must be unique within the exchange account.


# 44. Order State Transition Record

```python
class OrderStateTransition(CanonicalModel):
    transition_id: str
    order_id: str

    previous_status: OrderStatus | None
    current_status: OrderStatus

    occurred_at: datetime
    source_event_id: str

    reason_code: str | None = None
    reason_text: str | None = None

    aggregate_version_before: int
    aggregate_version_after: int
```


# 45. Open Order Snapshot

```python
class OpenOrderSnapshot(CanonicalModel):
    snapshot_id: str
    exchange: str
    account_id: str
    captured_at: datetime

    orders: tuple[Order, ...]
    source_count: int
    normalized_count: int
    rejected_count: int
```


# 46. Position Schema

```python
class Position(CanonicalModel):
    position_id: str

    exchange: str
    account_id: str

    market_id: str
    contract_id: str
    outcome_id: str

    quantity: Decimal
    average_entry_price: Decimal | None = None

    realized_pnl: Money
    unrealized_pnl: Money

    fees_paid: Money
    rebates_received: Money

    opened_at: datetime | None = None
    last_updated_at: datetime

    aggregate_version: int = Field(ge=0)
```

Position sign convention:

- positive quantity means net long
- negative quantity means net short

If an exchange does not support short contracts directly, the canonical model
still represents economic direction consistently.


# 47. Position Lot Schema

```python
class PositionLot(CanonicalModel):
    lot_id: str
    position_id: str

    source_fill_id: str
    quantity: Decimal
    remaining_quantity: Decimal

    entry_price: Decimal
    opened_at: datetime

    strategy_id: str | None = None
```

Lot tracking is optional if average-cost accounting is sufficient.

The selected accounting method must be explicit.


# 48. Cash Balance Schema

```python
class CashBalance(CanonicalModel):
    balance_id: str

    exchange: str
    account_id: str
    currency: str

    available: Decimal
    reserved: Decimal
    total: Decimal

    captured_at: datetime
```

Invariant:

```text
available + reserved == total
```

Exchange definitions may differ.

Adapter mapping must document semantics.


# 49. Portfolio Snapshot

```python
class PortfolioSnapshot(CanonicalModel):
    portfolio_id: str
    captured_at: datetime

    positions: tuple[Position, ...]
    balances: tuple[CashBalance, ...]

    realized_pnl: tuple[Money, ...]
    unrealized_pnl: tuple[Money, ...]

    gross_exposure: tuple[Money, ...]
    net_exposure: tuple[Money, ...]

    reconciliation_status: str
```


# 50. Accounting Journal Entry

```python
class JournalLine(CanonicalModel):
    account_code: str
    amount: Decimal
    currency: str
    description: str | None = None


class AccountingJournalEntry(CanonicalModel):
    journal_entry_id: str
    occurred_at: datetime

    source_event_id: str
    reference_type: str
    reference_id: str

    lines: tuple[JournalLine, ...]
    description: str

    created_at: datetime
```

For each currency, journal lines must sum to zero.

This provides a double-entry audit layer.


# 51. PnL Attribution Schema

```python
class PnlAttribution(CanonicalModel):
    attribution_id: str

    strategy_id: str | None = None
    market_id: str | None = None
    exchange: str | None = None

    starts_at: datetime
    ends_at: datetime

    realized_trading_pnl: Money
    unrealized_pnl_change: Money
    fees: Money
    rebates: Money
    slippage: Money | None = None
    settlement_pnl: Money | None = None

    total_pnl: Money
    calculation_version: str
```


# 52. Settlement Schema

```python
class SettlementStatus(StrEnum):
    UNRESOLVED = "unresolved"
    PENDING_RESOLUTION = "pending_resolution"
    RESOLVED = "resolved"
    DISPUTED = "disputed"
    FINALIZED = "finalized"
    SETTLED = "settled"
    CORRECTED = "corrected"


class Settlement(CanonicalModel):
    settlement_id: str
    market_id: str
    exchange: str

    status: SettlementStatus
    winning_outcome_ids: tuple[str, ...]

    resolved_at: datetime | None = None
    finalized_at: datetime | None = None
    settled_at: datetime | None = None

    payout_per_unit: Decimal | None = None
    source: str
    source_reference: str | None = None

    correction_of_settlement_id: str | None = None
```


# 53. Risk Limit Schema

```python
class RiskLimitScope(StrEnum):
    GLOBAL = "global"
    EXCHANGE = "exchange"
    ACCOUNT = "account"
    STRATEGY = "strategy"
    MARKET = "market"


class RiskLimit(CanonicalModel):
    risk_limit_id: str
    rule_id: str
    rule_version: str

    scope: RiskLimitScope
    scope_id: str | None = None

    limit_type: str
    limit_value: Decimal
    unit: str

    effective_at: datetime
    expires_at: datetime | None = None

    enabled: bool
    created_by: str
    approved_by: str | None = None
```


# 54. Risk Input Snapshot

```python
class RiskInputSnapshot(CanonicalModel):
    risk_input_snapshot_id: str
    captured_at: datetime

    strategy_id: str
    exchange: str
    account_id: str
    market_id: str

    current_position: Decimal
    open_order_quantity: Decimal
    available_balance: Decimal

    gross_exposure: Decimal
    net_exposure: Decimal
    daily_realized_pnl: Decimal
    daily_unrealized_pnl: Decimal

    market_data_age_ms: int
    reconciliation_healthy: bool
    kill_switch_clear: bool
```


# 55. Risk Rule Result

```python
class RiskRuleResult(CanonicalModel):
    rule_id: str
    rule_version: str

    passed: bool
    reason_code: str
    reason_text: str | None = None

    observed_value: Decimal | None = None
    limit_value: Decimal | None = None
    unit: str | None = None

    evaluated_at: datetime
```


# 56. Risk Decision Schema

```python
class RiskDecision(CanonicalModel):
    risk_decision_id: str
    intent_id: str

    status: RiskDecisionStatus
    evaluated_at: datetime

    input_snapshot_id: str
    rule_results: tuple[RiskRuleResult, ...]

    approved_quantity: Decimal | None = None
    approved_limit_price: Decimal | None = None
    approval_expires_at: datetime | None = None

    configuration_hash: str
    correlation_id: str
```

An approved decision may reduce quantity or alter limits only if policy permits
and the change is explicit.


# 57. Risk Breach Schema

```python
class RiskBreach(CanonicalModel):
    breach_id: str
    rule_id: str
    rule_version: str

    scope: RiskLimitScope
    scope_id: str | None = None

    severity: str
    detected_at: datetime

    observed_value: Decimal | None = None
    limit_value: Decimal | None = None
    unit: str | None = None

    action_taken: str
    correlation_id: str
```


# 58. Kill Switch Schema

```python
class KillSwitchScope(StrEnum):
    GLOBAL = "global"
    EXCHANGE = "exchange"
    ACCOUNT = "account"
    STRATEGY = "strategy"
    MARKET = "market"
    EXECUTION_GATEWAY = "execution_gateway"


class KillSwitchState(CanonicalModel):
    kill_switch_id: str
    scope: KillSwitchScope
    scope_id: str | None = None

    active: bool
    activated_at: datetime | None = None
    activated_by: str | None = None
    activation_reason: str | None = None

    released_at: datetime | None = None
    released_by: str | None = None
    release_reason: str | None = None

    version: int
```


# 59. Reconciliation Result

```python
class ReconciliationStatus(StrEnum):
    HEALTHY = "healthy"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"
    FAILED = "failed"


class ReconciliationMismatch(CanonicalModel):
    mismatch_id: str
    category: str

    local_value: str | None = None
    external_value: str | None = None

    severity: str
    explanation: str | None = None
    requires_manual_review: bool


class ReconciliationResult(CanonicalModel):
    reconciliation_id: str
    exchange: str
    account_id: str

    started_at: datetime
    completed_at: datetime

    status: ReconciliationStatus
    mismatches: tuple[ReconciliationMismatch, ...]

    open_orders_checked: int
    positions_checked: int
    balances_checked: int
    fills_checked: int

    trading_gate_released: bool
```


# 60. Market Relationship Schema

```python
class MarketRelationshipType(StrEnum):
    EQUIVALENT = "equivalent"
    COMPLEMENT = "complement"
    SUBSET = "subset"
    SUPERSET = "superset"
    MUTUALLY_EXCLUSIVE = "mutually_exclusive"
    CONDITIONALLY_EQUIVALENT = "conditionally_equivalent"
    CORRELATED = "correlated"
    UNRELATED = "unrelated"
    UNRESOLVED = "unresolved"


class MarketRelationship(CanonicalModel):
    relationship_id: str

    source_market_id: str
    target_market_id: str

    relationship_type: MarketRelationshipType
    confidence: Decimal

    valid_from: datetime
    valid_until: datetime | None = None

    evidence: tuple[str, ...]
    validator_version: str

    settlement_rule_match: bool | None = None
    human_review_status: str | None = None

    created_at: datetime
    updated_at: datetime
```


# 61. Matching Candidate Schema

```python
class MarketMatchCandidate(CanonicalModel):
    candidate_id: str

    source_market_id: str
    target_market_id: str

    metadata_score: Decimal | None = None
    embedding_score: Decimal | None = None
    rule_score: Decimal | None = None
    llm_score: Decimal | None = None

    proposed_relationship: MarketRelationshipType
    extracted_entities: tuple[str, ...] = ()
    extracted_dates: tuple[datetime, ...] = ()
    extracted_thresholds: tuple[str, ...] = ()

    generated_at: datetime
    pipeline_version: str
```


# 62. Matching Validation Result

```python
class MatchingValidationResult(CanonicalModel):
    validation_id: str
    candidate_id: str

    passed: bool
    relationship_type: MarketRelationshipType
    confidence: Decimal

    rule_results: tuple[RiskRuleResult, ...]
    requires_human_review: bool

    validated_at: datetime
    validator_version: str
```

Matching rule results may reuse a generic rule-result base type in the actual
implementation rather than the risk-specific name.


# 63. Arbitrage Opportunity Schema

```python
class ArbitrageLeg(CanonicalModel):
    leg_id: str
    exchange: str
    account_id: str

    market_id: str
    contract_id: str
    outcome_id: str

    side: Side
    quantity: Decimal
    expected_price: Decimal

    expected_fee: Decimal
    expected_slippage: Decimal


class ArbitrageOpportunity(CanonicalModel):
    opportunity_id: str
    relationship_id: str

    detected_at: datetime
    valid_until: datetime

    legs: tuple[ArbitrageLeg, ...]

    gross_edge: Decimal
    expected_fees: Decimal
    expected_slippage: Decimal
    expected_net_edge: Decimal

    maximum_unhedged_exposure: Decimal
    confidence: Decimal

    calculation_version: str
```


# 64. Arbitrage Execution Plan

```python
class ArbitrageExecutionPolicy(StrEnum):
    SIMULTANEOUS = "simultaneous"
    PRIMARY_THEN_HEDGE = "primary_then_hedge"
    PASSIVE_THEN_AGGRESSIVE = "passive_then_aggressive"
    INVENTORY_BACKED = "inventory_backed"


class ArbitrageExecutionPlan(CanonicalModel):
    plan_id: str
    opportunity_id: str

    policy: ArbitrageExecutionPolicy
    legs: tuple[ArbitrageLeg, ...]

    hedge_timeout_ms: int
    max_unhedged_quantity: Decimal
    cancel_on_partial_failure: bool

    created_at: datetime
    expires_at: datetime
```


# 65. Replay Manifest

```python
class ReplayManifest(CanonicalModel):
    replay_session_id: str

    dataset_id: str
    dataset_checksum: str

    starts_at: datetime
    ends_at: datetime

    speed: Decimal
    deterministic: bool
    random_seed: int

    event_ordering_policy_version: str

    strategy_versions: dict[str, str]
    model_versions: dict[str, str]

    configuration_hash: str
    code_commit: str
    dependency_lock_hash: str

    created_at: datetime
    created_by: str
```


# 66. Replay Session State

```python
class ReplayState(StrEnum):
    CREATED = "created"
    LOADING = "loading"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplaySession(CanonicalModel):
    replay_session_id: str
    manifest: ReplayManifest

    state: ReplayState

    current_time: datetime | None = None
    processed_events: int = 0
    rejected_events: int = 0

    started_at: datetime | None = None
    completed_at: datetime | None = None

    result_checksum: str | None = None
    failure_message: str | None = None
```


# 67. Replay Result Schema

```python
class ReplayResult(CanonicalModel):
    replay_session_id: str

    processed_events: int
    generated_signals: int
    generated_intents: int
    simulated_orders: int
    simulated_fills: int

    final_portfolio: PortfolioSnapshot
    metrics: dict[str, str]

    result_checksum: str
    completed_at: datetime
```


# 68. Simulation Configuration

```python
class SimulationConfiguration(CanonicalModel):
    simulation_version: str

    fill_model: str
    queue_model: str
    latency_model: str
    fee_model: str
    rejection_model: str
    slippage_model: str
    settlement_model: str

    random_seed: int

    fixed_latency_ms: int | None = None
    maker_fill_probability: Decimal | None = None
    taker_slippage_bps: Decimal | None = None

    parameters: dict[str, str] = Field(default_factory=dict)
```


# 69. Simulation Session

```python
class SimulationSession(CanonicalModel):
    simulation_session_id: str
    replay_session_id: str | None = None

    configuration: SimulationConfiguration

    state: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    result_checksum: str | None = None
```


# 70. Simulated Exchange Order

```python
class SimulatedExchangeOrder(CanonicalModel):
    simulated_order_id: str
    order_id: str

    accepted_at: datetime
    active_at: datetime

    queue_position: Decimal | None = None
    volume_ahead: Decimal | None = None

    status: OrderStatus
    configuration_version: str
```


# 71. Simulated Fill

```python
class SimulatedFill(CanonicalModel):
    simulated_fill_id: str
    order_id: str

    price: Decimal
    quantity: Decimal

    liquidity_role: LiquidityRole
    fee: Money | None = None

    occurred_at: datetime

    fill_reason: str
    source_market_event_ids: tuple[str, ...]
```


# 72. Experiment Manifest

```python
class ExperimentManifest(CanonicalModel):
    experiment_id: str

    name: str
    hypothesis: str
    owner: str

    dataset_id: str
    dataset_checksum: str

    code_commit: str
    dependency_lock_hash: str
    configuration_hash: str

    strategy_versions: dict[str, str]
    model_versions: dict[str, str]
    feature_versions: dict[str, str]

    random_seed: int

    created_at: datetime
```


# 73. Experiment Result

```python
class ExperimentMetric(CanonicalModel):
    name: str
    value: Decimal | int | str
    unit: str | None = None


class ExperimentResult(CanonicalModel):
    experiment_id: str

    started_at: datetime
    completed_at: datetime

    metrics: tuple[ExperimentMetric, ...]
    artifact_references: tuple[str, ...]

    result_checksum: str
    notes: str | None = None
    approved_for_next_stage: bool = False
```


# 74. Model Artifact Metadata

```python
class ModelArtifactMetadata(CanonicalModel):
    model_id: str
    model_name: str
    model_version: str

    artifact_uri: str
    artifact_checksum: str

    training_dataset_id: str
    training_dataset_checksum: str

    training_code_commit: str
    dependency_lock_hash: str

    feature_schema_version: str
    target_definition: str

    trained_at: datetime
    random_seed: int

    evaluation_metrics: dict[str, str]
    calibration_method: str | None = None

    approval_status: str
    approved_by: str | None = None
    approved_at: datetime | None = None
```


# 75. Service Health Schema

```python
class DependencyHealth(CanonicalModel):
    dependency: str
    status: HealthStatus
    message: str | None = None
    checked_at: datetime


class ServiceHealth(CanonicalModel):
    service: str
    component: str
    environment: Environment

    status: HealthStatus
    since: datetime

    summary: str
    last_success_at: datetime | None = None
    last_error_at: datetime | None = None

    dependencies: tuple[DependencyHealth, ...]

    trading_impact: str
    ready: bool
    alive: bool
```


# 76. Adapter Health Schema

```python
class AdapterHealth(CanonicalModel):
    exchange: str
    environment: Environment

    status: HealthStatus
    connected: bool
    authenticated: bool
    subscriptions_active: bool

    last_message_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    last_reconciliation_at: datetime | None = None

    market_data_fresh: bool
    trading_gate_open: bool

    reconnect_attempts: int
    message: str | None = None
```


# 77. Rate Limit Schema

```python
class RateLimitWindow(CanonicalModel):
    name: str
    limit: int
    remaining: int | None = None
    resets_at: datetime | None = None
    window_seconds: int | None = None


class RateLimitStatus(CanonicalModel):
    exchange: str
    measured_at: datetime
    windows: tuple[RateLimitWindow, ...]
```


# 78. Data Quality Finding

```python
class DataQualityFinding(CanonicalModel):
    finding_id: str
    rule_id: str
    rule_version: str

    severity: DataQualitySeverity
    action: DataQualityAction

    exchange: str | None = None
    market_id: str | None = None
    event_id: str | None = None
    raw_record_id: str | None = None

    detected_at: datetime

    reason_code: str
    message: str

    safe_payload_reference: str | None = None
    blocks_trading: bool
```


# 79. Dead Letter Record

```python
class DeadLetterRecord(CanonicalModel):
    dead_letter_id: str

    source_event_id: str | None = None
    source_command_id: str | None = None

    consumer_name: str
    failure_category: str

    exception_type: str
    exception_message: str

    first_failed_at: datetime
    last_failed_at: datetime
    retry_count: int

    payload_reference: str
    replayable: bool

    resolved_at: datetime | None = None
    resolution_note: str | None = None
```


# 80. Operator Audit Record

```python
class OperatorAuditRecord(CanonicalModel):
    audit_id: str

    actor: str
    action: str
    scope: str
    scope_id: str | None = None

    requested_at: datetime
    completed_at: datetime | None = None

    result: str
    reason: str | None = None

    correlation_id: str
    source_ip_hash: str | None = None
```


# 81. Configuration Snapshot

```python
class ConfigurationSnapshot(CanonicalModel):
    configuration_snapshot_id: str
    environment: Environment

    captured_at: datetime
    configuration_hash: str

    redacted_configuration: dict[str, object]

    code_commit: str
    dependency_lock_hash: str
```


# 82. Event Schema Registry Record

```python
class EventSchemaRegistryRecord(CanonicalModel):
    event_type: str
    schema_version: int

    python_model_path: str
    json_schema_uri: str | None = None

    introduced_in_platform_version: str
    deprecated_in_platform_version: str | None = None

    backward_compatible_with: tuple[int, ...] = ()
    upcaster_paths: tuple[str, ...] = ()
```


# 83. Command Schemas

Required command models include:

- ConnectAdapterCommand
- DisconnectAdapterCommand
- SubscribeMarketCommand
- UnsubscribeMarketCommand
- StartStrategyCommand
- StopStrategyCommand
- PlaceOrderCommand
- CancelOrderCommand
- ReplaceOrderCommand
- ActivateKillSwitchCommand
- ReleaseKillSwitchCommand
- StartReplayCommand
- PauseReplayCommand
- ResumeReplayCommand
- SeekReplayCommand
- ReconcileAccountCommand

Example:

```python
class PlaceOrderCommand(CanonicalModel):
    envelope: CommandEnvelope
    approved_order: ApprovedOrder


class CancelOrderCommand(CanonicalModel):
    envelope: CommandEnvelope
    request: CancelOrderRequest


class ReconcileAccountCommand(CanonicalModel):
    envelope: CommandEnvelope
    exchange: str
    account_id: str
    include_fills_since: datetime | None = None
```


# 84. Core Market Events

Core market event models include:

```python
class MarketDiscoveredEvent(CanonicalModel):
    envelope: EventEnvelope
    market: Market
    outcomes: tuple[Outcome, ...]
    contracts: tuple[Contract, ...]


class MarketUpdatedEvent(CanonicalModel):
    envelope: EventEnvelope
    market: Market
    changed_fields: tuple[str, ...]


class MarketStatusChangedEvent(CanonicalModel):
    envelope: EventEnvelope
    update: MarketLifecycleUpdate


class OrderBookSnapshotEvent(CanonicalModel):
    envelope: EventEnvelope
    snapshot: OrderBookSnapshot


class OrderBookDeltaEvent(CanonicalModel):
    envelope: EventEnvelope
    delta: OrderBookDelta


class TradeObservedEvent(CanonicalModel):
    envelope: EventEnvelope
    trade: Trade


class SettlementObservedEvent(CanonicalModel):
    envelope: EventEnvelope
    settlement: Settlement
```


# 85. Core Strategy Events

```python
class StrategyStartedEvent(CanonicalModel):
    envelope: EventEnvelope
    strategy: StrategyInstance


class StrategyStoppedEvent(CanonicalModel):
    envelope: EventEnvelope
    strategy_id: str
    reason: str


class StrategyHealthChangedEvent(CanonicalModel):
    envelope: EventEnvelope
    strategy_id: str
    previous_status: HealthStatus
    current_status: HealthStatus
    message: str | None = None


class SignalGeneratedEvent(CanonicalModel):
    envelope: EventEnvelope
    signal: Signal


class SignalWithdrawnEvent(CanonicalModel):
    envelope: EventEnvelope
    signal_id: str
    withdrawn_at: datetime
    reason: str
```


# 86. Core Risk Events

```python
class RiskCheckRequestedEvent(CanonicalModel):
    envelope: EventEnvelope
    intent: OrderIntent
    input_snapshot: RiskInputSnapshot


class RiskApprovedEvent(CanonicalModel):
    envelope: EventEnvelope
    decision: RiskDecision
    approved_order: ApprovedOrder


class RiskRejectedEvent(CanonicalModel):
    envelope: EventEnvelope
    decision: RiskDecision


class RiskLimitBreachedEvent(CanonicalModel):
    envelope: EventEnvelope
    breach: RiskBreach


class KillSwitchActivatedEvent(CanonicalModel):
    envelope: EventEnvelope
    state: KillSwitchState


class KillSwitchReleasedEvent(CanonicalModel):
    envelope: EventEnvelope
    state: KillSwitchState
```


# 87. Core Execution Events

```python
class OrderCreatedEvent(CanonicalModel):
    envelope: EventEnvelope
    order: Order


class OrderSubmittedEvent(CanonicalModel):
    envelope: EventEnvelope
    order_id: str
    request: ExchangeOrderRequest


class OrderAcceptedEvent(CanonicalModel):
    envelope: EventEnvelope
    acknowledgement: ExchangeOrderAcknowledgement
    transition: OrderStateTransition


class OrderRejectedEvent(CanonicalModel):
    envelope: EventEnvelope
    acknowledgement: ExchangeOrderAcknowledgement
    transition: OrderStateTransition


class OrderPartiallyFilledEvent(CanonicalModel):
    envelope: EventEnvelope
    fill: Fill
    order: Order
    transition: OrderStateTransition


class OrderFilledEvent(CanonicalModel):
    envelope: EventEnvelope
    fill: Fill
    order: Order
    transition: OrderStateTransition


class OrderCancelRequestedEvent(CanonicalModel):
    envelope: EventEnvelope
    request: CancelOrderRequest


class OrderCancelledEvent(CanonicalModel):
    envelope: EventEnvelope
    acknowledgement: CancelOrderAcknowledgement
    transition: OrderStateTransition


class OrderLostEvent(CanonicalModel):
    envelope: EventEnvelope
    order_id: str
    reason: str
```


# 88. Core Portfolio Events

```python
class PositionChangedEvent(CanonicalModel):
    envelope: EventEnvelope
    previous_position: Position | None
    current_position: Position
    source_fill_id: str | None = None


class CashBalanceChangedEvent(CanonicalModel):
    envelope: EventEnvelope
    previous_balance: CashBalance | None
    current_balance: CashBalance
    reason: str


class PnlUpdatedEvent(CanonicalModel):
    envelope: EventEnvelope
    attribution: PnlAttribution


class PortfolioReconciledEvent(CanonicalModel):
    envelope: EventEnvelope
    result: ReconciliationResult


class PortfolioMismatchDetectedEvent(CanonicalModel):
    envelope: EventEnvelope
    result: ReconciliationResult
```


# 89. Core System Events

```python
class AdapterConnectedEvent(CanonicalModel):
    envelope: EventEnvelope
    health: AdapterHealth


class AdapterDisconnectedEvent(CanonicalModel):
    envelope: EventEnvelope
    exchange: str
    reason: str
    reconnect_scheduled: bool


class SequenceGapDetectedEvent(CanonicalModel):
    envelope: EventEnvelope
    exchange: str
    market_id: str
    expected_sequence: int
    received_sequence: int


class DataQualityIssueDetectedEvent(CanonicalModel):
    envelope: EventEnvelope
    finding: DataQualityFinding


class ServiceHealthChangedEvent(CanonicalModel):
    envelope: EventEnvelope
    health: ServiceHealth


class ConfigurationLoadedEvent(CanonicalModel):
    envelope: EventEnvelope
    snapshot: ConfigurationSnapshot
```


# 90. API Error Schema

```python
class ApiErrorDetail(CanonicalModel):
    field: str | None = None
    code: str
    message: str


class ApiErrorResponse(CanonicalModel):
    error_id: str
    status: int
    code: str
    message: str

    details: tuple[ApiErrorDetail, ...] = ()

    correlation_id: str
    occurred_at: datetime
```


# 91. API Pagination Schemas

```python
class CursorPageRequest(CanonicalModel):
    cursor: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class CursorPageInfo(CanonicalModel):
    next_cursor: str | None = None
    previous_cursor: str | None = None
    returned_count: int
    has_more: bool
```


# 92. API Market List Response

```python
class MarketListResponse(CanonicalModel):
    items: tuple[Market, ...]
    page: CursorPageInfo
    correlation_id: str
```


# 93. API Order List Response

```python
class OrderListResponse(CanonicalModel):
    items: tuple[Order, ...]
    page: CursorPageInfo
    correlation_id: str
```


# 94. API Portfolio Response

```python
class PortfolioResponse(CanonicalModel):
    portfolio: PortfolioSnapshot
    correlation_id: str
```


# 95. API Strategy Control Requests

```python
class StartStrategyRequest(CanonicalModel):
    strategy_id: str
    configuration_version: int
    reason: str | None = None


class StopStrategyRequest(CanonicalModel):
    strategy_id: str
    reason: str


class StrategyControlResponse(CanonicalModel):
    strategy: StrategyInstance
    correlation_id: str
```


# 96. API Kill Switch Requests

```python
class ActivateKillSwitchRequest(CanonicalModel):
    scope: KillSwitchScope
    scope_id: str | None = None
    reason: str


class ReleaseKillSwitchRequest(CanonicalModel):
    kill_switch_id: str
    reason: str


class KillSwitchResponse(CanonicalModel):
    state: KillSwitchState
    correlation_id: str
```


# 97. API Replay Requests

```python
class StartReplayRequest(CanonicalModel):
    manifest: ReplayManifest


class ReplayControlRequest(CanonicalModel):
    replay_session_id: str
    action: str
    seek_to: datetime | None = None


class ReplayResponse(CanonicalModel):
    session: ReplaySession
    correlation_id: str
```


# 98. JSON Schema Publication

Every canonical Pydantic model that crosses a process or persistence boundary
should be able to emit JSON Schema.

Recommended publication path:

```text
schemas/json/
  event/
  command/
  api/
  domain/
```

Filename pattern:

```text
<schema_name>.v<version>.json
```

Example:

```text
order_created_event.v1.json
risk_decision.v1.json
market.v1.json
```

Published schemas should include:

- title
- description
- field types
- required fields
- enum values
- examples
- version metadata


# 99. Schema Versioning Policy

Schema versions are positive integers.

Version 1 is the first published contract.

Additive optional fields may remain in the same version when backward
compatibility is preserved.

A new version is required for:

- required field addition
- field removal
- field rename
- enum semantic change
- unit change
- precision change
- meaning change
- cardinality change
- timestamp semantic change

A version increment does not automatically imply platform major version change.

Breaking public API changes require release-policy review.


# 100. Upcasters and Downcasters

Historical event replay may require upcasters.

An upcaster converts:

```text
EventType version N -> EventType version N+1
```

Requirements:

- deterministic
- pure
- tested
- versioned
- no external I/O
- preserves original event ID or records source event ID
- documents defaults or inferred values

Downcasters should be avoided unless required for compatibility with an older
consumer.

Downcasting must never silently discard safety-critical information.


# 101. Unknown Enum Handling

Canonical enums are strict.

Adapter transport enums may include an `UNKNOWN` or raw fallback value when an
exchange introduces a new string.

The normalizer should:

1. preserve the raw value
2. emit a data-quality finding
3. map to canonical UNKNOWN only where safe
4. block trading if the meaning affects execution, settlement, or accounting

Do not silently map unknown states to a familiar state.


# 102. Nullability Rules

A field is optional only when its absence is meaningful and expected.

Examples:

- `accepted_at` is absent before acceptance
- `average_fill_price` is absent before a fill
- `resolves_at` may be absent for markets without a fixed date

Do not make a field optional merely to simplify parsing.

Boundary models may initially permit missing data, but canonical validation
should reject incomplete objects or mark them explicitly incomplete.


# 103. Default Value Rules

Defaults are permitted for stable domain defaults.

Examples:

- empty tuple
- empty metadata dictionary
- payout per unit of one where the platform contract defines it
- schema version one

Defaults are not permitted when absence indicates incomplete mapping.

Examples:

- exchange
- market ID
- quantity
- price
- occurred_at
- correlation ID


# 104. Validation Error Contract

Validation failures should produce structured error data.

Recommended fields:

```text
schema_name
schema_version
field_path
error_code
message
input_type
safe_input_excerpt
```

Do not include:

- secrets
- private keys
- authorization headers
- full sensitive payloads

Validation error codes should be stable enough for monitoring.


# 105. Canonical Hashing

Stable hashes are used for:

- event payloads
- replay datasets
- configurations
- model artifacts
- experiment results

Recommended algorithm:

```text
SHA-256
```

Hash input should be canonical serialized bytes.

Canonicalization must define:

- key ordering
- whitespace
- Decimal representation
- datetime representation
- enum representation
- list ordering

A hash does not replace a digital signature.


# 106. Sensitive Field Classification

Schema fields may be classified:

- public
- internal
- confidential
- secret

Secret examples:

- API key
- private key
- auth token
- signature secret

Confidential examples:

- full account ID
- private strategy configuration
- proprietary model URI

Canonical business events should avoid secret fields entirely.

API response schemas should redact confidential values according to the caller's
authorization.


# 107. Redaction Schema

```python
class RedactionRule(CanonicalModel):
    field_path: str
    action: str
    replacement: str = "[REDACTED]"


class RedactedPayloadReference(CanonicalModel):
    reference_id: str
    content_hash: str
    redaction_rules_applied: tuple[str, ...]
    created_at: datetime
```


# 108. Schema Compatibility Tests

Each public schema requires tests for:

- valid minimum payload
- valid full payload
- missing required field
- unknown extra field
- invalid enum
- invalid Decimal
- float rejection where required
- naive datetime rejection
- serialization round trip
- JSON Schema generation
- previous compatible version
- upcaster behavior

Event envelope tests also verify:

- event ID
- correlation ID
- timestamps
- schema version
- quality flags


# 109. Property Tests for Schemas

Recommended property tests:

- Probability always remains in the closed unit interval.
- Quantity is never negative.
- Order filled plus remaining equals original quantity.
- Cash available plus reserved equals total.
- Journal lines sum to zero per currency.
- Decimal serialization round trips exactly.
- Timezone-aware datetimes remain timezone aware.
- Stable serialization produces stable hashes.
- Enum values round trip exactly.
- Duplicate fill IDs do not create duplicate portfolio effects.


# 110. Example Market JSON

```json
{
  "market_id": "mkt_01j00000000000000000000000",
  "canonical_event_id": null,
  "exchange": "kalshi",
  "exchange_market_id": "FED-26SEP-T4.50",
  "exchange_event_id": "FED-26SEP",
  "title": "Will the target range be above 4.50 percent?",
  "subtitle": null,
  "description": null,
  "category": "economics",
  "tags": [
    "federal_reserve",
    "interest_rates"
  ],
  "outcome_type": "binary",
  "status": "open",
  "opens_at": "2026-01-01T00:00:00Z",
  "closes_at": "2026-09-16T18:00:00Z",
  "resolves_at": "2026-09-16T20:00:00Z",
  "finalized_at": null,
  "currency": "USD",
  "payout_per_unit": "1",
  "tick_size": "0.01",
  "quantity_increment": "1",
  "rules_text": "Resolution follows the published exchange rules.",
  "rules_url": null,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-07-27T15:00:00Z"
}
```


# 111. Example Order Book Snapshot JSON

```json
{
  "market_id": "mkt_01j00000000000000000000000",
  "contract_id": "ctr_01j00000000000000000000000",
  "exchange": "kalshi",
  "sequence": 99123,
  "exchange_occurred_at": "2026-07-27T15:00:00.120000Z",
  "received_at": "2026-07-27T15:00:00.132000Z",
  "bids": [
    {
      "price": "0.41",
      "quantity": "30",
      "order_count": 4
    },
    {
      "price": "0.40",
      "quantity": "55",
      "order_count": 8
    }
  ],
  "asks": [
    {
      "price": "0.43",
      "quantity": "25",
      "order_count": 3
    },
    {
      "price": "0.44",
      "quantity": "70",
      "order_count": 9
    }
  ],
  "is_valid": true,
  "snapshot_reason": "initial"
}
```


# 112. Example Signal JSON

```json
{
  "signal_id": "sig_01j00000000000000000000000",
  "strategy_id": "strat_fed_value_v1",
  "market_id": "mkt_01j00000000000000000000000",
  "contract_id": "ctr_01j00000000000000000000000",
  "outcome_id": "out_yes",
  "signal_type": "fair_value_gap",
  "direction": "buy",
  "strength": "0.65",
  "fair_probability": "0.47",
  "confidence": "0.72",
  "valid_from": "2026-07-27T15:00:00.140000Z",
  "valid_until": "2026-07-27T15:00:02.140000Z",
  "model_id": "mdl_fed_probability",
  "model_version": "1.4.2",
  "feature_snapshot_id": "feat_01j00000000000000000000000",
  "reason_code": "MODEL_ABOVE_ASK",
  "reason_text": "Fair probability exceeds executable ask after cost.",
  "correlation_id": "corr_01j00000000000000000000000"
}
```


# 113. Example Risk Decision JSON

```json
{
  "risk_decision_id": "risk_01j00000000000000000000000",
  "intent_id": "intent_01j00000000000000000000000",
  "status": "approved",
  "evaluated_at": "2026-07-27T15:00:00.145000Z",
  "input_snapshot_id": "risk_input_01j0000000000000000000",
  "rule_results": [
    {
      "rule_id": "RISK-005",
      "rule_version": "1.0",
      "passed": true,
      "reason_code": "MARKET_DATA_FRESH",
      "reason_text": null,
      "observed_value": "12",
      "limit_value": "5000",
      "unit": "milliseconds",
      "evaluated_at": "2026-07-27T15:00:00.145000Z"
    }
  ],
  "approved_quantity": "10",
  "approved_limit_price": "0.43",
  "approval_expires_at": "2026-07-27T15:00:01.145000Z",
  "configuration_hash": "sha256:abc123",
  "correlation_id": "corr_01j00000000000000000000000"
}
```


# 114. Example Order JSON

```json
{
  "order_id": "ord_01j00000000000000000000000",
  "intent_id": "intent_01j00000000000000000000000",
  "strategy_id": "strat_fed_value_v1",
  "risk_decision_id": "risk_01j00000000000000000000000",
  "exchange": "kalshi",
  "account_id": "acct_shadow",
  "market_id": "mkt_01j00000000000000000000000",
  "contract_id": "ctr_01j00000000000000000000000",
  "outcome_id": "out_yes",
  "side": "buy",
  "quantity": "10",
  "filled_quantity": "4",
  "remaining_quantity": "6",
  "limit_price": "0.43",
  "average_fill_price": "0.425",
  "order_type": "limit",
  "time_in_force": "gtc",
  "post_only": false,
  "reduce_only": false,
  "status": "partially_filled",
  "client_order_id": "pmrp-ord-0001",
  "exchange_order_id": "exchange-order-123",
  "created_at": "2026-07-27T15:00:00.146000Z",
  "submitted_at": "2026-07-27T15:00:00.148000Z",
  "accepted_at": "2026-07-27T15:00:00.160000Z",
  "last_updated_at": "2026-07-27T15:00:00.500000Z",
  "expires_at": null,
  "aggregate_version": 5
}
```


# 115. Example Fill JSON

```json
{
  "fill_id": "fill_01j00000000000000000000000",
  "exchange_fill_id": "exchange-fill-456",
  "order_id": "ord_01j00000000000000000000000",
  "exchange_order_id": "exchange-order-123",
  "client_order_id": "pmrp-ord-0001",
  "exchange": "kalshi",
  "account_id": "acct_shadow",
  "market_id": "mkt_01j00000000000000000000000",
  "contract_id": "ctr_01j00000000000000000000000",
  "outcome_id": "out_yes",
  "side": "buy",
  "price": "0.42",
  "quantity": "4",
  "liquidity_role": "maker",
  "fee": {
    "amount": "0.01",
    "currency": "USD"
  },
  "rebate": null,
  "exchange_occurred_at": "2026-07-27T15:00:00.480000Z",
  "received_at": "2026-07-27T15:00:00.500000Z",
  "trade_id": "trade_789"
}
```

The final implementation may represent Fee as a dedicated canonical schema
rather than a generic Money object.


# 116. Example Event Envelope JSON

```json
{
  "event_id": "evt_01j00000000000000000000000",
  "event_type": "order.partially_filled",
  "schema_version": 1,
  "occurred_at": "2026-07-27T15:00:00.480000Z",
  "received_at": "2026-07-27T15:00:00.500000Z",
  "published_at": "2026-07-27T15:00:00.505000Z",
  "producer": "execution-service",
  "exchange": "kalshi",
  "market_id": "mkt_01j00000000000000000000000",
  "account_id": "acct_shadow",
  "strategy_id": "strat_fed_value_v1",
  "order_id": "ord_01j00000000000000000000000",
  "correlation_id": "corr_01j00000000000000000000000",
  "causation_id": "evt_01j00000000000000000000001",
  "trace_id": "trace-abc123",
  "replay_session_id": null,
  "simulation_session_id": null,
  "quality_flags": [],
  "attributes": {}
}
```


# 117. Example Replay Manifest JSON

```json
{
  "replay_session_id": "rpl_01j00000000000000000000000",
  "dataset_id": "dataset_fed_july_2026",
  "dataset_checksum": "sha256:dataset123",
  "starts_at": "2026-07-01T00:00:00Z",
  "ends_at": "2026-07-27T23:59:59Z",
  "speed": "20",
  "deterministic": true,
  "random_seed": 20260727,
  "event_ordering_policy_version": "1.0",
  "strategy_versions": {
    "strat_fed_value_v1": "1.2.0"
  },
  "model_versions": {
    "mdl_fed_probability": "1.4.2"
  },
  "configuration_hash": "sha256:config123",
  "code_commit": "abcdef123456",
  "dependency_lock_hash": "sha256:lock123",
  "created_at": "2026-07-27T12:00:00Z",
  "created_by": "researcher"
}
```


# 118. Database Mapping Guidance

This document defines logical schemas.

`06_DATABASE.md` defines physical PostgreSQL mappings.

General mapping guidance:

```text
Decimal          -> NUMERIC
datetime UTC     -> TIMESTAMPTZ
identifier       -> TEXT or UUID-compatible type
enum             -> TEXT with application validation
tuple/list       -> child table or JSONB based on query requirements
metadata         -> JSONB
event payload    -> JSONB plus indexed envelope columns
```

High-value query fields should be first-class columns.

Do not hide all operational state inside opaque JSON.


# 119. Event Naming Convention

Event type strings use lowercase dotted names.

Examples:

```text
market.discovered
market.updated
market.status_changed
market.order_book_snapshot
market.order_book_delta
market.trade_observed
market.settlement_observed

strategy.started
strategy.stopped
strategy.signal_generated

risk.check_requested
risk.approved
risk.rejected
risk.limit_breached
risk.kill_switch_activated

order.created
order.submitted
order.accepted
order.rejected
order.partially_filled
order.filled
order.cancel_requested
order.cancelled
order.lost

portfolio.position_changed
portfolio.cash_balance_changed
portfolio.reconciled

system.adapter_connected
system.adapter_disconnected
system.sequence_gap_detected
system.data_quality_issue
```


# 120. Command Naming Convention

Command type strings use lowercase dotted imperative names.

Examples:

```text
adapter.connect
adapter.disconnect
market.subscribe
market.unsubscribe
strategy.start
strategy.stop
order.place
order.cancel
order.replace
risk.kill_switch.activate
risk.kill_switch.release
replay.start
replay.pause
replay.resume
replay.seek
account.reconcile
```


# 121. Schema Ownership Matrix

```text
Schema Group                    Owning Package
---------------------------------------------------------------
Identifiers                     pmrp.schemas.identifiers
Enums                           pmrp.schemas.enums
Financial values                pmrp.schemas.numeric
Event envelope                  pmrp.schemas.events
Command envelope                pmrp.schemas.commands
Markets                         pmrp.schemas.markets
Market data                     pmrp.schemas.market_data
Orders and fills                pmrp.schemas.orders
Portfolio                       pmrp.schemas.portfolio
Risk                            pmrp.schemas.risk
Strategy and signals            pmrp.schemas.strategy
Models and features             pmrp.schemas.models
Matching and arbitrage          pmrp.schemas.matching
Replay                          pmrp.schemas.replay
Simulation                      pmrp.schemas.simulation
System health                   pmrp.schemas.system
Operator API                    pmrp.schemas.api
```


# 122. Required Schema Registry Entries

The initial registry should include at least:

- Market v1
- Outcome v1
- Contract v1
- OrderBookSnapshot v1
- OrderBookDelta v1
- Trade v1
- Signal v1
- OrderIntent v1
- ApprovedOrder v1
- Order v1
- Fill v1
- Position v1
- CashBalance v1
- RiskDecision v1
- RiskBreach v1
- KillSwitchState v1
- ReconciliationResult v1
- Settlement v1
- MarketRelationship v1
- ReplayManifest v1
- ReplayResult v1
- SimulationConfiguration v1
- ModelArtifactMetadata v1
- ServiceHealth v1
- AdapterHealth v1


# 123. Required Event Registry Entries

The initial event registry should include at least:

- market.discovered v1
- market.updated v1
- market.status_changed v1
- market.order_book_snapshot v1
- market.order_book_delta v1
- market.trade_observed v1
- market.settlement_observed v1
- strategy.started v1
- strategy.stopped v1
- strategy.health_changed v1
- strategy.signal_generated v1
- risk.check_requested v1
- risk.approved v1
- risk.rejected v1
- risk.limit_breached v1
- risk.kill_switch_activated v1
- risk.kill_switch_released v1
- order.created v1
- order.submitted v1
- order.accepted v1
- order.rejected v1
- order.partially_filled v1
- order.filled v1
- order.cancel_requested v1
- order.cancelled v1
- order.lost v1
- portfolio.position_changed v1
- portfolio.cash_balance_changed v1
- portfolio.pnl_updated v1
- portfolio.reconciled v1
- portfolio.mismatch_detected v1
- system.adapter_connected v1
- system.adapter_disconnected v1
- system.sequence_gap_detected v1
- system.data_quality_issue v1
- system.health_changed v1
- system.configuration_loaded v1


# 124. Minimum Validation Invariants

The implementation must enforce at least the following invariants.

Markets:

- market ID is nonempty
- exchange market ID is nonempty
- tick size is positive
- quantity increment is positive
- payout per unit is positive
- closes_at does not precede opens_at when both exist

Order books:

- quantities are nonnegative
- bid ordering is descending
- ask ordering is ascending
- duplicate prices are resolved
- invalid sequence gaps do not update a valid projection

Orders:

- quantity is positive
- filled quantity is nonnegative
- remaining quantity is nonnegative
- filled plus remaining equals total
- limit order has a price
- market order does not require a price
- terminal transition rules are enforced

Fills:

- quantity is positive
- fill ID is unique
- fill side matches order side
- cumulative fills do not exceed order quantity unless flagged

Portfolio:

- balances reconcile
- Decimal is used
- duplicate fills are idempotent
- journal entries balance by currency

Risk:

- required inputs are fresh
- approved quantity is positive
- approval references an intent
- each rule result has a stable reason code

Replay:

- dataset checksum exists
- seed exists
- ordering policy version exists
- live side effects are disabled


# 125. Schema Review Checklist

```text
[ ] Schema has a clear owner.
[ ] Field names are stable and snake_case.
[ ] Units are explicit.
[ ] Decimal is used for financial values.
[ ] Datetimes are timezone-aware UTC.
[ ] Required fields are truly required.
[ ] Optional fields have meaningful absence semantics.
[ ] Unknown fields are handled intentionally.
[ ] Enum values are stable.
[ ] Serialization round trip is exact.
[ ] Schema version is defined.
[ ] Backward compatibility impact is reviewed.
[ ] JSON Schema output is valid.
[ ] Example payload exists.
[ ] Validation tests exist.
[ ] Sensitive fields are classified.
[ ] Replay impact is reviewed.
```


# 126. Implementation Guidance

The first implementation should not create every schema in one pull request.

Recommended sequence:

1. common base model
2. identifiers
3. enums
4. financial value objects
5. event envelope
6. market and outcome schemas
7. market-data schemas
8. order and fill schemas
9. risk schemas
10. portfolio schemas
11. strategy and signal schemas
12. replay and simulation schemas
13. system health schemas
14. API schemas
15. JSON Schema publication
16. compatibility tests

Each group should include:

- code
- validation
- tests
- examples
- registry entry


# 127. Schema Definition of Done

A schema is complete when:

- ownership is clear
- Pydantic model exists
- type annotations are complete
- Decimal and time rules are followed
- invariants are validated
- schema version is registered
- JSON Schema can be generated
- serialization round trip is tested
- valid and invalid fixtures exist
- backward compatibility is reviewed
- documentation example exists
- sensitive fields are redacted or excluded
- replay and persistence implications are understood


# 128. Final Schema Position

Canonical schemas are the platform's shared language.

Adapters translate into them.

Strategies consume them.

Risk evaluates them.

Execution records them.

Portfolio accounting depends on them.

Replay reproduces them.

Monitoring observes them.

Research exports them.

If canonical contracts are vague, every subsystem becomes fragile.

If canonical contracts are precise, versioned, exact, and tested, the platform
can evolve without coupling every exchange, strategy, and storage engine
together.

The schema layer is therefore not administrative overhead.

It is core trading infrastructure.
