"""Strategy protocol tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pmrp.bus import InProcessEventBus
from pmrp.clock import FrozenClock
from pmrp.schemas.identifiers import StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.strategy import Signal
from pmrp.strategies import Strategy, StrategyContext

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 27, 15, 0, tzinfo=UTC)


def test_strategy_package_exports_protocol_and_context() -> None:
    import pmrp.strategies as strategies

    assert strategies.Strategy is Strategy
    assert strategies.StrategyContext is StrategyContext


async def test_noop_strategy_satisfies_runtime_protocol() -> None:
    strategy = NoopStrategy()
    context = StrategyContext(
        strategy_id=strategy.strategy_id,
        clock=FrozenClock(NOW),
        event_bus=InProcessEventBus(),
        signal_publisher=RecordingSignalPublisher(),
        order_intent_publisher=RecordingOrderIntentPublisher(),
    )

    assert isinstance(strategy, Strategy)

    await strategy.initialize(context)
    await strategy.on_event({"event": "demo"})
    await strategy.shutdown("test_complete")

    assert strategy.initialized_context is context
    assert strategy.events == [{"event": "demo"}]
    assert strategy.shutdown_reason == "test_complete"


def test_strategy_protocol_declares_registration_metadata() -> None:
    strategy = NoopStrategy()

    assert strategy.strategy_id == StrategyId("strat_noop_protocol_v1")
    assert strategy.strategy_type == "noop"
    assert strategy.strategy_version == "1.0.0"
    assert strategy.configuration_schema_version == 1
    assert strategy.subscribed_event_types == ("market.snapshot",)


def test_strategy_package_does_not_import_forbidden_boundaries() -> None:
    strategy_root = Path(__file__).resolve().parents[3] / "src" / "pmrp" / "strategies"
    forbidden_fragments = (
        "pmrp.adapters",
        "pmrp.execution",
        "sqlalchemy",
        "asyncpg",
        "os.environ",
        "datetime.now",
        "time.time",
        "httpx",
        "requests",
    )

    for path in strategy_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            assert fragment not in text, f"{fragment!r} found in {path}"


class NoopStrategy:
    def __init__(self) -> None:
        self.initialized_context: StrategyContext | None = None
        self.events: list[object] = []
        self.shutdown_reason: str | None = None

    @property
    def strategy_id(self) -> StrategyId:
        return StrategyId("strat_noop_protocol_v1")

    @property
    def strategy_type(self) -> str:
        return "noop"

    @property
    def strategy_version(self) -> str:
        return "1.0.0"

    @property
    def configuration_schema_version(self) -> int:
        return 1

    @property
    def subscribed_event_types(self) -> tuple[str, ...]:
        return ("market.snapshot",)

    async def initialize(self, context: StrategyContext) -> None:
        self.initialized_context = context

    async def on_event(self, event: object) -> None:
        self.events.append(event)

    async def shutdown(self, reason: str) -> None:
        self.shutdown_reason = reason


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
