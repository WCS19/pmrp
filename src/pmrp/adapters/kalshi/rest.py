"""Kalshi REST market-data client contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, NoReturn, Protocol
from urllib.parse import urlencode

from pydantic import Field, field_serializer, field_validator

from pmrp.adapters.base.errors import (
    AdapterAuthenticationError,
    AdapterEndpointCategory,
    AdapterProtocolError,
    AdapterRateLimitError,
    AdapterTransportError,
)
from pmrp.adapters.kalshi.raw_models import (
    KalshiMarketListResponse,
    KalshiRawErrorResponse,
    parse_kalshi_error_json,
    parse_kalshi_market_list_json,
)
from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.immutability import freeze_string_mapping, thaw_string_mapping

KALSHI_MARKETS_PATH = "/trade-api/v2/markets"
KALSHI_DEFAULT_REST_TIMEOUT_SECONDS = 10

_KALSHI_REST_TEXT_MAX_LENGTH = 4096
_KALSHI_REST_TIMEOUT_MAX_SECONDS = 120


class KalshiRestRequest(CanonicalModel):
    """One Kalshi REST request after adapter-specific translation."""

    method: Literal["GET"]
    path: str = Field(min_length=1, max_length=512)
    query: Mapping[str, str] = Field(default_factory=dict)
    headers: Mapping[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(gt=0, le=_KALSHI_REST_TIMEOUT_MAX_SECONDS)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = _validate_required_text(value, field_name="Kalshi REST path")
        if not value.startswith("/"):
            msg = "Kalshi REST path must start with /"
            raise ValueError(msg)
        return value

    @field_validator("query", "headers")
    @classmethod
    def validate_string_mapping(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        try:
            return freeze_string_mapping(value, field_name="Kalshi REST string mapping")
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_serializer("query", "headers")
    def serialize_string_mapping(self, value: Mapping[str, str]) -> dict[str, str]:
        return thaw_string_mapping(value)

    @property
    def target(self) -> str:
        """Return the deterministic path and query component sent to transport."""

        if not self.query:
            return self.path
        return f"{self.path}?{urlencode(sorted(self.query.items()))}"


class KalshiRestResponse(CanonicalModel):
    """One Kalshi REST response returned by an injected transport."""

    status_code: int = Field(ge=100, le=599)
    body_text: str = Field(min_length=1)
    headers: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        try:
            return freeze_string_mapping(value, field_name="Kalshi REST response headers")
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_serializer("headers")
    def serialize_headers(self, value: Mapping[str, str]) -> dict[str, str]:
        return thaw_string_mapping(value)


class KalshiMarketListParams(CanonicalModel):
    """Supported Kalshi market-list query parameters."""

    limit: int | None = Field(default=None, gt=0, le=1000)
    cursor: str | None = Field(default=None, min_length=1, max_length=512)
    status: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("cursor", "status")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Kalshi market-list query parameter")

    def to_query(self) -> Mapping[str, str]:
        query: dict[str, str] = {}
        if self.limit is not None:
            query["limit"] = str(self.limit)
        if self.cursor is not None:
            query["cursor"] = self.cursor
        if self.status is not None:
            query["status"] = self.status
        return query


class KalshiRestTransport(Protocol):
    """Async transport boundary used by the Kalshi REST client."""

    async def send(self, request: KalshiRestRequest) -> KalshiRestResponse:
        """Send one translated Kalshi REST request."""

        ...


class KalshiMarketDataRestClient:
    """Kalshi market-data REST client using an injected transport."""

    def __init__(
        self,
        *,
        transport: KalshiRestTransport,
        default_timeout_seconds: int = KALSHI_DEFAULT_REST_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = transport
        self._default_timeout_seconds = _validate_timeout_seconds(default_timeout_seconds)

    async def list_markets(
        self,
        params: KalshiMarketListParams | None = None,
    ) -> KalshiMarketListResponse:
        """Fetch and parse a Kalshi market-list response."""

        actual_params = params if params is not None else KalshiMarketListParams()
        request = KalshiRestRequest(
            method="GET",
            path=KALSHI_MARKETS_PATH,
            query=actual_params.to_query(),
            headers={},
            timeout_seconds=self._default_timeout_seconds,
        )
        response = await self._transport.send(request)
        if response.status_code == 200:
            return _parse_market_list_success(response, request=request)
        _raise_rest_error(response, request=request)


def _parse_market_list_success(
    response: KalshiRestResponse,
    *,
    request: KalshiRestRequest,
) -> KalshiMarketListResponse:
    try:
        return parse_kalshi_market_list_json(response.body_text)
    except ValueError as exc:
        raise AdapterProtocolError(
            "Kalshi market-list response payload is malformed",
            exchange="kalshi",
            endpoint_category=AdapterEndpointCategory.MARKET_DATA,
            http_status=response.status_code,
            context={"endpoint": request.path},
        ) from exc


def _raise_rest_error(response: KalshiRestResponse, *, request: KalshiRestRequest) -> NoReturn:
    raw_error = _parse_error_response(response)
    http_status = (
        raw_error.http_status if raw_error.http_status is not None else response.status_code
    )
    error_code = raw_error.error_code
    context = _error_context(request=request, raw_error=raw_error)

    if http_status in (401, 403):
        raise AdapterAuthenticationError(
            "Kalshi REST authentication failed",
            exchange="kalshi",
            endpoint_category=AdapterEndpointCategory.MARKET_DATA,
            http_status=http_status,
            exchange_error_code=error_code,
            request_id=raw_error.request_id,
            context=context,
        )
    if http_status == 429:
        raise AdapterRateLimitError(
            "Kalshi REST rate limit exceeded",
            exchange="kalshi",
            endpoint_category=AdapterEndpointCategory.MARKET_DATA,
            http_status=http_status,
            exchange_error_code=error_code,
            request_id=raw_error.request_id,
            context=context,
        )
    if http_status >= 500:
        raise AdapterTransportError(
            "Kalshi REST service error",
            exchange="kalshi",
            endpoint_category=AdapterEndpointCategory.MARKET_DATA,
            http_status=http_status,
            exchange_error_code=error_code,
            request_id=raw_error.request_id,
            context=context,
        )
    raise AdapterProtocolError(
        "Kalshi REST request failed",
        exchange="kalshi",
        endpoint_category=AdapterEndpointCategory.MARKET_DATA,
        http_status=http_status,
        exchange_error_code=error_code,
        request_id=raw_error.request_id,
        context=context,
    )


def _parse_error_response(response: KalshiRestResponse) -> KalshiRawErrorResponse:
    try:
        return parse_kalshi_error_json(response.body_text)
    except ValueError:
        return KalshiRawErrorResponse.from_exchange_payload(
            {
                "http_status": response.status_code,
                "error": {
                    "code": "unparseable_error_payload",
                    "message": "Kalshi error response was not valid JSON",
                },
            }
        )


def _error_context(
    *,
    request: KalshiRestRequest,
    raw_error: KalshiRawErrorResponse,
) -> dict[str, str]:
    context = {"endpoint": request.path}
    if raw_error.retry_after_seconds is not None:
        context["retry_after_seconds"] = str(raw_error.retry_after_seconds)
    return context


def _validate_timeout_seconds(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = "Kalshi REST timeout_seconds must be an integer"
        raise TypeError(msg)
    if value <= 0:
        msg = "Kalshi REST timeout_seconds must be positive"
        raise ValueError(msg)
    if value > _KALSHI_REST_TIMEOUT_MAX_SECONDS:
        msg = f"Kalshi REST timeout_seconds must be at most {_KALSHI_REST_TIMEOUT_MAX_SECONDS}"
        raise ValueError(msg)
    return value


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_required_text(value, field_name=field_name)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    if len(value) > _KALSHI_REST_TEXT_MAX_LENGTH:
        msg = f"{field_name} must be at most {_KALSHI_REST_TEXT_MAX_LENGTH} characters"
        raise ValueError(msg)
    return value
