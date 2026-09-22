"""Application service for deterministic pre-trade risk evaluation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Protocol, Self

from pmrp.risk.context import RiskContext
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskDecision


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

    async def commit(self) -> None:
        """Commit the transaction after all risk records are persisted."""
        ...


type RiskEvaluationUnitOfWorkFactory = Callable[[], RiskEvaluationUnitOfWork]


@dataclass(frozen=True, slots=True)
class RiskEvaluationService:
    """Evaluate risk and persist the immutable decision in one transaction."""

    engine: RiskDecisionEvaluator
    unit_of_work_factory: RiskEvaluationUnitOfWorkFactory

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
            await unit_of_work.commit()
            return decision
