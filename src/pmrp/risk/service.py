"""Application service for deterministic pre-trade risk evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Protocol, Self

from pmrp.risk.breaches import RiskBreachFactory
from pmrp.risk.context import RiskContext
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

    async def commit(self) -> None:
        """Commit the transaction after all risk records are persisted."""
        ...


type RiskEvaluationUnitOfWorkFactory = Callable[[], RiskEvaluationUnitOfWork]


@dataclass(frozen=True, slots=True)
class RiskEvaluationService:
    """Evaluate risk and persist the immutable decision in one transaction."""

    engine: RiskDecisionEvaluator
    unit_of_work_factory: RiskEvaluationUnitOfWorkFactory
    breach_factory: RiskBreachFactory | None = None

    async def evaluate_and_persist(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        input_snapshot_id: str,
    ) -> RiskDecision:
        """Evaluate risk rules, persist the decision, commit, and return it."""

        async with self.unit_of_work_factory() as unit_of_work:
            decision = await self.engine.evaluate(
                intent,
                context,
                input_snapshot_id=input_snapshot_id,
            )
            await unit_of_work.risk_decisions.add(decision)
            if self.breach_factory is not None:
                for breach in self.breach_factory.breaches_for_decision(decision):
                    await unit_of_work.risk_breaches.add(breach)
            await unit_of_work.commit()
            return decision
