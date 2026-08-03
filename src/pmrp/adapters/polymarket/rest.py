"""Polymarket Gamma REST market-data client contracts."""

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
from pmrp.adapters.polymarket.raw_models import (
    PolymarketMarketListResponse,
    PolymarketRawErrorResponse,
    parse_polymarket_error_json,
    parse_polymarket_market_list_json,
)
from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.immutability import freeze_string_mapping, thaw_string_mapping

POLYMARKET_MARKETS_KEYSET_PATH = "/markets/keyset"
POLYMARKET_DEFAULT_REST_TIMEOUT_SECONDS = 10

_POLYMARKET_MARKETS_KEYSET_LIMIT_MAX = 100
_POLYMARKET_REST_TEXT_MAX_LENGTH = 4096
_POLYMARKET_REST_TIMEOUT_MAX_SECONDS = 120


class PolymarketRestRequest(CanonicalModel):
    """One Polymarket REST request after adapter-specific translation."""

    method: Literal["GET"]
    path: str = Field(min_length=1, max_length=512)
    query: Mapping[str, str] = Field(default_factory=dict)
    headers: Mapping[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(gt=0, le=_POLYMARKET_REST_TIMEOUT_MAX_SECONDS)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        value = _validate_required_text(value, field_name="Polymarket REST path")
        if not value.startswith("/"):
            msg = "Polymarket REST path must start with /"
            raise ValueError(msg)
        return value

    @field_validator("query", "headers")
    @classmethod
    def validate_string_mapping(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        try:
            return freeze_string_mapping(value, field_name="Polymarket REST string mapping")
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


class PolymarketRestResponse(CanonicalModel):
    """One Polymarket REST response returned by an injected transport."""

    status_code: int = Field(ge=100, le=599)
    body_text: str
    headers: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        try:
            return freeze_string_mapping(value, field_name="Polymarket REST response headers")
        except TypeError as exc:
            raise ValueError(str(exc)) from exc

    @field_serializer("headers")
    def serialize_headers(self, value: Mapping[str, str]) -> dict[str, str]:
        return thaw_string_mapping(value)


class PolymarketMarketListParams(CanonicalModel):
    """Supported Polymarket Gamma keyset market-list query parameters."""

    limit: int | None = Field(
        default=None,
        gt=0,
        le=_POLYMARKET_MARKETS_KEYSET_LIMIT_MAX,
    )
    after_cursor: str | None = Field(default=None, min_length=1, max_length=512)
    order: str | None = Field(default=None, min_length=1, max_length=512)
    ascending: bool | None = None
    closed: bool | None = None
    include_tag: bool | None = None
    condition_ids: tuple[str, ...] = ()
    clob_token_ids: tuple[str, ...] = ()
    question_ids: tuple[str, ...] = ()
    slugs: tuple[str, ...] = ()

    @field_validator("after_cursor", "order")
    @classmethod
    def validate_text_fields(cls, value: str | None) -> str | None:
        return _validate_optional_text(value, field_name="Polymarket market-list query parameter")

    @field_validator("condition_ids", "clob_token_ids", "question_ids", "slugs")
    @classmethod
    def validate_text_tuple_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _validate_text_tuple(value, field_name="Polymarket market-list query parameter")

    def to_query(self) -> Mapping[str, str]:
        query: dict[str, str] = {}
        if self.limit is not None:
            query["limit"] = str(self.limit)
        if self.after_cursor is not None:
            query["after_cursor"] = self.after_cursor
        if self.order is not None:
            query["order"] = self.order
        if self.ascending is not None:
            query["ascending"] = _bool_query_value(self.ascending)
        if self.closed is not None:
            query["closed"] = _bool_query_value(self.closed)
        if self.include_tag is not None:
            query["include_tag"] = _bool_query_value(self.include_tag)
        _add_text_tuple_query(query, "condition_ids", self.condition_ids)
        _add_text_tuple_query(query, "clob_token_ids", self.clob_token_ids)
        _add_text_tuple_query(query, "question_ids", self.question_ids)
        _add_text_tuple_query(query, "slug", self.slugs)
        return query


class PolymarketRestTransport(Protocol):
    """Async transport boundary used by the Polymarket REST client."""

    async def send(self, request: PolymarketRestRequest) -> PolymarketRestResponse:
        """Send one translated Polymarket REST request."""

        ...


class PolymarketMarketDataRestClient:
    """Polymarket market-data REST client using an injected transport."""

    def __init__(
        self,
        *,
        transport: PolymarketRestTransport,
        default_timeout_seconds: int = POLYMARKET_DEFAULT_REST_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = transport
        self._default_timeout_seconds = _validate_timeout_seconds(default_timeout_seconds)

    async def list_markets(
        self,
        params: PolymarketMarketListParams | None = None,
    ) -> PolymarketMarketListResponse:
        """Fetch and parse a Polymarket Gamma keyset market-list response."""

        actual_params = params if params is not None else PolymarketMarketListParams()
        request = PolymarketRestRequest(
            method="GET",
            path=POLYMARKET_MARKETS_KEYSET_PATH,
            query=actual_params.to_query(),
            headers={},
            timeout_seconds=self._default_timeout_seconds,
        )
        response = await self._transport.send(request)
        if response.status_code == 200:
            return _parse_market_list_success(response, request=request)
        _raise_rest_error(response, request=request)


def _parse_market_list_success(
    response: PolymarketRestResponse,
    *,
    request: PolymarketRestRequest,
) -> PolymarketMarketListResponse:
    try:
        return parse_polymarket_market_list_json(response.body_text)
    except (TypeError, ValueError) as exc:
        raise AdapterProtocolError(
            "Polymarket market-list response payload is malformed",
            exchange="polymarket",
            endpoint_category=AdapterEndpointCategory.MARKET_DATA,
            http_status=response.status_code,
            context={"endpoint": request.path},
        ) from exc


def _raise_rest_error(
    response: PolymarketRestResponse,
    *,
    request: PolymarketRestRequest,
) -> NoReturn:
    raw_error = _parse_error_response(response)
    http_status = (
        raw_error.http_status if raw_error.http_status is not None else response.status_code
    )
    error_code = raw_error.error_code
    context = _error_context(request=request, response=response)

    if http_status in (401, 403):
        raise AdapterAuthenticationError(
            "Polymarket REST authentication failed",
            exchange="polymarket",
            endpoint_category=AdapterEndpointCategory.MARKET_DATA,
            http_status=http_status,
            exchange_error_code=error_code,
            context=context,
        )
    if http_status == 429:
        raise AdapterRateLimitError(
            "Polymarket REST rate limit exceeded",
            exchange="polymarket",
            endpoint_category=AdapterEndpointCategory.MARKET_DATA,
            http_status=http_status,
            exchange_error_code=error_code,
            context=context,
        )
    if http_status >= 500:
        raise AdapterTransportError(
            "Polymarket REST service error",
            exchange="polymarket",
            endpoint_category=AdapterEndpointCategory.MARKET_DATA,
            http_status=http_status,
            exchange_error_code=error_code,
            context=context,
        )
    raise AdapterProtocolError(
        "Polymarket REST request failed",
        exchange="polymarket",
        endpoint_category=AdapterEndpointCategory.MARKET_DATA,
        http_status=http_status,
        exchange_error_code=error_code,
        context=context,
    )


def _parse_error_response(response: PolymarketRestResponse) -> PolymarketRawErrorResponse:
    try:
        return parse_polymarket_error_json(response.body_text)
    except (TypeError, ValueError):
        return PolymarketRawErrorResponse.from_exchange_payload(
            {
                "http_status": response.status_code,
                "code": "unparseable_error_payload",
                "error": "Polymarket error response was not valid JSON",
            }
        )


def _error_context(
    *,
    request: PolymarketRestRequest,
    response: PolymarketRestResponse,
) -> dict[str, str]:
    context = {"endpoint": request.path}
    retry_after_seconds = _retry_after_seconds(response.headers)
    if retry_after_seconds is not None:
        context["retry_after_seconds"] = retry_after_seconds
    return context


def _retry_after_seconds(headers: Mapping[str, str]) -> str | None:
    value: str | None = None
    for header_name, header_value in headers.items():
        if header_name.lower() == "retry-after":
            value = header_value
            break
    if value is None:
        return None
    if not value.isdecimal():
        return None
    return str(int(value))


def _add_text_tuple_query(
    query: dict[str, str],
    key: str,
    values: tuple[str, ...],
) -> None:
    if values:
        query[key] = ",".join(values)


def _bool_query_value(value: bool) -> str:
    return "true" if value else "false"


def _validate_timeout_seconds(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        msg = "Polymarket REST timeout_seconds must be an integer"
        raise TypeError(msg)
    if value <= 0:
        msg = "Polymarket REST timeout_seconds must be positive"
        raise ValueError(msg)
    if value > _POLYMARKET_REST_TIMEOUT_MAX_SECONDS:
        msg = (
            "Polymarket REST timeout_seconds must be at most "
            f"{_POLYMARKET_REST_TIMEOUT_MAX_SECONDS}"
        )
        raise ValueError(msg)
    return value


def _validate_text_tuple(value: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    if len(set(value)) != len(value):
        msg = f"{field_name} values must be unique"
        raise ValueError(msg)
    return tuple(_validate_required_text(item, field_name=field_name) for item in value)


def _validate_optional_text(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    return _validate_required_text(value, field_name=field_name)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    if len(value) > _POLYMARKET_REST_TEXT_MAX_LENGTH:
        msg = f"{field_name} must be at most {_POLYMARKET_REST_TEXT_MAX_LENGTH} characters"
        raise ValueError(msg)
    return value
