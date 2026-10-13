"""Repositories for storage-backed PMRP components."""

from pmrp.storage.repositories.canonical_events import (
    CanonicalEventRepository,
    canonical_event_to_rows,
)
from pmrp.storage.repositories.capital_reservations import (
    CapitalReservationRepository,
    capital_reservation_from_row,
    capital_reservation_to_row,
)
from pmrp.storage.repositories.cash_balances import (
    CashBalanceRecord,
    CashBalanceRepository,
    cash_balance_from_row,
    cash_balance_record_from_row,
    cash_balance_to_row,
)
from pmrp.storage.repositories.event_contracts import CanonicalEventContract
from pmrp.storage.repositories.journal_entries import (
    JournalEntryRepository,
    journal_entry_from_rows,
    journal_entry_to_rows,
)
from pmrp.storage.repositories.kill_switches import (
    KillSwitchRepository,
    kill_switch_from_row,
    kill_switch_to_row,
)
from pmrp.storage.repositories.outbox import (
    CANONICAL_EVENTS_TOPIC,
    OutboxMessageRepository,
    outbox_message_to_row,
)
from pmrp.storage.repositories.pnl_attributions import (
    PnlAttributionRepository,
    pnl_attribution_from_row,
    pnl_attribution_to_row,
)
from pmrp.storage.repositories.portfolio_unit_of_work import SqlAlchemyPortfolioUnitOfWork
from pmrp.storage.repositories.positions import (
    PositionRepository,
    position_from_row,
    position_to_row,
)
from pmrp.storage.repositories.protocols import Repository, VersionedRepository
from pmrp.storage.repositories.reconciliation_results import (
    ReconciliationResultRepository,
    reconciliation_result_from_rows,
    reconciliation_result_to_rows,
)
from pmrp.storage.repositories.risk_breaches import (
    RiskBreachRepository,
    risk_breach_from_row,
    risk_breach_to_row,
)
from pmrp.storage.repositories.risk_decisions import (
    RiskDecisionRepository,
    risk_decision_from_row,
    risk_decision_to_row,
)
from pmrp.storage.repositories.risk_input_snapshots import (
    RiskInputSnapshotRepository,
    risk_input_snapshot_from_row,
    risk_input_snapshot_to_row,
)
from pmrp.storage.repositories.risk_limits import (
    RiskLimitRepository,
    risk_limit_from_row,
    risk_limit_to_row,
)
from pmrp.storage.repositories.risk_unit_of_work import SqlAlchemyRiskUnitOfWork
from pmrp.storage.repositories.settlements import (
    SettlementRepository,
    settlement_from_row,
    settlement_to_row,
)

__all__ = [
    "CANONICAL_EVENTS_TOPIC",
    "CanonicalEventContract",
    "CanonicalEventRepository",
    "CapitalReservationRepository",
    "CashBalanceRecord",
    "CashBalanceRepository",
    "JournalEntryRepository",
    "KillSwitchRepository",
    "OutboxMessageRepository",
    "PnlAttributionRepository",
    "PositionRepository",
    "ReconciliationResultRepository",
    "Repository",
    "RiskBreachRepository",
    "RiskDecisionRepository",
    "RiskInputSnapshotRepository",
    "RiskLimitRepository",
    "SettlementRepository",
    "SqlAlchemyPortfolioUnitOfWork",
    "SqlAlchemyRiskUnitOfWork",
    "VersionedRepository",
    "canonical_event_to_rows",
    "capital_reservation_from_row",
    "capital_reservation_to_row",
    "cash_balance_from_row",
    "cash_balance_record_from_row",
    "cash_balance_to_row",
    "journal_entry_from_rows",
    "journal_entry_to_rows",
    "kill_switch_from_row",
    "kill_switch_to_row",
    "outbox_message_to_row",
    "pnl_attribution_from_row",
    "pnl_attribution_to_row",
    "position_from_row",
    "position_to_row",
    "reconciliation_result_from_rows",
    "reconciliation_result_to_rows",
    "risk_breach_from_row",
    "risk_breach_to_row",
    "risk_decision_from_row",
    "risk_decision_to_row",
    "risk_input_snapshot_from_row",
    "risk_input_snapshot_to_row",
    "risk_limit_from_row",
    "risk_limit_to_row",
    "settlement_from_row",
    "settlement_to_row",
]
