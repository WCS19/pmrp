"""Factories for canonical risk event contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pmrp.events import EventFactory
from pmrp.risk.service import RiskEvaluationResult
from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.events import (
    RISK_APPROVED_EVENT_TYPE,
    RISK_CHECK_REQUESTED_EVENT_TYPE,
    RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE,
    RISK_KILL_SWITCH_RELEASED_EVENT_TYPE,
    RISK_LIMIT_BREACHED_EVENT_TYPE,
    RISK_REJECTED_EVENT_TYPE,
    KillSwitchActivatedEvent,
    KillSwitchReleasedEvent,
    RiskApprovedEvent,
    RiskCheckRequestedEvent,
    RiskLimitBreachedEvent,
    RiskRejectedEvent,
)
from pmrp.schemas.orders import ApprovedOrder, OrderIntent
from pmrp.schemas.risk import KillSwitchState, RiskBreach, RiskDecision, RiskInputSnapshot

RiskEvaluationCanonicalEvent = RiskApprovedEvent | RiskRejectedEvent | RiskLimitBreachedEvent


@dataclass(frozen=True, slots=True)
class RiskEventFactory:
    """Build canonical risk events with validated envelope lineage."""

    event_factory: EventFactory
    producer: str = "risk"

    def build_check_requested_event(
        self,
        intent: OrderIntent,
        input_snapshot: RiskInputSnapshot,
    ) -> RiskCheckRequestedEvent:
        """Build the event that records a pre-trade risk check request."""

        return RiskCheckRequestedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=RISK_CHECK_REQUESTED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=input_snapshot.captured_at,
                exchange=input_snapshot.exchange,
                market_id=intent.market_id,
                account_id=input_snapshot.account_id,
                strategy_id=intent.strategy_id,
                correlation_id=intent.correlation_id,
            ),
            intent=intent,
            input_snapshot=input_snapshot,
        )

    def build_approved_event(
        self,
        decision: RiskDecision,
        approved_order: ApprovedOrder,
    ) -> RiskApprovedEvent:
        """Build the event that records an approved risk decision."""

        return RiskApprovedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=RISK_APPROVED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=decision.evaluated_at,
                exchange=approved_order.exchange,
                market_id=approved_order.market_id,
                account_id=approved_order.account_id,
                strategy_id=approved_order.strategy_id,
                order_id=approved_order.order_id,
                correlation_id=decision.correlation_id,
            ),
            decision=decision,
            approved_order=approved_order,
        )

    def build_rejected_event(
        self,
        decision: RiskDecision,
        *,
        intent: OrderIntent | None = None,
    ) -> RiskRejectedEvent:
        """Build the event that records a rejected risk decision."""

        if intent is not None:
            _validate_decision_intent_lineage(decision, intent)
        return RiskRejectedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=RISK_REJECTED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=decision.evaluated_at,
                market_id=intent.market_id if intent is not None else None,
                strategy_id=intent.strategy_id if intent is not None else None,
                correlation_id=decision.correlation_id,
            ),
            decision=decision,
        )

    def build_limit_breached_event(self, breach: RiskBreach) -> RiskLimitBreachedEvent:
        """Build the event that records a risk limit breach."""

        return RiskLimitBreachedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=RISK_LIMIT_BREACHED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=breach.detected_at,
                correlation_id=breach.correlation_id,
            ),
            breach=breach,
        )

    def build_kill_switch_activated_event(
        self,
        state: KillSwitchState,
    ) -> KillSwitchActivatedEvent:
        """Build the event that records kill-switch activation."""

        return KillSwitchActivatedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=_required_datetime(
                    state.activated_at,
                    field_name="activated_at",
                ),
            ),
            state=state,
        )

    def build_kill_switch_released_event(
        self,
        state: KillSwitchState,
    ) -> KillSwitchReleasedEvent:
        """Build the event that records kill-switch release."""

        return KillSwitchReleasedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=RISK_KILL_SWITCH_RELEASED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=_required_datetime(
                    state.released_at,
                    field_name="released_at",
                ),
            ),
            state=state,
        )

    def build_evaluation_events(
        self,
        result: RiskEvaluationResult,
        *,
        breaches: tuple[RiskBreach, ...] | None = None,
        intent: OrderIntent | None = None,
    ) -> tuple[RiskEvaluationCanonicalEvent, ...]:
        """Build the canonical events implied by one persisted risk evaluation."""

        decision_event: RiskApprovedEvent | RiskRejectedEvent
        if result.decision.status is RiskDecisionStatus.APPROVED:
            if result.approved_order is None:
                msg = "approved risk evaluation result requires approved_order to build event"
                raise ValueError(msg)
            decision_event = self.build_approved_event(result.decision, result.approved_order)
        elif result.decision.status is RiskDecisionStatus.REJECTED:
            decision_event = self.build_rejected_event(result.decision, intent=intent)
        else:
            msg = "risk evaluation events require an approved or rejected decision"
            raise ValueError(msg)

        effective_breaches = result.breaches if breaches is None else breaches
        breach_events = tuple(
            self.build_limit_breached_event(breach) for breach in effective_breaches
        )
        return (decision_event, *breach_events)


def _validate_decision_intent_lineage(decision: RiskDecision, intent: OrderIntent) -> None:
    if decision.intent_id != intent.intent_id:
        msg = "risk decision intent_id must match intent"
        raise ValueError(msg)
    if decision.correlation_id != intent.correlation_id:
        msg = "risk decision correlation_id must match intent"
        raise ValueError(msg)


def _required_datetime(value: datetime | None, *, field_name: str) -> datetime:
    if value is None:
        msg = f"kill-switch {field_name} is required to build event"
        raise ValueError(msg)
    return value
