"""Canonical schema primitives for PMRP."""

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.commands import CommandEnvelope
from pmrp.schemas.enums import Environment, HealthStatus, Side
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.identifiers import EventId, MarketId, OrderId
from pmrp.schemas.market_data import OrderBookDelta, OrderBookSnapshot, Trade
from pmrp.schemas.markets import Contract, Market, Outcome
from pmrp.schemas.metadata import AuditMetadata, FlexibleMetadata, SourceMetadata, VersionMetadata
from pmrp.schemas.numeric import Money, Price, Probability, Quantity
from pmrp.schemas.orders import (
    ApprovedOrder,
    CancelOrderAcknowledgement,
    CancelOrderRequest,
    ExchangeOrderAcknowledgement,
    ExchangeOrderRequest,
    Fill,
    OpenOrderSnapshot,
    Order,
    OrderIntent,
    OrderStateTransition,
    ReplaceOrderRequest,
)
from pmrp.schemas.portfolio import (
    AccountingJournalEntry,
    CashBalance,
    JournalLine,
    PnlAttribution,
    PortfolioSnapshot,
    Position,
    PositionLot,
    ReconciliationMismatch,
    ReconciliationResult,
    ReconciliationStatus,
    Settlement,
    SettlementStatus,
)
from pmrp.schemas.replay import ReplayManifest, ReplayResult, ReplaySession, ReplayState
from pmrp.schemas.risk import (
    KillSwitchScope,
    KillSwitchState,
    RiskBreach,
    RiskDecision,
    RiskLimit,
    RiskLimitScope,
    RiskRuleResult,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.schemas.strategy import Signal, SignalDirection
from pmrp.schemas.system import (
    AdapterHealth,
    DependencyHealth,
    RateLimitStatus,
    RateLimitWindow,
    ServiceHealth,
)
from pmrp.schemas.time import UTCDateTime
from pmrp.schemas.versions import SchemaRegistration, SchemaVersion, get_schema_model

__all__ = [
    "AccountingJournalEntry",
    "AdapterHealth",
    "ApprovedOrder",
    "AuditMetadata",
    "CancelOrderAcknowledgement",
    "CancelOrderRequest",
    "CanonicalModel",
    "CashBalance",
    "CommandEnvelope",
    "Contract",
    "DependencyHealth",
    "Environment",
    "EventEnvelope",
    "EventId",
    "ExchangeOrderAcknowledgement",
    "ExchangeOrderRequest",
    "Fill",
    "FlexibleMetadata",
    "HealthStatus",
    "JournalLine",
    "KillSwitchScope",
    "KillSwitchState",
    "Market",
    "MarketId",
    "Money",
    "OpenOrderSnapshot",
    "Order",
    "OrderBookDelta",
    "OrderBookSnapshot",
    "OrderId",
    "OrderIntent",
    "OrderStateTransition",
    "Outcome",
    "PnlAttribution",
    "PortfolioSnapshot",
    "Position",
    "PositionLot",
    "Price",
    "Probability",
    "Quantity",
    "RateLimitStatus",
    "RateLimitWindow",
    "ReconciliationMismatch",
    "ReconciliationResult",
    "ReconciliationStatus",
    "ReplaceOrderRequest",
    "ReplayManifest",
    "ReplayResult",
    "ReplaySession",
    "ReplayState",
    "RiskBreach",
    "RiskDecision",
    "RiskLimit",
    "RiskLimitScope",
    "RiskRuleResult",
    "SchemaRegistration",
    "SchemaVersion",
    "ServiceHealth",
    "Settlement",
    "SettlementStatus",
    "Side",
    "Signal",
    "SignalDirection",
    "SimulationConfiguration",
    "SourceMetadata",
    "Trade",
    "UTCDateTime",
    "VersionMetadata",
    "canonical_json",
    "canonical_sha256",
    "get_schema_model",
]
