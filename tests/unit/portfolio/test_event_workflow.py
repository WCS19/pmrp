"""Unit tests for portfolio event persistence workflows."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from types import TracebackType

import pytest

from pmrp.clock import FrozenClock
from pmrp.events import (
    DeterministicEventIdentifierGenerator,
    EventFactory,
    default_event_type_registry,
)
from pmrp.portfolio import (
    PortfolioCanonicalEvent,
    PortfolioEventFactory,
    PortfolioEventUnitOfWork,
    PortfolioEventWorkflow,
)
from pmrp.schemas.identifiers import AccountId
from pmrp.schemas.portfolio import ReconciliationResult, ReconciliationStatus

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
ACCOUNT_ID = AccountId("acct_portfolio_event_workflow")


@pytest.mark.asyncio
async def test_portfolio_event_workflow_persists_events_and_commits() -> None:
    unit_of_work = _FakePortfolioUnitOfWork()
    event = _portfolio_event_factory().build_reconciliation_event(_reconciliation_result())
    workflow = PortfolioEventWorkflow(unit_of_work_factory=lambda: unit_of_work)

    result = await workflow.persist_events((event,))

    assert result.events == (event,)
    assert result.event_count == 1
    assert unit_of_work.canonical_events.events == (event,)
    assert unit_of_work.outbox_messages.events == (event,)
    assert unit_of_work.entered == 1
    assert unit_of_work.committed == 1
    assert unit_of_work.rolled_back == 0
    assert unit_of_work.exited == 1


@pytest.mark.asyncio
async def test_portfolio_event_workflow_rejects_empty_event_batch() -> None:
    unit_of_work = _FakePortfolioUnitOfWork()
    workflow = PortfolioEventWorkflow(unit_of_work_factory=lambda: unit_of_work)

    with pytest.raises(ValueError, match="at least one event"):
        await workflow.persist_events(())

    assert unit_of_work.entered == 0
    assert unit_of_work.committed == 0
    assert unit_of_work.rolled_back == 0
    assert unit_of_work.exited == 0


@pytest.mark.asyncio
async def test_portfolio_event_workflow_rejects_nonportfolio_events_before_transaction() -> None:
    unit_of_work = _FakePortfolioUnitOfWork()
    workflow = PortfolioEventWorkflow(unit_of_work_factory=lambda: unit_of_work)

    with pytest.raises(TypeError, match="portfolio canonical events"):
        await workflow.persist_events((object(),))  # type: ignore[arg-type]

    assert unit_of_work.entered == 0
    assert unit_of_work.committed == 0
    assert unit_of_work.rolled_back == 0
    assert unit_of_work.exited == 0


@pytest.mark.asyncio
async def test_portfolio_event_workflow_rolls_back_when_outbox_persistence_fails() -> None:
    unit_of_work = _FakePortfolioUnitOfWork(outbox_error=RuntimeError("outbox unavailable"))
    event = _portfolio_event_factory().build_reconciliation_event(_reconciliation_result())
    workflow = PortfolioEventWorkflow(unit_of_work_factory=lambda: unit_of_work)

    with pytest.raises(RuntimeError, match="outbox unavailable"):
        await workflow.persist_events((event,))

    assert unit_of_work.canonical_events.events == (event,)
    assert unit_of_work.outbox_messages.events == ()
    assert unit_of_work.entered == 1
    assert unit_of_work.committed == 0
    assert unit_of_work.rolled_back == 1
    assert unit_of_work.exited == 1


def test_fake_portfolio_unit_of_work_conforms_to_event_workflow_protocol() -> None:
    unit_of_work = _FakePortfolioUnitOfWork()

    assert isinstance(unit_of_work, PortfolioEventUnitOfWork)


def _portfolio_event_factory() -> PortfolioEventFactory:
    return PortfolioEventFactory(
        event_factory=EventFactory(
            clock=FrozenClock(NOW),
            registry=default_event_type_registry(),
            identifier_generator=DeterministicEventIdentifierGenerator(),
        )
    )


def _reconciliation_result() -> ReconciliationResult:
    return ReconciliationResult(
        reconciliation_id="recon_portfolio_event_workflow",
        exchange="kalshi",
        account_id=ACCOUNT_ID,
        started_at=NOW - timedelta(seconds=3),
        completed_at=NOW - timedelta(seconds=1),
        status=ReconciliationStatus.HEALTHY,
        mismatches=(),
        open_orders_checked=1,
        positions_checked=2,
        balances_checked=1,
        fills_checked=3,
        trading_gate_released=True,
    )


class _FakePortfolioEventStore:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.events: tuple[PortfolioCanonicalEvent, ...] = ()
        self._error = error

    async def add_events(self, events: Iterable[PortfolioCanonicalEvent]) -> None:
        if self._error is not None:
            raise self._error
        self.events = (*self.events, *tuple(events))


class _FakePortfolioUnitOfWork:
    def __init__(self, *, outbox_error: Exception | None = None) -> None:
        self.canonical_events = _FakePortfolioEventStore()
        self.outbox_messages = _FakePortfolioEventStore(error=outbox_error)
        self.entered = 0
        self.exited = 0
        self.committed = 0
        self.rolled_back = 0

    async def __aenter__(self) -> _FakePortfolioUnitOfWork:
        self.entered += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc, traceback
        self.exited += 1
        if exc_type is not None and self.committed == 0:
            self.rolled_back += 1
        return False

    async def commit(self) -> None:
        self.committed += 1
