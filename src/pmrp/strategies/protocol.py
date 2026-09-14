"""Strategy structural protocol definitions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pmrp.schemas.identifiers import StrategyId
from pmrp.strategies.context import StrategyContext


@runtime_checkable
class Strategy(Protocol):
    """Contract implemented by isolated PMRP strategy instances."""

    @property
    def strategy_id(self) -> StrategyId:
        """Canonical configured strategy instance identifier."""
        ...

    @property
    def strategy_type(self) -> str:
        """Stable strategy type key used for registration."""
        ...

    @property
    def strategy_version(self) -> str:
        """Version of the strategy implementation."""
        ...

    @property
    def configuration_schema_version(self) -> int:
        """Version of the strategy-specific configuration schema."""
        ...

    @property
    def subscribed_event_types(self) -> tuple[str, ...]:
        """Canonical event type names this strategy consumes."""
        ...

    async def initialize(self, context: StrategyContext) -> None:
        """Initialize the strategy with its approved runtime context."""
        ...

    async def on_event(self, event: object) -> None:
        """Process one canonical event from the strategy's ordered partition."""
        ...

    async def shutdown(self, reason: str) -> None:
        """Release strategy resources during a controlled stop."""
        ...


class StrategyFactory(Protocol):
    """Create strategy instances from validated configuration records."""

    def create(
        self,
        *,
        strategy_id: StrategyId,
        configuration: object,
    ) -> Strategy:
        """Return a strategy instance for an already validated configuration."""
        ...
