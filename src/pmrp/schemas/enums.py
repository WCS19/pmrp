"""Foundational canonical enum definitions."""

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
