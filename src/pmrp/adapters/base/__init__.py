"""Shared base contracts for exchange adapters."""

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
    "AdapterCapabilityError",
    "AdapterEndpointCategory",
    "AdapterError",
    "AdapterProtocolError",
    "AdapterRateLimitError",
    "AdapterSequenceGapError",
    "AdapterTimeoutError",
    "AdapterTransportError",
]
