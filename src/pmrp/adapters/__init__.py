"""Exchange adapter interfaces and shared adapter contracts."""

from pmrp.adapters.base import (
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
