"""Risk evaluation workflows that assemble canonical event contracts."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pmrp.risk.context import RiskContext
from pmrp.risk.events import RiskEvaluationCanonicalEvent, RiskEventFactory
from pmrp.risk.service import (
    RiskApprovedOrderRequest,
    RiskCapitalReservationRequest,
    RiskEvaluationBeforeCommitHook,
    RiskEvaluationResult,
    RiskEvaluationUnitOfWork,
)
from pmrp.schemas.events import RiskCheckRequestedEvent
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskInputSnapshot

type RiskEvaluationWorkflowEvent = RiskCheckRequestedEvent | RiskEvaluationCanonicalEvent


class RiskEvaluationEventStore(Protocol):
    """Persistence boundary for canonical risk workflow events."""

    async def add_events(self, events: Iterable[RiskEvaluationWorkflowEvent]) -> None:
        """Persist risk workflow events without committing independently."""
        ...


@runtime_checkable
class RiskEvaluationEventUnitOfWork(Protocol):
    """Unit of work that can persist canonical events and outbox rows."""

    @property
    def canonical_events(self) -> RiskEvaluationEventStore:
        """Return the active canonical event store."""
        ...

    @property
    def outbox_messages(self) -> RiskEvaluationEventStore:
        """Return the active outbox event store."""
        ...


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
        before_commit: RiskEvaluationBeforeCommitHook | None = None,
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
        return self._build_event_result(
            result,
            intent=intent,
            check_requested_event=check_requested_event,
        )

    async def evaluate_persist_and_build_events(
        self,
        intent: OrderIntent,
        context: RiskContext,
        input_snapshot: RiskInputSnapshot,
        *,
        approved_order_request: RiskApprovedOrderRequest | None = None,
        reservation_request: RiskCapitalReservationRequest | None = None,
    ) -> RiskEvaluationEventResult:
        """Run risk evaluation and persist its canonical events before commit."""

        check_requested_event = self.event_factory.build_check_requested_event(
            intent,
            input_snapshot,
        )
        event_result: RiskEvaluationEventResult | None = None

        async def persist_events_before_commit(
            unit_of_work: RiskEvaluationUnitOfWork,
            result: RiskEvaluationResult,
        ) -> None:
            nonlocal event_result
            event_unit_of_work = _require_event_unit_of_work(unit_of_work)
            built_result = self._build_event_result(
                result,
                intent=intent,
                check_requested_event=check_requested_event,
            )
            await event_unit_of_work.canonical_events.add_events(built_result.all_events)
            await event_unit_of_work.outbox_messages.add_events(built_result.all_events)
            event_result = built_result

        persisted_result = await self.service.evaluate_and_persist_result(
            intent,
            context,
            input_snapshot_id=input_snapshot.risk_input_snapshot_id,
            approved_order_request=approved_order_request,
            reservation_request=reservation_request,
            before_commit=persist_events_before_commit,
        )
        if event_result is None:
            msg = "risk event workflow did not persist events before commit"
            raise RuntimeError(msg)
        if event_result.result != persisted_result:
            msg = "risk event workflow persisted events for a different result"
            raise RuntimeError(msg)
        return event_result

    def _build_event_result(
        self,
        result: RiskEvaluationResult,
        *,
        intent: OrderIntent,
        check_requested_event: RiskCheckRequestedEvent,
    ) -> RiskEvaluationEventResult:
        evaluation_events = self.event_factory.build_evaluation_events(
            result,
            intent=intent,
        )
        return RiskEvaluationEventResult(
            result=result,
            check_requested_event=check_requested_event,
            evaluation_events=evaluation_events,
        )


def _require_event_unit_of_work(
    unit_of_work: RiskEvaluationUnitOfWork,
) -> RiskEvaluationEventUnitOfWork:
    if not isinstance(unit_of_work, RiskEvaluationEventUnitOfWork):
        msg = "risk event workflow requires canonical_events and outbox_messages stores"
        raise TypeError(msg)
    return unit_of_work
