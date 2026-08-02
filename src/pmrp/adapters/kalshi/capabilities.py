"""Kalshi adapter capability declaration."""

from __future__ import annotations

from pmrp.adapters.base import AdapterCapabilities
from pmrp.schemas.enums import OrderType, TimeInForce

KALSHI_EXCHANGE = "kalshi"

KALSHI_CAPABILITIES = AdapterCapabilities(
    exchange=KALSHI_EXCHANGE,
    supported_order_types=(OrderType.LIMIT, OrderType.MARKET),
    supported_time_in_force=(TimeInForce.GTC, TimeInForce.IOC),
    supports_post_only=True,
    supports_replace_order=False,
    supports_client_order_id=True,
    supports_streaming_order_updates=False,
    supports_streaming_market_data=True,
    supports_historical_data=True,
    supports_sequence_numbers=True,
    supports_batch_endpoints=False,
    supports_self_trade_controls=False,
    max_batch_size=None,
)


def kalshi_capabilities() -> AdapterCapabilities:
    """Return Kalshi's immutable adapter capability declaration."""

    return KALSHI_CAPABILITIES
