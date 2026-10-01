"""Tests for canonical event repository mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from pmrp.schemas.enums import (
    DataQualityFlag,
    ExchangeName,
    OrderType,
    Side,
    TimeInForce,
)
from pmrp.schemas.events import (
    RISK_CHECK_REQUESTED_EVENT_TYPE,
    EventEnvelope,
    RiskCheckRequestedEvent,
)
from pmrp.schemas.identifiers import AccountId, ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskInputSnapshot
from pmrp.schemas.serialization import canonical_sha256
from pmrp.storage import PersistenceTimeoutError
from pmrp.storage.models import CanonicalEventRow, EventIdRow
from pmrp.storage.repositories import CanonicalEventRepository, canonical_event_to_rows

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_canonical_event_repo")
CONTRACT_ID = ContractId("ctr_canonical_event_repo")
STRATEGY_ID = StrategyId("strat_canonical_event_repo")
ACCOUNT_ID = AccountId("acct_01k00000000000000000000000")


def test_canonical_event_to_rows_serializes_event_payload_and_lineage() -> None:
    event = _risk_check_requested_event()

    event_id_row, event_row = canonical_event_to_rows(event)

    assert event_id_row.event_id == "evt_canonical_event_repo_0001"
    assert event_id_row.occurred_at == NOW
    assert event_row.occurred_at == NOW
    assert event_row.event_id == "evt_canonical_event_repo_0001"
    assert event_row.event_type == RISK_CHECK_REQUESTED_EVENT_TYPE
    assert event_row.schema_version == 1
    assert event_row.received_at == NOW + timedelta(milliseconds=100)
    assert event_row.published_at == NOW + timedelta(milliseconds=200)
    assert event_row.producer == "risk"
    assert event_row.exchange == "kalshi"
    assert event_row.market_id == "mkt_canonical_event_repo"
    assert event_row.account_id == "acct_01k00000000000000000000000"
    assert event_row.strategy_id == "strat_canonical_event_repo"
    assert event_row.order_id is None
    assert event_row.correlation_id == "corr_canonical_event_repo"
    assert event_row.causation_id == "evt_canonical_event_repo_cause"
    assert event_row.trace_id == "trace-canonical-event-repo"
    assert event_row.replay_session_id is None
    assert event_row.simulation_session_id is None
    assert event_row.quality_flags == ["replayed"]
    assert event_row.attributes == {"attempt": 1, "source": "unit"}
    assert event_row.payload["envelope"]["attributes"] == {"attempt": 1, "source": "unit"}
    assert event_row.payload["intent"]["quantity"] == "10"
    assert event_row.payload["input_snapshot"]["available_balance"] == "100.00"
    assert event_row.payload_hash == canonical_sha256(event)


def test_canonical_event_to_rows_requires_canonical_event_model() -> None:
    with pytest.raises(TypeError, match="canonical event"):
        canonical_event_to_rows(object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_repository_add_events_inserts_event_id_and_event_rows() -> None:
    session = _FakeSession()
    repository = CanonicalEventRepository(session)  # type: ignore[arg-type]

    await repository.add_events((_risk_check_requested_event(), _risk_check_requested_event()))

    assert len(session.added) == 4
    assert isinstance(session.added[0], EventIdRow)
    assert isinstance(session.added[1], CanonicalEventRow)
    assert isinstance(session.added[2], EventIdRow)
    assert isinstance(session.added[3], CanonicalEventRow)
    assert session.flushed == 1
    assert session.committed == 0


@pytest.mark.asyncio
async def test_repository_add_event_classifies_sqlalchemy_flush_errors() -> None:
    session = _FakeSession(flush_error=SQLAlchemyTimeoutError("pool exhausted"))
    repository = CanonicalEventRepository(session)  # type: ignore[arg-type]

    with pytest.raises(PersistenceTimeoutError, match="timed out"):
        await repository.add_event(_risk_check_requested_event())


def _risk_check_requested_event() -> RiskCheckRequestedEvent:
    return RiskCheckRequestedEvent(
        envelope=EventEnvelope(
            event_id="evt_canonical_event_repo_0001",
            event_type=RISK_CHECK_REQUESTED_EVENT_TYPE,
            schema_version=1,
            occurred_at=NOW,
            received_at=NOW + timedelta(milliseconds=100),
            published_at=NOW + timedelta(milliseconds=200),
            producer="risk",
            exchange=ExchangeName.KALSHI.value,
            market_id=MARKET_ID,
            account_id=ACCOUNT_ID,
            strategy_id=STRATEGY_ID,
            correlation_id="corr_canonical_event_repo",
            causation_id="evt_canonical_event_repo_cause",
            trace_id="trace-canonical-event-repo",
            quality_flags=(DataQualityFlag.REPLAYED,),
            attributes={"attempt": 1, "source": "unit"},
        ),
        intent=_intent(),
        input_snapshot=_input_snapshot(),
    )


def _intent() -> OrderIntent:
    return OrderIntent(
        intent_id="intent_canonical_event_repo",
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
        correlation_id="corr_canonical_event_repo",
        idempotency_key="idem-canonical-event-repo",
    )


def _input_snapshot() -> RiskInputSnapshot:
    return RiskInputSnapshot(
        risk_input_snapshot_id="risk_input_canonical_event_repo",
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
        self.added: list[EventIdRow | CanonicalEventRow] = []
        self.flushed = 0
        self.committed = 0
        self._flush_error = flush_error

    def add(self, row: EventIdRow | CanonicalEventRow) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        if self._flush_error is not None:
            raise self._flush_error
        self.flushed += 1
