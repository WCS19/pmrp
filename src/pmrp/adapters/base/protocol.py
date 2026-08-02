"""Typed exchange-adapter protocol."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from pmrp.adapters.base.capabilities import AdapterCapabilities
from pmrp.adapters.base.requests import MarketListRequest, MarketSubscription
from pmrp.adapters.base.responses import (
    RawBalance,
    RawExchangeEvent,
    RawFill,
    RawMarket,
    RawOpenOrder,
    RawPosition,
)
from pmrp.schemas.orders import (
    CancelOrderAcknowledgement,
    CancelOrderRequest,
    ExchangeOrderAcknowledgement,
    ExchangeOrderRequest,
)
from pmrp.schemas.system import AdapterHealth


@runtime_checkable
class ExchangeAdapter(Protocol):
    """Common asynchronous exchange-adapter interface."""

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Return this adapter's declared exchange capabilities."""

        ...

    async def connect(self) -> None:
        """Connect adapter transports and prepare exchange communication."""

        ...

    async def disconnect(self) -> None:
        """Disconnect adapter transports and release exchange resources."""

        ...

    async def health(self) -> AdapterHealth:
        """Return the adapter's current health snapshot."""

        ...

    async def list_markets(self, request: MarketListRequest) -> Sequence[RawMarket]:
        """Return raw exchange market listings for the supplied request."""

        ...

    def subscribe_market_data(
        self,
        subscriptions: Sequence[MarketSubscription],
    ) -> AsyncIterator[RawExchangeEvent]:
        """Stream raw market-data events for the supplied subscriptions."""

        ...

    async def place_order(
        self,
        request: ExchangeOrderRequest,
    ) -> ExchangeOrderAcknowledgement:
        """Submit an already approved canonical exchange order request."""

        ...

    async def cancel_order(
        self,
        request: CancelOrderRequest,
    ) -> CancelOrderAcknowledgement:
        """Submit a canonical exchange cancel request."""

        ...

    async def get_open_orders(self) -> Sequence[RawOpenOrder]:
        """Return raw open-order state from the exchange."""

        ...

    async def get_positions(self) -> Sequence[RawPosition]:
        """Return raw account positions from the exchange."""

        ...

    async def get_balances(self) -> Sequence[RawBalance]:
        """Return raw account balances from the exchange."""

        ...

    async def get_recent_fills(self) -> Sequence[RawFill]:
        """Return recent raw fills from the exchange."""

        ...
