"""Risk rule protocol definitions."""

from __future__ import annotations

from typing import Protocol

from pmrp.risk.context import RiskContext
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskRuleResult


class RiskRule(Protocol):
    """Small deterministic risk rule interface."""

    @property
    def rule_id(self) -> str:
        """Return the stable risk rule identifier."""
        ...

    @property
    def version(self) -> str:
        """Return the stable risk rule version."""
        ...

    async def evaluate(self, intent: OrderIntent, context: RiskContext) -> RiskRuleResult:
        """Evaluate an order intent against a risk context snapshot."""
        ...
