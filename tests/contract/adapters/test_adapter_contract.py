"""Common exchange-adapter contract tests using the deterministic fixture adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pmrp.adapters import (
    AdapterAmbiguousOrderSubmissionError,
    AdapterAuthenticationError,
    AdapterEndpointCategory,
    AdapterProtocolError,
    AdapterRateLimitError,
    AdapterRateLimitRule,
    AdapterSequenceGapError,
    AdapterTimeoutError,
    ExchangeAdapter,
    FixtureAdapter,
    FixtureAdapterFailureMode,
    MarketDataChannel,
    MarketListRequest,
    MarketSubscription,
    RawExchangeEvent,
)
from pmrp.clock import FrozenClock
from pmrp.schemas.enums import Environment, HealthStatus, OrderType, Side, TimeInForce
from pmrp.schemas.orders import CancelOrderRequest, ExchangeOrderRequest

pytestmark = pytest.mark.contract

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "adapters" / "fixture"
FIXED_NOW = datetime(2026, 8, 2, 18, 45, tzinfo=UTC)


def _adapter(
    *,
    failure_mode: FixtureAdapterFailureMode | None = None,
    rate_limit_rule: AdapterRateLimitRule | None = None,
    rate_limit_remaining: int | None = None,
) -> FixtureAdapter:
    return FixtureAdapter(
        fixtures_path=FIXTURE_ROOT / "normal",
        clock=FrozenClock(FIXED_NOW),
        failure_mode=failure_mode,
        rate_limit_rule=rate_limit_rule,
        rate_limit_remaining=rate_limit_remaining,
    )


def _market_list_request() -> MarketListRequest:
    return MarketListRequest(
        exchange="fixture",
        environment=Environment.TEST,
        requested_at=FIXED_NOW,
        correlation_id="corr_01j00000000000000000000001",
        limit=10,
        cursor=None,
        status_filter=(),
        include_closed=False,
    )


def _subscription() -> MarketSubscription:
    return MarketSubscription(
        exchange="fixture",
        environment=Environment.TEST,
        exchange_market_id="FIX-MARKET-001",
        exchange_contract_id="FIX-MARKET-001-YES",
        channels=(MarketDataChannel.ORDER_BOOK, MarketDataChannel.TRADES),
        depth=10,
        requested_at=FIXED_NOW,
        correlation_id="corr_01j00000000000000000000001",
    )


def _order_request() -> ExchangeOrderRequest:
    return ExchangeOrderRequest(
        order_id="ord_01j00000000000000000000000",
        client_order_id="client-order-001",
        exchange="fixture",
        account_id="acct_paper_001",
        exchange_market_id="FIX-MARKET-001",
        exchange_contract_id="FIX-MARKET-001-YES",
        side=Side.BUY,
        quantity="10",
        limit_price="0.43",
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        post_only=True,
        reduce_only=False,
        idempotency_key="idem-submit-001",
        submitted_at=FIXED_NOW,
    )


def _cancel_request() -> CancelOrderRequest:
    return CancelOrderRequest(
        cancel_request_id="cancel_001",
        order_id="ord_01j00000000000000000000000",
        exchange="fixture",
        account_id="acct_paper_001",
        client_order_id="client-order-001",
        exchange_order_id="fixture-client-order-001",
        requested_at=FIXED_NOW,
        idempotency_key="idem-cancel-001",
        correlation_id="corr_01j00000000000000000000001",
    )


@pytest.mark.asyncio
async def test_fixture_adapter_satisfies_exchange_adapter_protocol() -> None:
    adapter = _adapter()

    assert isinstance(adapter, ExchangeAdapter)
    assert adapter.capabilities.has_order_type(OrderType.LIMIT)


@pytest.mark.asyncio
async def test_adapter_contract_connection_lifecycle_and_health() -> None:
    adapter = _adapter()

    initial_health = await adapter.health()
    assert initial_health.status is HealthStatus.UNHEALTHY
    assert initial_health.connected is False

    await adapter.connect()
    connected_health = await adapter.health()
    assert connected_health.status is HealthStatus.HEALTHY
    assert connected_health.connected is True
    assert connected_health.authenticated is True
    assert connected_health.trading_gate_open is False

    await adapter.disconnect()
    await adapter.disconnect()
    disconnected_health = await adapter.health()
    assert disconnected_health.status is HealthStatus.UNHEALTHY
    assert disconnected_health.connected is False


@pytest.mark.asyncio
async def test_adapter_contract_authentication_failure_is_classified() -> None:
    adapter = _adapter(failure_mode=FixtureAdapterFailureMode.AUTHENTICATION)

    with pytest.raises(AdapterAuthenticationError) as exc_info:
        await adapter.connect()

    assert exc_info.value.context["endpoint_category"] == "authentication"


@pytest.mark.asyncio
async def test_adapter_contract_market_listing_returns_raw_models() -> None:
    adapter = _adapter()

    await adapter.connect()
    markets = await adapter.list_markets(_market_list_request())

    assert len(markets) == 1
    assert markets[0].exchange_market_id == "FIX-MARKET-001"
    assert markets[0].raw_event.payload_text is not None


@pytest.mark.asyncio
async def test_adapter_contract_subscription_lifecycle_is_deterministic() -> None:
    adapter = _adapter()
    await adapter.connect()

    events = await _collect_events(adapter.subscribe_market_data((_subscription(),)))

    assert [event.sequence for event in events] == [1, 2]
    health = await adapter.health()
    assert health.subscriptions_active is True
    assert health.market_data_fresh is True


@pytest.mark.asyncio
async def test_adapter_contract_sequence_gap_is_surfaced() -> None:
    adapter = _adapter(failure_mode=FixtureAdapterFailureMode.SEQUENCE_GAP)
    await adapter.connect()

    with pytest.raises(AdapterSequenceGapError):
        await _collect_events(adapter.subscribe_market_data((_subscription(),)))


@pytest.mark.asyncio
async def test_adapter_contract_order_submission_is_typed_and_idempotent() -> None:
    adapter = _adapter()
    request = _order_request()

    await adapter.connect()
    first_ack = await adapter.place_order(request)
    second_ack = await adapter.place_order(request)

    assert first_ack.accepted is True
    assert first_ack == second_ack
    assert first_ack.exchange_order_id == "fixture-client-order-001"


@pytest.mark.asyncio
async def test_adapter_contract_ambiguous_submission_is_explicit() -> None:
    adapter = _adapter(failure_mode=FixtureAdapterFailureMode.AMBIGUOUS_SUBMISSION)
    await adapter.connect()

    with pytest.raises(AdapterAmbiguousOrderSubmissionError) as exc_info:
        await adapter.place_order(_order_request())

    assert exc_info.value.requires_reconciliation is True


@pytest.mark.asyncio
async def test_adapter_contract_cancel_is_typed_and_idempotent() -> None:
    adapter = _adapter()
    request = _cancel_request()

    await adapter.connect()
    first_ack = await adapter.cancel_order(request)
    second_ack = await adapter.cancel_order(request)

    assert first_ack.accepted is True
    assert first_ack == second_ack
    assert first_ack.exchange_status == "cancelled"


@pytest.mark.asyncio
async def test_adapter_contract_account_snapshot_queries_are_supported() -> None:
    adapter = _adapter()

    await adapter.connect()
    open_orders = await adapter.get_open_orders()
    positions = await adapter.get_positions()
    balances = await adapter.get_balances()
    fills = await adapter.get_recent_fills()

    assert open_orders[0].exchange_order_id == "fixture-order-001"
    assert positions[0].exchange_position_id == "fixture-position-001"
    assert balances[0].currency == "USD"
    assert fills[0].exchange_fill_id == "fixture-fill-001"


@pytest.mark.asyncio
async def test_adapter_contract_rate_limit_is_visible() -> None:
    rule = AdapterRateLimitRule(
        exchange="fixture",
        endpoint_category=AdapterEndpointCategory.MARKET_DATA,
        operation="list_markets",
        window_name="minute",
        limit=1,
        window_seconds=60,
        cost=1,
    )
    adapter = _adapter(rate_limit_rule=rule, rate_limit_remaining=0)

    await adapter.connect()
    with pytest.raises(AdapterRateLimitError) as exc_info:
        await adapter.list_markets(_market_list_request())

    assert exc_info.value.retryable is True
    assert adapter.last_rate_limit_decision is not None
    assert adapter.last_rate_limit_decision.allowed is False


@pytest.mark.asyncio
async def test_adapter_contract_timeout_is_classified() -> None:
    adapter = _adapter(failure_mode=FixtureAdapterFailureMode.TIMEOUT)

    await adapter.connect()
    with pytest.raises(AdapterTimeoutError) as exc_info:
        await adapter.list_markets(_market_list_request())

    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_adapter_contract_malformed_payload_is_classified() -> None:
    adapter = _adapter(failure_mode=FixtureAdapterFailureMode.MALFORMED_PAYLOAD)

    await adapter.connect()
    with pytest.raises(AdapterProtocolError):
        await adapter.list_markets(_market_list_request())


async def _collect_events(
    events: AsyncIterator[RawExchangeEvent],
) -> Sequence[RawExchangeEvent]:
    collected: list[RawExchangeEvent] = []
    async for event in events:
        collected.append(event)
    return tuple(collected)
