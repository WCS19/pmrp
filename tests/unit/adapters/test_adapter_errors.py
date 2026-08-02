"""Tests for shared adapter error contracts."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from pmrp.adapters import (
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


@pytest.mark.unit
def test_adapter_error_records_safe_message_and_context() -> None:
    source_context = {"correlation_id": "corr_01j00000000000000000000001"}

    error = AdapterError(
        "exchange request failed",
        exchange="kalshi",
        endpoint_category=AdapterEndpointCategory.MARKET_DATA,
        http_status=503,
        exchange_error_code="service_unavailable",
        request_id="req_01j00000000000000000000001",
        safe_response_excerpt="upstream temporarily unavailable",
        retryable=True,
        context=source_context,
    )
    source_context["correlation_id"] = "changed"

    assert str(error) == "exchange request failed"
    assert error.safe_message == "exchange request failed"
    assert error.retryable is True
    assert error.context == {
        "correlation_id": "corr_01j00000000000000000000001",
        "retryable": "true",
        "exchange": "kalshi",
        "endpoint_category": "market_data",
        "http_status": "503",
        "exchange_error_code": "service_unavailable",
        "request_id": "req_01j00000000000000000000001",
        "safe_response_excerpt": "upstream temporarily unavailable",
    }
    assert isinstance(error.context, MappingProxyType)


@pytest.mark.unit
def test_adapter_error_context_is_immutable() -> None:
    error = AdapterError("exchange request failed", context={"component": "adapter"})

    with pytest.raises(TypeError):
        error.context["component"] = "changed"


@pytest.mark.unit
def test_adapter_error_string_does_not_include_context_values() -> None:
    error = AdapterError(
        "exchange request failed",
        context={"safe_detail": "redacted-detail"},
    )

    assert "redacted-detail" not in str(error)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("error_type", "expected_retryable"),
    [
        (AdapterAuthenticationError, False),
        (AdapterRateLimitError, True),
        (AdapterTransportError, True),
        (AdapterTimeoutError, True),
        (AdapterProtocolError, False),
        (AdapterSequenceGapError, False),
        (AdapterCapabilityError, False),
        (AdapterAmbiguousOrderSubmissionError, False),
    ],
)
def test_adapter_error_subclasses_have_expected_retry_classification(
    error_type: type[AdapterError],
    expected_retryable: bool,
) -> None:
    error = error_type("classified adapter failure")

    assert isinstance(error, AdapterError)
    assert error.retryable is expected_retryable
    assert error.context["retryable"] == str(expected_retryable).lower()


@pytest.mark.unit
def test_timeout_error_is_transport_error() -> None:
    error = AdapterTimeoutError("request timed out")

    assert isinstance(error, AdapterTransportError)


@pytest.mark.unit
def test_sequence_gap_error_is_protocol_error() -> None:
    error = AdapterSequenceGapError("sequence gap detected")

    assert isinstance(error, AdapterProtocolError)


@pytest.mark.unit
def test_ambiguous_order_submission_requires_reconciliation() -> None:
    error = AdapterAmbiguousOrderSubmissionError(
        "order submission status is ambiguous",
        endpoint_category=AdapterEndpointCategory.ORDERS,
    )

    assert error.retryable is False
    assert error.requires_reconciliation is True
    assert error.context["requires_reconciliation"] == "true"
    assert error.context["endpoint_category"] == "orders"


@pytest.mark.unit
def test_retry_classification_can_be_overridden_for_specific_exchange_case() -> None:
    error = AdapterProtocolError("recoverable stream protocol issue", retryable=True)

    assert error.retryable is True
    assert error.context["retryable"] == "true"


@pytest.mark.unit
def test_adapter_error_rejects_blank_safe_message() -> None:
    with pytest.raises(ValueError, match="safe_message"):
        AdapterError(" failed ")


@pytest.mark.unit
def test_adapter_error_rejects_invalid_http_status() -> None:
    with pytest.raises(ValueError, match="http_status"):
        AdapterError("exchange request failed", http_status=99)


@pytest.mark.unit
def test_endpoint_category_accepts_exchange_specific_string() -> None:
    error = AdapterError(
        "exchange request failed",
        endpoint_category="portfolio_margin",
    )

    assert error.context["endpoint_category"] == "portfolio_margin"
