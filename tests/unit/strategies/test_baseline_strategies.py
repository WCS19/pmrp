"""Baseline strategy behavior tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.bus import InProcessEventBus
from pmrp.clock import FrozenClock
from pmrp.schemas.events import (
    MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,
    EventEnvelope,
    OrderBookSnapshotEvent,
)
from pmrp.schemas.identifiers import StrategyId
from pmrp.schemas.market_data import OrderBookSnapshot
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.strategy import Signal, SignalDirection
from pmrp.strategies import (
    MIDPOINT_OBSERVER_CONFIGURATION_SCHEMA_VERSION,
    MIDPOINT_OBSERVER_STRATEGY_TYPE,
    MIDPOINT_OBSERVER_STRATEGY_VERSION,
    THRESHOLD_SIGNAL_CONFIGURATION_SCHEMA_VERSION,
    THRESHOLD_SIGNAL_STRATEGY_TYPE,
    THRESHOLD_SIGNAL_STRATEGY_VERSION,
    MidpointObserverConfiguration,
    MidpointObserverFactory,
    MidpointObserverStrategy,
    Strategy,
    StrategyContext,
    StrategyContextError,
    StrategyRuntime,
    ThresholdSignalConfiguration,
    ThresholdSignalFactory,
    ThresholdSignalStrategy,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 29, 15, 0, tzinfo=UTC)


async def test_midpoint_observer_calculates_midpoint_and_emits_metrics_only() -> None:
    metrics = RecordingMetrics()
    signal_publisher = RecordingSignalPublisher()
    order_intents = RecordingOrderIntentPublisher()
    strategy = MidpointObserverStrategy(
        strategy_id=StrategyId("strat_midpoint_observer_test"),
        configuration=MidpointObserverConfiguration(),
    )
    context = _context(
        strategy.strategy_id,
        services={"metrics": metrics},
        signal_publisher=signal_publisher,
        order_intent_publisher=order_intents,
    )

    await strategy.initialize(context)
    await strategy.on_event(_snapshot_event(best_bid="0.41", best_ask="0.43"))

    assert isinstance(strategy, Strategy)
    assert strategy.strategy_type == MIDPOINT_OBSERVER_STRATEGY_TYPE
    assert strategy.strategy_version == MIDPOINT_OBSERVER_STRATEGY_VERSION
    assert strategy.configuration_schema_version == MIDPOINT_OBSERVER_CONFIGURATION_SCHEMA_VERSION
    assert strategy.subscribed_event_types == (MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,)
    assert len(strategy.observations) == 1
    observation = strategy.observations[0]
    assert observation.best_bid == Decimal("0.41")
    assert observation.best_ask == Decimal("0.43")
    assert observation.midpoint == Decimal("0.42")
    assert observation.spread == Decimal("0.02")
    assert signal_publisher.signals == []
    assert order_intents.intents == []
    expected_tags = {
        "strategy_id": "strat_midpoint_observer_test",
        "market_id": "mkt_midpoint_observer_test",
        "contract_id": "ctr_midpoint_observer_test",
        "exchange": "kalshi",
    }
    assert metrics.increments == [("strategy.midpoint_observer.snapshot_observed", expected_tags)]
    assert ("strategy.midpoint_observer.best_bid", Decimal("0.41"), expected_tags) in metrics.gauges
    assert ("strategy.midpoint_observer.best_ask", Decimal("0.43"), expected_tags) in metrics.gauges
    assert ("strategy.midpoint_observer.midpoint", Decimal("0.42"), expected_tags) in metrics.gauges
    assert ("strategy.midpoint_observer.spread", Decimal("0.02"), expected_tags) in metrics.gauges


async def test_midpoint_observer_filters_market_and_skips_invalid_snapshots() -> None:
    metrics = RecordingMetrics()
    strategy = MidpointObserverStrategy(
        strategy_id=StrategyId("strat_midpoint_observer_filter"),
        configuration=MidpointObserverConfiguration(market_id="mkt_midpoint_observer_test"),
    )
    await strategy.initialize(_context(strategy.strategy_id, services={"metrics": metrics}))

    await strategy.on_event(_snapshot_event(market_id="mkt_other_midpoint_observer"))
    await strategy.on_event(_snapshot_event(is_valid=False))

    assert strategy.observations == ()
    assert metrics.increments == [
        (
            "strategy.midpoint_observer.snapshot_skipped",
            {
                "strategy_id": "strat_midpoint_observer_filter",
                "market_id": "mkt_midpoint_observer_test",
                "contract_id": "ctr_midpoint_observer_test",
                "exchange": "kalshi",
            },
        )
    ]
    assert metrics.gauges == []


async def test_midpoint_observer_requires_metrics_service() -> None:
    strategy = MidpointObserverStrategy(
        strategy_id=StrategyId("strat_midpoint_observer_metrics"),
        configuration=MidpointObserverConfiguration(),
    )

    with pytest.raises(StrategyContextError) as missing_error:
        await strategy.initialize(_context(strategy.strategy_id))

    assert missing_error.value.reason_code == "midpoint_observer_metrics_missing"

    with pytest.raises(StrategyContextError) as invalid_error:
        await strategy.initialize(_context(strategy.strategy_id, services={"metrics": object()}))

    assert invalid_error.value.reason_code == "midpoint_observer_metrics_invalid"


async def test_midpoint_observer_runs_under_strategy_runtime() -> None:
    event_bus = InProcessEventBus(deterministic=True)
    metrics = RecordingMetrics()
    strategy = MidpointObserverStrategy(
        strategy_id=StrategyId("strat_midpoint_observer_runtime"),
        configuration=MidpointObserverConfiguration(),
    )
    runtime = StrategyRuntime(clock=FrozenClock(NOW))
    runtime.register(
        strategy,
        _context(
            strategy.strategy_id,
            event_bus=event_bus,
            services={"metrics": metrics},
        ),
    )

    await runtime.start()
    await event_bus.publish(_snapshot_event(best_bid="0.40", best_ask="0.46"))
    await _wait_until(lambda: len(strategy.observations) == 1)
    await runtime.stop("test_complete")

    assert strategy.observations[0].midpoint == Decimal("0.43")
    assert strategy.shutdown_reason == "test_complete"


def test_midpoint_observer_factory_requires_typed_configuration() -> None:
    factory = MidpointObserverFactory()
    strategy = factory.create(
        strategy_id=StrategyId("strat_midpoint_observer_factory"),
        configuration=MidpointObserverConfiguration(metric_prefix="custom.midpoint"),
    )

    assert strategy.strategy_id == "strat_midpoint_observer_factory"

    with pytest.raises(TypeError, match="MidpointObserverConfiguration"):
        factory.create(
            strategy_id=StrategyId("strat_midpoint_observer_bad_factory"),
            configuration=object(),
        )


async def test_threshold_signal_strategy_emits_buy_signal_and_no_order_intent() -> None:
    signal_publisher = RecordingSignalPublisher()
    order_intents = RecordingOrderIntentPublisher()
    strategy = ThresholdSignalStrategy(
        strategy_id=StrategyId("strat_threshold_signal_test"),
        configuration=ThresholdSignalConfiguration(
            threshold_probability="0.45",
            confidence="0.80",
        ),
    )
    context = _context(
        strategy.strategy_id,
        signal_publisher=signal_publisher,
        order_intent_publisher=order_intents,
    )

    await strategy.initialize(context)
    await strategy.on_event(_snapshot_event(best_bid="0.39", best_ask="0.42"))

    assert isinstance(strategy, Strategy)
    assert strategy.strategy_type == THRESHOLD_SIGNAL_STRATEGY_TYPE
    assert strategy.strategy_version == THRESHOLD_SIGNAL_STRATEGY_VERSION
    assert strategy.configuration_schema_version == THRESHOLD_SIGNAL_CONFIGURATION_SCHEMA_VERSION
    assert strategy.subscribed_event_types == (MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,)
    assert len(strategy.decisions) == 1
    decision = strategy.decisions[0]
    signal = decision.signal
    assert strategy.generated_signals == (signal,)
    assert signal_publisher.signals == [signal]
    assert order_intents.intents == []
    assert decision.best_ask == Decimal("0.42")
    assert decision.threshold_probability == Decimal("0.45")
    assert signal.signal_id.startswith("sig_threshold_")
    assert signal.strategy_id == "strat_threshold_signal_test"
    assert signal.market_id == "mkt_midpoint_observer_test"
    assert signal.contract_id == "ctr_midpoint_observer_test"
    assert signal.signal_type == "threshold_probability"
    assert signal.direction is SignalDirection.BUY
    assert signal.strength == Decimal("0.03")
    assert signal.fair_probability == Decimal("0.45")
    assert signal.confidence == Decimal("0.80")
    assert signal.valid_from == NOW
    assert signal.valid_until is None
    assert signal.reason_code == "BEST_ASK_BELOW_THRESHOLD"
    assert signal.correlation_id == "corr_midpoint_observer_test"


async def test_threshold_signal_strategy_filters_and_skips_non_actionable_snapshots() -> None:
    signal_publisher = RecordingSignalPublisher()
    strategy = ThresholdSignalStrategy(
        strategy_id=StrategyId("strat_threshold_signal_filter"),
        configuration=ThresholdSignalConfiguration(
            market_id="mkt_midpoint_observer_test",
            threshold_probability="0.45",
        ),
    )
    await strategy.initialize(_context(strategy.strategy_id, signal_publisher=signal_publisher))

    await strategy.on_event(_snapshot_event(market_id="mkt_other_threshold_signal"))
    await strategy.on_event(_snapshot_event(best_ask="0.45"))
    await strategy.on_event(_snapshot_event(best_ask="0.46"))
    await strategy.on_event(_snapshot_event(is_valid=False))
    await strategy.on_event(_snapshot_event(asks=()))

    assert strategy.decisions == ()
    assert signal_publisher.signals == []


async def test_threshold_signal_strategy_requires_initialization() -> None:
    strategy = ThresholdSignalStrategy(
        strategy_id=StrategyId("strat_threshold_signal_uninitialized"),
        configuration=ThresholdSignalConfiguration(threshold_probability="0.45"),
    )

    with pytest.raises(StrategyContextError) as exc_info:
        await strategy.on_event(_snapshot_event(best_ask="0.42"))

    assert exc_info.value.reason_code == "threshold_signal_not_initialized"


async def test_threshold_signal_strategy_runs_under_strategy_runtime() -> None:
    event_bus = InProcessEventBus(deterministic=True)
    signal_publisher = RecordingSignalPublisher()
    order_intents = RecordingOrderIntentPublisher()
    strategy = ThresholdSignalStrategy(
        strategy_id=StrategyId("strat_threshold_signal_runtime"),
        configuration=ThresholdSignalConfiguration(threshold_probability="0.45"),
    )
    runtime = StrategyRuntime(clock=FrozenClock(NOW))
    runtime.register(
        strategy,
        _context(
            strategy.strategy_id,
            event_bus=event_bus,
            signal_publisher=signal_publisher,
            order_intent_publisher=order_intents,
        ),
    )

    await runtime.start()
    await event_bus.publish(_snapshot_event(best_bid="0.40", best_ask="0.44"))
    await _wait_until(lambda: len(signal_publisher.signals) == 1)
    await runtime.stop("test_complete")

    assert strategy.generated_signals == (signal_publisher.signals[0],)
    assert signal_publisher.signals[0].strength == Decimal("0.01")
    assert order_intents.intents == []
    assert strategy.shutdown_reason == "test_complete"


def test_threshold_signal_configuration_rejects_invalid_probability_inputs() -> None:
    with pytest.raises(TypeError, match="float input"):
        ThresholdSignalConfiguration(threshold_probability=0.45)

    with pytest.raises(ValidationError, match="less than or equal to 1"):
        ThresholdSignalConfiguration(threshold_probability="1.01")

    with pytest.raises(TypeError, match="float input"):
        ThresholdSignalConfiguration(threshold_probability="0.45", confidence=1.0)


def test_threshold_signal_factory_requires_typed_configuration() -> None:
    factory = ThresholdSignalFactory()
    strategy = factory.create(
        strategy_id=StrategyId("strat_threshold_signal_factory"),
        configuration=ThresholdSignalConfiguration(
            threshold_probability="0.45",
            signal_type="custom_threshold",
        ),
    )

    assert strategy.strategy_id == "strat_threshold_signal_factory"

    with pytest.raises(TypeError, match="ThresholdSignalConfiguration"):
        factory.create(
            strategy_id=StrategyId("strat_threshold_signal_bad_factory"),
            configuration=object(),
        )


class RecordingMetrics:
    def __init__(self) -> None:
        self.increments: list[tuple[str, dict[str, str] | None]] = []
        self.gauges: list[tuple[str, int | Decimal, dict[str, str] | None]] = []

    def increment(self, name: str, *, tags: dict[str, str] | None = None) -> None:
        self.increments.append((name, tags))

    def gauge(self, name: str, value: int | Decimal, *, tags: dict[str, str] | None = None) -> None:
        self.gauges.append((name, value, tags))


class RecordingSignalPublisher:
    def __init__(self) -> None:
        self.signals: list[Signal] = []

    async def publish_signal(self, signal: Signal) -> None:
        self.signals.append(signal)


class RecordingOrderIntentPublisher:
    def __init__(self) -> None:
        self.intents: list[OrderIntent] = []

    async def publish_order_intent(self, intent: OrderIntent) -> None:
        self.intents.append(intent)


def _context(
    strategy_id: StrategyId,
    *,
    event_bus: InProcessEventBus | None = None,
    services: dict[str, object] | None = None,
    signal_publisher: RecordingSignalPublisher | None = None,
    order_intent_publisher: RecordingOrderIntentPublisher | None = None,
) -> StrategyContext:
    return StrategyContext(
        strategy_id=strategy_id,
        clock=FrozenClock(NOW),
        event_bus=event_bus or InProcessEventBus(),
        signal_publisher=signal_publisher or RecordingSignalPublisher(),
        order_intent_publisher=order_intent_publisher or RecordingOrderIntentPublisher(),
        services=services,
    )


def _snapshot_event(
    *,
    market_id: str = "mkt_midpoint_observer_test",
    best_bid: str = "0.41",
    best_ask: str = "0.43",
    asks: tuple[dict[str, object], ...] | None = None,
    is_valid: bool = True,
) -> OrderBookSnapshotEvent:
    return OrderBookSnapshotEvent(
        envelope=EventEnvelope(
            event_id="evt_midpoint_observer_test",
            event_type=MARKET_ORDER_BOOK_SNAPSHOT_EVENT_TYPE,
            schema_version=1,
            occurred_at=NOW,
            received_at=NOW,
            published_at=NOW,
            producer="unit_test",
            exchange="kalshi",
            market_id=market_id,
            correlation_id="corr_midpoint_observer_test",
        ),
        snapshot=OrderBookSnapshot.model_validate(
            {
                "market_id": market_id,
                "contract_id": "ctr_midpoint_observer_test",
                "exchange": "kalshi",
                "sequence": 1,
                "exchange_occurred_at": NOW,
                "received_at": NOW,
                "bids": ({"price": best_bid, "quantity": "10", "order_count": 1},),
                "asks": asks
                if asks is not None
                else ({"price": best_ask, "quantity": "10", "order_count": 1},),
                "is_valid": is_valid,
                "snapshot_reason": "baseline_test",
            }
        ),
    )


async def _wait_until(predicate: Callable[[], bool]) -> None:
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not met")
