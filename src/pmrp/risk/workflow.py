"""Risk evaluation workflows that assemble canonical event contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pmrp.risk.context import RiskContext
from pmrp.risk.events import RiskEvaluationCanonicalEvent, RiskEventFactory
from pmrp.risk.service import (
    RiskApprovedOrderRequest,
    RiskCapitalReservationRequest,
    RiskEvaluationResult,
)
from pmrp.schemas.events import RiskCheckRequestedEvent
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskInputSnapshot

type RiskEvaluationWorkflowEvent = RiskCheckRequestedEvent | RiskEvaluationCanonicalEvent


class RiskEvaluationRunner(Protocol):
    """Boundary for services that evaluate and persist one risk decision."""

    async def evaluate_and_persist_result(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        input_snapshot_id: str,
        approved_order_request: RiskApprovedOrderRequest | None = None,
        reservation_request: RiskCapitalReservationRequest | None = None,
    ) -> RiskEvaluationResult:
        """Evaluate risk and return the persisted decision result."""
        ...


@dataclass(frozen=True, slots=True)
class RiskEvaluationEventResult:
    """Risk evaluation result with the canonical events built around it."""

    result: RiskEvaluationResult
    check_requested_event: RiskCheckRequestedEvent
    evaluation_events: tuple[RiskEvaluationCanonicalEvent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.result, RiskEvaluationResult):
            raise TypeError("risk evaluation event result requires a RiskEvaluationResult")
        if not isinstance(self.check_requested_event, RiskCheckRequestedEvent):
            raise TypeError("risk evaluation event result requires a RiskCheckRequestedEvent")
        if not isinstance(self.evaluation_events, tuple):
            raise TypeError("risk evaluation event result evaluation_events must be a tuple")
        if not self.evaluation_events:
            raise ValueError("risk evaluation event result requires at least one event")
        if any(
            not isinstance(event, RiskEvaluationCanonicalEvent) for event in self.evaluation_events
        ):
            raise TypeError("risk evaluation event result events must be risk evaluation events")

    @property
    def all_events(self) -> tuple[RiskEvaluationWorkflowEvent, ...]:
        """Return all events in deterministic publication order."""

        return (self.check_requested_event, *self.evaluation_events)


@dataclass(frozen=True, slots=True)
class RiskEvaluationEventWorkflow:
    """Evaluate risk and build the canonical risk events implied by the result."""

    service: RiskEvaluationRunner
    event_factory: RiskEventFactory

    async def evaluate_and_build_events(
        self,
        intent: OrderIntent,
        context: RiskContext,
        input_snapshot: RiskInputSnapshot,
        *,
        approved_order_request: RiskApprovedOrderRequest | None = None,
        reservation_request: RiskCapitalReservationRequest | None = None,
    ) -> RiskEvaluationEventResult:
        """Run risk evaluation and return its canonical event contracts."""

        check_requested_event = self.event_factory.build_check_requested_event(
            intent,
            input_snapshot,
        )
        result = await self.service.evaluate_and_persist_result(
            intent,
            context,
            input_snapshot_id=input_snapshot.risk_input_snapshot_id,
            approved_order_request=approved_order_request,
            reservation_request=reservation_request,
        )
        evaluation_events = self.event_factory.build_evaluation_events(
            result,
            intent=intent,
        )
        return RiskEvaluationEventResult(
            result=result,
            check_requested_event=check_requested_event,
            evaluation_events=evaluation_events,
        )
