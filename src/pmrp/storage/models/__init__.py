"""SQLAlchemy storage row-model metadata."""

from pmrp.storage.models.base import NAMING_CONVENTION, StorageBase
from pmrp.storage.models.canonical_events import CanonicalEventRow, EventIdRow
from pmrp.storage.models.dead_letters import DeadLetterRecordRow
from pmrp.storage.models.event_processing import OutboxMessageRow, ProcessedEventRow
from pmrp.storage.models.exchange_registry import ExchangeAccountRow, ExchangeRow
from pmrp.storage.models.fills import FillIdRow, FillRow
from pmrp.storage.models.health_audit import AdapterHealthSnapshotRow, OperatorAuditRecordRow
from pmrp.storage.models.idempotency import IdempotencyRecordRow
from pmrp.storage.models.market_catalog import ContractRow, MarketRow, OutcomeRow
from pmrp.storage.models.market_data import OrderBookSnapshotRow, TradeRow
from pmrp.storage.models.matching import MarketRelationshipRow
from pmrp.storage.models.orders import OrderIntentRow, OrderRow, OrderStateTransitionRow
from pmrp.storage.models.portfolio import (
    CashBalanceRow,
    JournalEntryRow,
    JournalLineRow,
    PnlAttributionRow,
    PositionRow,
    SettlementRow,
)
from pmrp.storage.models.raw_exchange import RawExchangeRecordRow
from pmrp.storage.models.reconciliation import ReconciliationMismatchRow, ReconciliationRunRow
from pmrp.storage.models.replay_simulation import (
    ReplayResultRow,
    ReplaySessionRow,
    SimulationSessionRow,
)
from pmrp.storage.models.research_metadata import (
    ModelArtifactRow,
    StrategyConfigurationRow,
    StrategyDefinitionRow,
    StrategyInstanceRow,
)
from pmrp.storage.models.research_signals import FeatureSnapshotRow, SignalRow
from pmrp.storage.models.risk import (
    CapitalReservationRow,
    KillSwitchRow,
    RiskBreachRow,
    RiskDecisionRow,
    RiskLimitRow,
)
from pmrp.storage.models.schema_registry import SchemaRegistryRow

__all__ = [
    "NAMING_CONVENTION",
    "AdapterHealthSnapshotRow",
    "CanonicalEventRow",
    "CapitalReservationRow",
    "CashBalanceRow",
    "ContractRow",
    "DeadLetterRecordRow",
    "EventIdRow",
    "ExchangeAccountRow",
    "ExchangeRow",
    "FeatureSnapshotRow",
    "FillIdRow",
    "FillRow",
    "IdempotencyRecordRow",
    "JournalEntryRow",
    "JournalLineRow",
    "KillSwitchRow",
    "MarketRelationshipRow",
    "MarketRow",
    "ModelArtifactRow",
    "OperatorAuditRecordRow",
    "OrderBookSnapshotRow",
    "OrderIntentRow",
    "OrderRow",
    "OrderStateTransitionRow",
    "OutboxMessageRow",
    "OutcomeRow",
    "PnlAttributionRow",
    "PositionRow",
    "ProcessedEventRow",
    "RawExchangeRecordRow",
    "ReconciliationMismatchRow",
    "ReconciliationRunRow",
    "ReplayResultRow",
    "ReplaySessionRow",
    "RiskBreachRow",
    "RiskDecisionRow",
    "RiskLimitRow",
    "SchemaRegistryRow",
    "SettlementRow",
    "SignalRow",
    "SimulationSessionRow",
    "StorageBase",
    "StrategyConfigurationRow",
    "StrategyDefinitionRow",
    "StrategyInstanceRow",
    "TradeRow",
]
