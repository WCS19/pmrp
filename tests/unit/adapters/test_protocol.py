"""Tests for the shared exchange-adapter protocol contract."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from types import NoneType
from typing import get_type_hints

import pytest

from pmrp.adapters import (
    AdapterCapabilities,
    ExchangeAdapter,
    MarketListRequest,
    MarketSubscription,
    RawBalance,
    RawExchangeEvent,
    RawFill,
    RawMarket,
    RawOpenOrder,
    RawPosition,
)
from pmrp.adapters.base.protocol import ExchangeAdapter as BaseExchangeAdapter
from pmrp.schemas.orders import (
    CancelOrderAcknowledgement,
    CancelOrderRequest,
    ExchangeOrderAcknowledgement,
    ExchangeOrderRequest,
)
from pmrp.schemas.system import AdapterHealth


class StructurallyCompleteAdapter:
    @property
    def capabilities(self) -> AdapterCapabilities:
        raise NotImplementedError

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def health(self) -> AdapterHealth:
        raise NotImplementedError

    async def list_markets(self, request: MarketListRequest) -> Sequence[RawMarket]:
        raise NotImplementedError

    async def subscribe_market_data(
        self,
        subscriptions: Sequence[MarketSubscription],
    ) -> AsyncIterator[RawExchangeEvent]:
        if False:
            yield RawExchangeEvent.model_validate({})

    async def place_order(
        self,
        request: ExchangeOrderRequest,
    ) -> ExchangeOrderAcknowledgement:
        raise NotImplementedError

    async def cancel_order(
        self,
        request: CancelOrderRequest,
    ) -> CancelOrderAcknowledgement:
        raise NotImplementedError

    async def get_open_orders(self) -> Sequence[RawOpenOrder]:
        return ()

    async def get_positions(self) -> Sequence[RawPosition]:
        return ()

    async def get_balances(self) -> Sequence[RawBalance]:
        return ()

    async def get_recent_fills(self) -> Sequence[RawFill]:
        return ()


pytestmark = pytest.mark.unit


def test_exchange_adapter_protocol_is_exported_from_public_adapter_package() -> None:
    assert ExchangeAdapter is BaseExchangeAdapter


def test_exchange_adapter_protocol_supports_runtime_structural_checks() -> None:
    assert isinstance(StructurallyCompleteAdapter(), ExchangeAdapter)
    assert not isinstance(object(), ExchangeAdapter)


def test_exchange_adapter_protocol_includes_required_operations() -> None:
    required_operations = {
        "connect",
        "disconnect",
        "health",
        "list_markets",
        "subscribe_market_data",
        "place_order",
        "cancel_order",
        "get_open_orders",
        "get_positions",
        "get_balances",
        "get_recent_fills",
    }

    assert required_operations <= set(ExchangeAdapter.__dict__)


def test_exchange_adapter_protocol_method_annotations_are_typed() -> None:
    assert get_type_hints(ExchangeAdapter.capabilities.fget)["return"] is AdapterCapabilities
    assert get_type_hints(ExchangeAdapter.connect)["return"] is NoneType
    assert get_type_hints(ExchangeAdapter.disconnect)["return"] is NoneType
    assert get_type_hints(ExchangeAdapter.health)["return"] is AdapterHealth
    assert get_type_hints(ExchangeAdapter.list_markets) == {
        "request": MarketListRequest,
        "return": Sequence[RawMarket],
    }
    assert get_type_hints(ExchangeAdapter.subscribe_market_data) == {
        "subscriptions": Sequence[MarketSubscription],
        "return": AsyncIterator[RawExchangeEvent],
    }
    assert get_type_hints(ExchangeAdapter.place_order) == {
        "request": ExchangeOrderRequest,
        "return": ExchangeOrderAcknowledgement,
    }
    assert get_type_hints(ExchangeAdapter.cancel_order) == {
        "request": CancelOrderRequest,
        "return": CancelOrderAcknowledgement,
    }
    assert get_type_hints(ExchangeAdapter.get_open_orders)["return"] == Sequence[RawOpenOrder]
    assert get_type_hints(ExchangeAdapter.get_positions)["return"] == Sequence[RawPosition]
    assert get_type_hints(ExchangeAdapter.get_balances)["return"] == Sequence[RawBalance]
    assert get_type_hints(ExchangeAdapter.get_recent_fills)["return"] == Sequence[RawFill]
