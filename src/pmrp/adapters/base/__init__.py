"""Shared base contracts for exchange adapters."""

from pmrp.adapters.base.capabilities import AdapterCapabilities
from pmrp.adapters.base.errors import (
    AdapterAmbiguousOrderSubmissionError,
    AdapterAuthenticationError,
    AdapterCapabilityError,
    AdapterEndpointCategory,
    AdapterError,
    AdapterProtocolError,
    AdapterRateLimitError,
    AdapterSequenceGapError,
    AdapterTimeoutError,
    AdapterTransportError,
)
from pmrp.adapters.base.requests import MarketDataChannel, MarketListRequest, MarketSubscription
from pmrp.adapters.base.responses import (
    RawBalance,
    RawExchangeEvent,
    RawFill,
    RawMarket,
    RawOpenOrder,
    RawPosition,
)

__all__ = [
    "AdapterAmbiguousOrderSubmissionError",
    "AdapterAuthenticationError",
    "AdapterCapabilities",
    "AdapterCapabilityError",
    "AdapterEndpointCategory",
    "AdapterError",
    "AdapterProtocolError",
    "AdapterRateLimitError",
    "AdapterSequenceGapError",
    "AdapterTimeoutError",
    "AdapterTransportError",
    "MarketDataChannel",
    "MarketListRequest",
    "MarketSubscription",
    "RawBalance",
    "RawExchangeEvent",
    "RawFill",
    "RawMarket",
    "RawOpenOrder",
    "RawPosition",
]
