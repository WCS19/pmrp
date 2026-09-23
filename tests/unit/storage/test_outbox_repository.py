"""Tests for transactional outbox repository mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from pmrp.schemas.enums import ExchangeName, OrderType, Side, TimeInForce
from pmrp.schemas.events import (
    RISK_CHECK_REQUESTED_EVENT_TYPE,
    EventEnvelope,
    RiskCheckRequestedEvent,
)
from pmrp.schemas.identifiers import AccountId, ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskInputSnapshot
from pmrp.storage import PersistenceTimeoutError
from pmrp.storage.models import OutboxMessageRow
from pmrp.storage.repositories import (
    CANONICAL_EVENTS_TOPIC,
    OutboxMessageRepository,
    outbox_message_to_row,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_outbox_repository")
CONTRACT_ID = ContractId("ctr_outbox_repository")
STRATEGY_ID = StrategyId("strat_outbox_repository")
ACCOUNT_ID = AccountId("acct_01k00000000000000000000000")


def test_outbox_message_to_row_serializes_canonical_event_payload() -> None:
    event = _risk_check_requested_event()

    row = outbox_message_to_row(event)

    assert row.event_id == "evt_outbox_repository_0001"
    assert row.topic == CANONICAL_EVENTS_TOPIC
    assert row.partition_key == "kalshi:mkt_outbox_repository"
    assert row.payload["envelope"] == {
        "account_id": "acct_01k00000000000000000000000",
        "attributes": {},
        "causation_id": None,
        "correlation_id": "corr_outbox_repository",
        "event_id": "evt_outbox_repository_0001",
        "event_type": RISK_CHECK_REQUESTED_EVENT_TYPE,
        "exchange": "kalshi",
        "market_id": "mkt_outbox_repository",
        "occurred_at": "2026-09-22T12:00:00Z",
        "order_id": None,
        "producer": "risk",
        "published_at": "2026-09-22T12:00:00Z",
        "quality_flags": [],
        "received_at": "2026-09-22T12:00:00Z",
        "replay_session_id": None,
        "schema_version": 1,
        "simulation_session_id": None,
        "strategy_id": "strat_outbox_repository",
        "trace_id": None,
    }
    assert row.payload["intent"]["quantity"] == "10"
    assert row.payload["input_snapshot"]["available_balance"] == "100.00"


def test_outbox_message_to_row_allows_explicit_topic_and_partition_key() -> None:
    row = outbox_message_to_row(
        _risk_check_requested_event(),
        topic="risk-events",
        partition_key="risk:corr_outbox_repository",
    )

    assert row.topic == "risk-events"
    assert row.partition_key == "risk:corr_outbox_repository"


@pytest.mark.parametrize("topic", ["", " risk-events", "risk-events "])
def test_outbox_message_to_row_rejects_invalid_topic(topic: str) -> None:
    with pytest.raises(ValueError, match="topic"):
        outbox_message_to_row(_risk_check_requested_event(), topic=topic)


@pytest.mark.parametrize("partition_key", ["", " partition", "partition "])
def test_outbox_message_to_row_rejects_invalid_partition_key(partition_key: str) -> None:
    with pytest.raises(ValueError, match="partition_key"):
        outbox_message_to_row(
            _risk_check_requested_event(),
            partition_key=partition_key,
        )


def test_outbox_message_to_row_requires_canonical_event_model() -> None:
    with pytest.raises(TypeError, match="canonical model"):
        outbox_message_to_row(object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_repository_add_events_inserts_rows_and_flushes_once() -> None:
    session = _FakeSession()
    repository = OutboxMessageRepository(session)  # type: ignore[arg-type]

    await repository.add_events((_risk_check_requested_event(), _risk_check_requested_event()))

    assert len(session.added) == 2
    assert {row.topic for row in session.added} == {CANONICAL_EVENTS_TOPIC}
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_add_event_classifies_sqlalchemy_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = OutboxMessageRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add_event(_risk_check_requested_event())


def _risk_check_requested_event() -> RiskCheckRequestedEvent:
    return RiskCheckRequestedEvent(
        envelope=EventEnvelope(
            event_id="evt_outbox_repository_0001",
            event_type=RISK_CHECK_REQUESTED_EVENT_TYPE,
            schema_version=1,
            occurred_at=NOW,
            received_at=NOW,
            published_at=NOW,
            producer="risk",
            exchange=ExchangeName.KALSHI.value,
            market_id=MARKET_ID,
            account_id=ACCOUNT_ID,
            strategy_id=STRATEGY_ID,
            correlation_id="corr_outbox_repository",
        ),
        intent=_intent(),
        input_snapshot=_input_snapshot(),
    )


def _intent() -> OrderIntent:
    return OrderIntent(
        intent_id="intent_outbox_repository",
        strategy_id=STRATEGY_ID,
        market_id=MARKET_ID,
        contract_id=CONTRACT_ID,
        outcome_id="out_yes",
        side=Side.BUY,
        quantity=Decimal("10"),
        limit_price=Decimal("0.50"),
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        post_only=False,
        reduce_only=False,
        urgency=Decimal("0.50"),
        created_at=NOW - timedelta(seconds=2),
        expires_at=NOW + timedelta(seconds=5),
        signal_ids=(),
        correlation_id="corr_outbox_repository",
        idempotency_key="idem-outbox-repository",
    )


def _input_snapshot() -> RiskInputSnapshot:
    return RiskInputSnapshot(
        risk_input_snapshot_id="risk_input_outbox_repo",
        captured_at=NOW - timedelta(seconds=1),
        strategy_id=STRATEGY_ID,
        exchange=ExchangeName.KALSHI.value,
        account_id=ACCOUNT_ID,
        market_id=MARKET_ID,
        current_position=Decimal("2"),
        open_order_quantity=Decimal("3"),
        available_balance=Decimal("100.00"),
        gross_exposure=Decimal("40.00"),
        net_exposure=Decimal("25.00"),
        daily_realized_pnl=Decimal("1.00"),
        daily_unrealized_pnl=Decimal("-0.25"),
        market_data_age_ms=250,
        reconciliation_healthy=True,
        kill_switch_clear=True,
    )


class _FakeSession:
    def __init__(self, *, flush_error: Exception | None = None) -> None:
        self.added: list[OutboxMessageRow] = []
        self.flushed = 0
        self.committed = 0
        self._flush_error = flush_error

    def add(self, row: OutboxMessageRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        if self._flush_error is not None:
            raise self._flush_error
        self.flushed += 1
