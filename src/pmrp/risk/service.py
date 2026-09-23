"""Application service for deterministic pre-trade risk evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Protocol, Self

from pmrp.risk.approvals import ApprovedOrderFactory
from pmrp.risk.breaches import RiskBreachFactory
from pmrp.risk.context import RiskContext
from pmrp.risk.reservations import CapitalReservation, CapitalReservationFactory
from pmrp.schemas.enums import ExchangeName, RiskDecisionStatus
from pmrp.schemas.identifiers import AccountId
from pmrp.schemas.numeric import validate_currency
from pmrp.schemas.orders import ApprovedOrder, OrderIntent
from pmrp.schemas.risk import RiskBreach, RiskDecision


class RiskDecisionEvaluator(Protocol):
    """Risk engine boundary used by the application service."""

    async def evaluate(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        input_snapshot_id: str,
    ) -> RiskDecision:
        """Evaluate an order intent into one canonical risk decision."""
        ...


class RiskDecisionStore(Protocol):
    """Persistence boundary for canonical risk decisions."""

    async def add(self, decision: RiskDecision) -> None:
        """Persist a canonical risk decision without committing independently."""
        ...


class RiskBreachStore(Protocol):
    """Persistence boundary for canonical risk breaches."""

    async def add(self, breach: RiskBreach) -> None:
        """Persist a canonical risk breach without committing independently."""
        ...


class CapitalReservationStore(Protocol):
    """Persistence boundary for active pre-trade capital reservations."""

    async def add(self, reservation: CapitalReservation) -> None:
        """Persist a capital reservation without committing independently."""
        ...


class RiskEvaluationUnitOfWork(Protocol):
    """Transaction boundary required by the risk evaluation service."""

    async def __aenter__(self) -> Self:
        """Enter the transaction scope."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Exit the transaction scope."""
        ...

    @property
    def risk_decisions(self) -> RiskDecisionStore:
        """Return the active risk decision store."""
        ...

    @property
    def risk_breaches(self) -> RiskBreachStore:
        """Return the active risk breach store."""
        ...

    @property
    def capital_reservations(self) -> CapitalReservationStore:
        """Return the active capital reservation store."""
        ...

    async def commit(self) -> None:
        """Commit the transaction after all risk records are persisted."""
        ...


type RiskEvaluationUnitOfWorkFactory = Callable[[], RiskEvaluationUnitOfWork]


@dataclass(frozen=True, slots=True)
class RiskApprovedOrderRequest:
    """Metadata required to derive an approved-order contract."""

    exchange: ExchangeName
    account_id: AccountId

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", ExchangeName(self.exchange))
        object.__setattr__(self, "account_id", AccountId(str(self.account_id)))


@dataclass(frozen=True, slots=True)
class RiskCapitalReservationRequest:
    """Metadata required to reserve capital for an approved decision."""

    exchange: ExchangeName
    account_id: AccountId
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "exchange", ExchangeName(self.exchange))
        object.__setattr__(self, "account_id", AccountId(str(self.account_id)))
        object.__setattr__(self, "currency", validate_currency(self.currency))


@dataclass(frozen=True, slots=True)
class RiskEvaluationResult:
    """Outcome of a persisted risk evaluation and optional approval artifacts."""

    decision: RiskDecision
    approved_order: ApprovedOrder | None = None
    capital_reservation: CapitalReservation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RiskDecision):
            raise TypeError("risk evaluation result requires a RiskDecision")
        if self.decision.status is not RiskDecisionStatus.APPROVED:
            if self.approved_order is not None:
                raise ValueError("non-approved risk decisions cannot include an approved order")
            if self.capital_reservation is not None:
                raise ValueError("non-approved risk decisions cannot include a capital reservation")
            return
        if self.approved_order is not None:
            _validate_approved_order_matches_decision(self.approved_order, self.decision)
        if self.capital_reservation is not None:
            _validate_reservation_matches_decision(self.capital_reservation, self.decision)


@dataclass(frozen=True, slots=True)
class RiskEvaluationService:
    """Evaluate risk and persist the immutable decision in one transaction."""

    engine: RiskDecisionEvaluator
    unit_of_work_factory: RiskEvaluationUnitOfWorkFactory
    approved_order_factory: ApprovedOrderFactory | None = None
    breach_factory: RiskBreachFactory | None = None
    reservation_factory: CapitalReservationFactory | None = None

    async def evaluate_and_persist(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        input_snapshot_id: str,
        reservation_request: RiskCapitalReservationRequest | None = None,
    ) -> RiskDecision:
        """Evaluate risk rules, persist the decision, commit, and return the decision."""

        result = await self.evaluate_and_persist_result(
            intent,
            context,
            input_snapshot_id=input_snapshot_id,
            reservation_request=reservation_request,
        )
        return result.decision

    async def evaluate_and_persist_result(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        input_snapshot_id: str,
        approved_order_request: RiskApprovedOrderRequest | None = None,
        reservation_request: RiskCapitalReservationRequest | None = None,
    ) -> RiskEvaluationResult:
        """Evaluate risk, persist risk records, and return optional approval artifacts."""

        async with self.unit_of_work_factory() as unit_of_work:
            decision = await self.engine.evaluate(
                intent,
                context,
                input_snapshot_id=input_snapshot_id,
            )
            await unit_of_work.risk_decisions.add(decision)
            approved_order: ApprovedOrder | None = None
            capital_reservation: CapitalReservation | None = None
            if decision.status is RiskDecisionStatus.APPROVED and reservation_request is not None:
                reservation_factory = self.reservation_factory or CapitalReservationFactory()
                capital_reservation = reservation_factory.build(
                    intent,
                    decision,
                    exchange=reservation_request.exchange,
                    account_id=reservation_request.account_id,
                    currency=reservation_request.currency,
                )
                await unit_of_work.capital_reservations.add(capital_reservation)
            if (
                decision.status is RiskDecisionStatus.APPROVED
                and approved_order_request is not None
            ):
                approved_order_factory = self.approved_order_factory or ApprovedOrderFactory()
                approved_order = approved_order_factory.build(
                    intent,
                    decision,
                    exchange=approved_order_request.exchange.value,
                    account_id=approved_order_request.account_id,
                )
            if self.breach_factory is not None:
                for breach in self.breach_factory.breaches_for_decision(decision):
                    await unit_of_work.risk_breaches.add(breach)
            await unit_of_work.commit()
            return RiskEvaluationResult(
                decision=decision,
                approved_order=approved_order,
                capital_reservation=capital_reservation,
            )


def _validate_approved_order_matches_decision(
    approved_order: ApprovedOrder,
    decision: RiskDecision,
) -> None:
    if not isinstance(approved_order, ApprovedOrder):
        raise TypeError("risk evaluation approved_order must be an ApprovedOrder")
    if approved_order.risk_decision_id != decision.risk_decision_id:
        raise ValueError("approved order risk_decision_id must match decision")
    if approved_order.intent_id != decision.intent_id:
        raise ValueError("approved order intent_id must match decision")
    if approved_order.correlation_id != decision.correlation_id:
        raise ValueError("approved order correlation_id must match decision")


def _validate_reservation_matches_decision(
    reservation: CapitalReservation,
    decision: RiskDecision,
) -> None:
    if not isinstance(reservation, CapitalReservation):
        raise TypeError("risk evaluation capital_reservation must be a CapitalReservation")
    if reservation.intent_id != decision.intent_id:
        raise ValueError("capital reservation intent_id must match decision")
