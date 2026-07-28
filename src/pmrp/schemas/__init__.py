"""Canonical schema primitives for PMRP."""

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.commands import CommandEnvelope
from pmrp.schemas.enums import Side
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
from pmrp.schemas.strategy import Signal, SignalDirection
from pmrp.schemas.time import UTCDateTime
from pmrp.schemas.versions import SchemaRegistration, SchemaVersion, get_schema_model

__all__ = [
    "ApprovedOrder",
    "AuditMetadata",
    "CancelOrderAcknowledgement",
    "CancelOrderRequest",
    "CanonicalModel",
    "CommandEnvelope",
    "Contract",
    "EventEnvelope",
    "EventId",
    "ExchangeOrderAcknowledgement",
    "ExchangeOrderRequest",
    "Fill",
    "FlexibleMetadata",
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
    "Price",
    "Probability",
    "Quantity",
    "ReplaceOrderRequest",
    "RiskBreach",
    "RiskDecision",
    "RiskLimit",
    "RiskLimitScope",
    "RiskRuleResult",
    "SchemaRegistration",
    "SchemaVersion",
    "Side",
    "Signal",
    "SignalDirection",
    "SourceMetadata",
    "Trade",
    "UTCDateTime",
    "VersionMetadata",
    "canonical_json",
    "canonical_sha256",
    "get_schema_model",
]
