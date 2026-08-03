"""Tests for the Kalshi REST market-listing client."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters import (
    AdapterAuthenticationError,
    AdapterProtocolError,
    AdapterRateLimitError,
    AdapterTransportError,
)
from pmrp.adapters.kalshi import (
    KALSHI_MARKETS_PATH,
    KalshiMarketDataRestClient,
    KalshiMarketListParams,
    KalshiRestRequest,
    KalshiRestResponse,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

MARKET_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kalshi" / "markets"
ERROR_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kalshi" / "errors"


class FakeKalshiRestTransport:
    def __init__(self, responses: Sequence[KalshiRestResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[KalshiRestRequest] = []

    async def send(self, request: KalshiRestRequest) -> KalshiRestResponse:
        self.requests.append(request)
        return self._responses.pop(0)


def _response(body_text: str, *, status_code: int = 200) -> KalshiRestResponse:
    return KalshiRestResponse(
        status_code=status_code,
        body_text=body_text,
        headers={"content-type": "application/json"},
    )


@pytest.mark.asyncio
async def test_kalshi_rest_market_listing_builds_request_and_parses_raw_response() -> None:
    transport = FakeKalshiRestTransport(
        [_response((MARKET_FIXTURE_ROOT / "list_success.json").read_text())]
    )
    client = KalshiMarketDataRestClient(transport=transport, default_timeout_seconds=7)

    response = await client.list_markets(
        KalshiMarketListParams(limit=50, cursor="cursor_fixture_markets_001", status="open")
    )

    assert len(response.markets) == 1
    assert response.markets[0].ticker == "KX-PMRP-EXAMPLE-YES"
    assert response.cursor == "cursor_fixture_markets_002"
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.path == KALSHI_MARKETS_PATH
    assert request.target == (
        "/trade-api/v2/markets?cursor=cursor_fixture_markets_001&limit=50&status=open"
    )
    assert request.timeout_seconds == 7
    assert request.headers == {}


@pytest.mark.asyncio
async def test_kalshi_rest_market_listing_uses_empty_query_by_default() -> None:
    transport = FakeKalshiRestTransport(
        [_response((MARKET_FIXTURE_ROOT / "optional_fields.json").read_text())]
    )
    client = KalshiMarketDataRestClient(transport=transport)

    response = await client.list_markets()

    assert response.markets[0].ticker == "KX-PMRP-OPTIONAL-YES"
    assert transport.requests[0].target == KALSHI_MARKETS_PATH
    assert transport.requests[0].timeout_seconds == 10


def test_kalshi_rest_request_response_and_params_are_strict_and_immutable() -> None:
    request = KalshiRestRequest(
        method="GET",
        path=KALSHI_MARKETS_PATH,
        query={"limit": "50"},
        headers={"accept": "application/json"},
        timeout_seconds=10,
    )
    response = _response((MARKET_FIXTURE_ROOT / "list_success.json").read_text())
    params = KalshiMarketListParams(limit=50, cursor="cursor_fixture_markets_001", status="open")
    original_hash = canonical_sha256(request)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        request.timeout_seconds = 11
    with pytest.raises(TypeError):
        request.query["limit"] = "51"
    with pytest.raises(TypeError):
        response.headers["content-type"] = "text/plain"

    assert params.to_query() == {
        "limit": "50",
        "cursor": "cursor_fixture_markets_001",
        "status": "open",
    }
    assert canonical_sha256(request) == original_hash


def test_kalshi_rest_request_rejects_invalid_path_and_timeout() -> None:
    with pytest.raises(ValidationError, match="must start with /"):
        KalshiRestRequest(method="GET", path="trade-api/v2/markets", timeout_seconds=10)
    with pytest.raises(ValidationError, match="greater than 0"):
        KalshiRestRequest(method="GET", path=KALSHI_MARKETS_PATH, timeout_seconds=0)
    with pytest.raises(TypeError, match="timeout_seconds must be an integer"):
        KalshiMarketDataRestClient(
            transport=FakeKalshiRestTransport(()),
            default_timeout_seconds=True,
        )


def test_kalshi_market_list_params_rejects_blank_text() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        KalshiMarketListParams(cursor=" cursor ")
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        KalshiMarketListParams(status=" open ")


@pytest.mark.asyncio
async def test_kalshi_rest_market_listing_rejects_malformed_success_payload() -> None:
    transport = FakeKalshiRestTransport([_response("{")])
    client = KalshiMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterProtocolError) as exc_info:
        await client.list_markets()

    assert exc_info.value.context["endpoint"] == KALSHI_MARKETS_PATH
    assert exc_info.value.context["http_status"] == "200"


@pytest.mark.asyncio
async def test_kalshi_rest_market_listing_classifies_authentication_error() -> None:
    transport = FakeKalshiRestTransport(
        [_response((ERROR_FIXTURE_ROOT / "unauthorized.json").read_text(), status_code=401)]
    )
    client = KalshiMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterAuthenticationError) as exc_info:
        await client.list_markets()

    assert exc_info.value.retryable is False
    assert exc_info.value.context["http_status"] == "401"
    assert exc_info.value.context["exchange_error_code"] == "unauthorized"
    assert exc_info.value.context["request_id"] == "req_fixture_unauthorized_0001"


@pytest.mark.asyncio
async def test_kalshi_rest_market_listing_classifies_rate_limit_error() -> None:
    transport = FakeKalshiRestTransport(
        [_response((ERROR_FIXTURE_ROOT / "rate_limited.json").read_text(), status_code=429)]
    )
    client = KalshiMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterRateLimitError) as exc_info:
        await client.list_markets()

    assert exc_info.value.retryable is True
    assert exc_info.value.context["http_status"] == "429"
    assert exc_info.value.context["retry_after_seconds"] == "3"


@pytest.mark.asyncio
async def test_kalshi_rest_market_listing_classifies_service_error() -> None:
    transport = FakeKalshiRestTransport(
        [_response((ERROR_FIXTURE_ROOT / "service_error.json").read_text(), status_code=503)]
    )
    client = KalshiMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterTransportError) as exc_info:
        await client.list_markets()

    assert exc_info.value.retryable is True
    assert exc_info.value.context["http_status"] == "503"
    assert exc_info.value.context["exchange_error_code"] == "service_unavailable"


@pytest.mark.asyncio
async def test_kalshi_rest_market_listing_classifies_malformed_request_error() -> None:
    transport = FakeKalshiRestTransport(
        [_response((ERROR_FIXTURE_ROOT / "malformed.json").read_text(), status_code=400)]
    )
    client = KalshiMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterProtocolError) as exc_info:
        await client.list_markets()

    assert exc_info.value.retryable is False
    assert exc_info.value.context["http_status"] == "400"
    assert exc_info.value.context["exchange_error_code"] == "malformed_payload"


@pytest.mark.asyncio
async def test_kalshi_rest_market_listing_handles_unparseable_error_payload_safely() -> None:
    transport = FakeKalshiRestTransport([_response("not json", status_code=502)])
    client = KalshiMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterTransportError) as exc_info:
        await client.list_markets()

    assert exc_info.value.context["http_status"] == "502"
    assert exc_info.value.context["exchange_error_code"] == "unparseable_error_payload"
    assert "not json" not in str(exc_info.value)


def test_kalshi_rest_models_json_round_trip_and_stable_hash() -> None:
    request = KalshiRestRequest(
        method="GET",
        path=KALSHI_MARKETS_PATH,
        query={"limit": "50"},
        headers={},
        timeout_seconds=10,
    )
    canonical = canonical_json(request)

    assert '"path":"/trade-api/v2/markets"' in canonical
    assert KalshiRestRequest.model_validate_json(canonical) == request
    assert canonical_sha256(request) == canonical_sha256(
        KalshiRestRequest.model_validate_json(canonical)
    )
