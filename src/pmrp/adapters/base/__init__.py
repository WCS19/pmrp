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
]
