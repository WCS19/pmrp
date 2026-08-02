"""Common exchange-adapter error taxonomy."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import ClassVar


class AdapterEndpointCategory(StrEnum):
    """Stable endpoint categories for safe adapter error context."""

    ACCOUNT = "account"
    AUTHENTICATION = "authentication"
    HEALTH = "health"
    MARKET_DATA = "market_data"
    ORDERS = "orders"
    STREAM = "stream"
    UNKNOWN = "unknown"


class AdapterError(Exception):
    """Base class for exchange-adapter failures with safe structured context."""

    default_retryable: ClassVar[bool] = False
    requires_reconciliation: ClassVar[bool] = False

    def __init__(
        self,
        safe_message: str,
        *,
        exchange: str | None = None,
        endpoint_category: AdapterEndpointCategory | str | None = None,
        http_status: int | None = None,
        exchange_error_code: str | None = None,
        request_id: str | None = None,
        safe_response_excerpt: str | None = None,
        retryable: bool | None = None,
        context: Mapping[str, str] | None = None,
    ) -> None:
        self.safe_message = _validate_required_text(safe_message, field_name="safe_message")
        self.retryable = self.default_retryable if retryable is None else retryable
        self.exchange = _validate_optional_text(exchange, field_name="exchange")
        self.endpoint_category = _normalize_endpoint_category(endpoint_category)
        self.http_status = _validate_http_status(http_status)
        self.exchange_error_code = _validate_optional_text(
            exchange_error_code,
            field_name="exchange_error_code",
        )
        self.request_id = _validate_optional_text(request_id, field_name="request_id")
        self.safe_response_excerpt = safe_response_excerpt
        self.context: Mapping[str, str] = MappingProxyType(
            _build_context(
                exchange=self.exchange,
                endpoint_category=self.endpoint_category,
                http_status=self.http_status,
                exchange_error_code=self.exchange_error_code,
                request_id=self.request_id,
                safe_response_excerpt=self.safe_response_excerpt,
                retryable=self.retryable,
                requires_reconciliation=self.requires_reconciliation,
                context=context,
            )
        )
        super().__init__(self.safe_message)


class AdapterAuthenticationError(AdapterError):
    """Authentication failed and must not be retried blindly."""


class AdapterRateLimitError(AdapterError):
    """The exchange rate limit was reached."""

    default_retryable: ClassVar[bool] = True


class AdapterTransportError(AdapterError):
    """A transient network or transport operation failed."""

    default_retryable: ClassVar[bool] = True


class AdapterTimeoutError(AdapterTransportError):
    """An exchange request or stream operation exceeded its explicit timeout."""


class AdapterProtocolError(AdapterError):
    """An exchange response or stream message violated the expected protocol."""


class AdapterSequenceGapError(AdapterProtocolError):
    """An exchange stream sequence gap was detected."""


class AdapterCapabilityError(AdapterError):
    """The requested operation is unsupported by the adapter capabilities."""


class AdapterAmbiguousOrderSubmissionError(AdapterError):
    """An order submission may have reached the exchange but lacks final status."""

    requires_reconciliation: ClassVar[bool] = True


def _build_context(
    *,
    exchange: str | None,
    endpoint_category: str | None,
    http_status: int | None,
    exchange_error_code: str | None,
    request_id: str | None,
    safe_response_excerpt: str | None,
    retryable: bool,
    requires_reconciliation: bool,
    context: Mapping[str, str] | None,
) -> dict[str, str]:
    safe_context = dict(context or {})
    safe_context["retryable"] = str(retryable).lower()
    if requires_reconciliation:
        safe_context["requires_reconciliation"] = "true"
    if exchange is not None:
        safe_context["exchange"] = exchange
    if endpoint_category is not None:
        safe_context["endpoint_category"] = endpoint_category
    if http_status is not None:
        safe_context["http_status"] = str(http_status)
    if exchange_error_code is not None:
        safe_context["exchange_error_code"] = exchange_error_code
    if request_id is not None:
        safe_context["request_id"] = request_id
    if safe_response_excerpt is not None:
        safe_context["safe_response_excerpt"] = safe_response_excerpt
    return safe_context


def _normalize_endpoint_category(
    endpoint_category: AdapterEndpointCategory | str | None,
) -> str | None:
    if isinstance(endpoint_category, AdapterEndpointCategory):
        return endpoint_category.value
    return _validate_optional_text(endpoint_category, field_name="endpoint_category")


def _validate_http_status(http_status: int | None) -> int | None:
    if http_status is None:
        return None
    if not 100 <= http_status <= 599:
        msg = "http_status must be between 100 and 599"
        raise ValueError(msg)
    return http_status


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_required_text(value, field_name=field_name)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
