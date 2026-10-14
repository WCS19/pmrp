"""Portfolio event persistence workflows."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from pmrp.portfolio.events import PortfolioCanonicalEvent
from pmrp.schemas.events import (
    CashBalanceChangedEvent,
    PnlUpdatedEvent,
    PortfolioMismatchDetectedEvent,
    PortfolioReconciledEvent,
    PositionChangedEvent,
)

_PORTFOLIO_EVENT_TYPES = (
    CashBalanceChangedEvent,
    PnlUpdatedEvent,
    PortfolioMismatchDetectedEvent,
    PortfolioReconciledEvent,
    PositionChangedEvent,
)


class PortfolioEventStore(Protocol):
    """Persistence boundary for canonical portfolio events."""

    async def add_events(self, events: Iterable[PortfolioCanonicalEvent]) -> None:
        """Persist portfolio events without committing independently."""
        ...


@runtime_checkable
class PortfolioEventUnitOfWork(Protocol):
    """Unit of work that can persist canonical portfolio events and outbox rows."""

    async def __aenter__(self) -> Self:
        """Open the unit of work transaction."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Close the unit of work transaction."""
        ...

    @property
    def canonical_events(self) -> PortfolioEventStore:
        """Return the active canonical event store."""
        ...

    @property
    def outbox_messages(self) -> PortfolioEventStore:
        """Return the active outbox event store."""
        ...

    async def commit(self) -> None:
        """Commit the active transaction."""
        ...


type PortfolioEventUnitOfWorkFactory = Callable[[], PortfolioEventUnitOfWork]


@dataclass(frozen=True, slots=True)
class PortfolioEventPersistenceResult:
    """Portfolio events persisted in deterministic publication order."""

    events: tuple[PortfolioCanonicalEvent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.events, tuple):
            raise TypeError("portfolio event persistence result events must be a tuple")
        _validate_portfolio_events(self.events)

    @property
    def event_count(self) -> int:
        """Return the number of persisted portfolio events."""

        return len(self.events)


@dataclass(frozen=True, slots=True)
class PortfolioEventWorkflow:
    """Persist canonical portfolio events and matching outbox rows atomically."""

    unit_of_work_factory: PortfolioEventUnitOfWorkFactory

    async def persist_events(
        self,
        events: Iterable[PortfolioCanonicalEvent],
    ) -> PortfolioEventPersistenceResult:
        """Persist portfolio events to durable event storage and the outbox."""

        event_tuple = tuple(events)
        _validate_portfolio_events(event_tuple)
        async with self.unit_of_work_factory() as unit_of_work:
            await unit_of_work.canonical_events.add_events(event_tuple)
            await unit_of_work.outbox_messages.add_events(event_tuple)
            await unit_of_work.commit()
        return PortfolioEventPersistenceResult(events=event_tuple)


def _validate_portfolio_events(events: tuple[object, ...]) -> None:
    if not events:
        raise ValueError("portfolio event workflow requires at least one event")
    if any(not isinstance(event, _PORTFOLIO_EVENT_TYPES) for event in events):
        raise TypeError("portfolio event workflow requires portfolio canonical events")
