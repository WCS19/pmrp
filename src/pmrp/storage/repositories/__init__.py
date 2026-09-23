"""Repositories for storage-backed PMRP components."""

from pmrp.storage.repositories.capital_reservations import (
    CapitalReservationRepository,
    capital_reservation_from_row,
    capital_reservation_to_row,
)
from pmrp.storage.repositories.kill_switches import (
    KillSwitchRepository,
    kill_switch_from_row,
    kill_switch_to_row,
)
from pmrp.storage.repositories.outbox import (
    CANONICAL_EVENTS_TOPIC,
    CanonicalEventContract,
    OutboxMessageRepository,
    outbox_message_to_row,
)
from pmrp.storage.repositories.protocols import Repository, VersionedRepository
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
from pmrp.storage.repositories.risk_limits import (
    RiskLimitRepository,
    risk_limit_from_row,
    risk_limit_to_row,
)
from pmrp.storage.repositories.risk_unit_of_work import SqlAlchemyRiskUnitOfWork

__all__ = [
    "CANONICAL_EVENTS_TOPIC",
    "CanonicalEventContract",
    "CapitalReservationRepository",
    "KillSwitchRepository",
    "OutboxMessageRepository",
    "Repository",
    "RiskBreachRepository",
    "RiskDecisionRepository",
    "RiskLimitRepository",
    "SqlAlchemyRiskUnitOfWork",
    "VersionedRepository",
    "capital_reservation_from_row",
    "capital_reservation_to_row",
    "kill_switch_from_row",
    "kill_switch_to_row",
    "outbox_message_to_row",
    "risk_breach_from_row",
    "risk_breach_to_row",
    "risk_decision_from_row",
    "risk_decision_to_row",
    "risk_limit_from_row",
    "risk_limit_to_row",
]
