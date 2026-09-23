"""Application service for deterministic pre-trade risk evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Protocol, Self

from pmrp.risk.breaches import RiskBreachFactory
from pmrp.risk.context import RiskContext
from pmrp.risk.reservations import CapitalReservation, CapitalReservationFactory
from pmrp.schemas.enums import ExchangeName, RiskDecisionStatus
from pmrp.schemas.identifiers import AccountId
from pmrp.schemas.numeric import validate_currency
from pmrp.schemas.orders import OrderIntent
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
class RiskEvaluationService:
    """Evaluate risk and persist the immutable decision in one transaction."""

    engine: RiskDecisionEvaluator
    unit_of_work_factory: RiskEvaluationUnitOfWorkFactory
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
        """Evaluate risk rules, persist the decision, commit, and return it."""

        async with self.unit_of_work_factory() as unit_of_work:
            decision = await self.engine.evaluate(
                intent,
                context,
                input_snapshot_id=input_snapshot_id,
            )
            await unit_of_work.risk_decisions.add(decision)
            if decision.status is RiskDecisionStatus.APPROVED and reservation_request is not None:
                reservation_factory = self.reservation_factory or CapitalReservationFactory()
                reservation = reservation_factory.build(
                    intent,
                    decision,
                    exchange=reservation_request.exchange,
                    account_id=reservation_request.account_id,
                    currency=reservation_request.currency,
                )
                await unit_of_work.capital_reservations.add(reservation)
            if self.breach_factory is not None:
                for breach in self.breach_factory.breaches_for_decision(decision):
                    await unit_of_work.risk_breaches.add(breach)
            await unit_of_work.commit()
            return decision
