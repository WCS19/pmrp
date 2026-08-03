"""Tests for the Polymarket REST market-listing client."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters import (
    AdapterProtocolError,
    AdapterRateLimitError,
    AdapterTransportError,
)
from pmrp.adapters.polymarket import (
    POLYMARKET_MARKETS_KEYSET_PATH,
    PolymarketMarketDataRestClient,
    PolymarketMarketListParams,
    PolymarketRestRequest,
    PolymarketRestResponse,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

MARKET_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "polymarket" / "markets"
ERROR_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "polymarket" / "errors"


class FakePolymarketRestTransport:
    def __init__(self, responses: Sequence[PolymarketRestResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[PolymarketRestRequest] = []

    async def send(self, request: PolymarketRestRequest) -> PolymarketRestResponse:
        self.requests.append(request)
        return self._responses.pop(0)


def _response(
    body_text: str,
    *,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> PolymarketRestResponse:
    return PolymarketRestResponse(
        status_code=status_code,
        body_text=body_text,
        headers=headers if headers is not None else {"content-type": "application/json"},
    )


@pytest.mark.asyncio
async def test_polymarket_rest_market_listing_builds_keyset_request_and_parses_response() -> None:
    transport = FakePolymarketRestTransport(
        [_response((MARKET_FIXTURE_ROOT / "keyset_success.json").read_text())]
    )
    client = PolymarketMarketDataRestClient(transport=transport, default_timeout_seconds=7)

    response = await client.list_markets(
        PolymarketMarketListParams(
            limit=20,
            after_cursor="cursor_fixture_markets_001",
            order="volume_num,liquidity_num",
            ascending=True,
            closed=False,
            include_tag=True,
            condition_ids=("0x111", "0x222"),
        )
    )

    assert len(response.markets) == 1
    assert response.markets[0].market_id == "pm_market_fixture_0001"
    assert response.markets[0].clob_token_ids[0].startswith("101010")
    assert response.next_cursor == "cursor_fixture_markets_002"
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "GET"
    assert request.path == POLYMARKET_MARKETS_KEYSET_PATH
    assert request.target == (
        "/markets/keyset?after_cursor=cursor_fixture_markets_001"
        "&ascending=true&closed=false&condition_ids=0x111%2C0x222"
        "&include_tag=true&limit=20&order=volume_num%2Cliquidity_num"
    )
    assert request.timeout_seconds == 7
    assert request.headers == {}


@pytest.mark.asyncio
async def test_polymarket_rest_market_listing_uses_empty_query_by_default() -> None:
    transport = FakePolymarketRestTransport(
        [_response((MARKET_FIXTURE_ROOT / "keyset_success.json").read_text())]
    )
    client = PolymarketMarketDataRestClient(transport=transport)

    response = await client.list_markets()

    assert response.markets[0].question == "Will the PMRP fixture market resolve yes?"
    assert transport.requests[0].target == POLYMARKET_MARKETS_KEYSET_PATH
    assert transport.requests[0].timeout_seconds == 10


def test_polymarket_rest_request_response_and_params_are_strict_and_immutable() -> None:
    request = PolymarketRestRequest(
        method="GET",
        path=POLYMARKET_MARKETS_KEYSET_PATH,
        query={"limit": "20"},
        headers={"accept": "application/json"},
        timeout_seconds=10,
    )
    response = _response((MARKET_FIXTURE_ROOT / "keyset_success.json").read_text())
    params = PolymarketMarketListParams(
        limit=20,
        closed=False,
        clob_token_ids=("101010", "202020"),
        slugs=("pmrp-fixture-market",),
    )
    original_hash = canonical_sha256(request)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        request.timeout_seconds = 11
    with pytest.raises(TypeError):
        request.query["limit"] = "21"
    with pytest.raises(TypeError):
        response.headers["content-type"] = "text/plain"

    assert params.to_query() == {
        "limit": "20",
        "closed": "false",
        "clob_token_ids": "101010,202020",
        "slug": "pmrp-fixture-market",
    }
    assert canonical_sha256(request) == original_hash


def test_polymarket_rest_request_rejects_invalid_path_and_timeout() -> None:
    with pytest.raises(ValidationError, match="must start with /"):
        PolymarketRestRequest(method="GET", path="markets/keyset", timeout_seconds=10)
    with pytest.raises(ValidationError, match="greater than 0"):
        PolymarketRestRequest(
            method="GET",
            path=POLYMARKET_MARKETS_KEYSET_PATH,
            timeout_seconds=0,
        )
    with pytest.raises(TypeError, match="timeout_seconds must be an integer"):
        PolymarketMarketDataRestClient(
            transport=FakePolymarketRestTransport(()),
            default_timeout_seconds=True,
        )


def test_polymarket_market_list_params_reject_invalid_values() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 100"):
        PolymarketMarketListParams(limit=101)
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        PolymarketMarketListParams(after_cursor=" cursor ")
    with pytest.raises(ValidationError, match="values must be unique"):
        PolymarketMarketListParams(condition_ids=("0x111", "0x111"))


@pytest.mark.asyncio
async def test_polymarket_rest_market_listing_rejects_malformed_success_payload() -> None:
    transport = FakePolymarketRestTransport([_response("{")])
    client = PolymarketMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterProtocolError) as exc_info:
        await client.list_markets()

    assert exc_info.value.context["endpoint"] == POLYMARKET_MARKETS_KEYSET_PATH
    assert exc_info.value.context["http_status"] == "200"


@pytest.mark.asyncio
async def test_polymarket_rest_market_listing_classifies_validation_error() -> None:
    transport = FakePolymarketRestTransport(
        [
            _response(
                (ERROR_FIXTURE_ROOT / "keyset_validation.json").read_text(),
                status_code=422,
            )
        ]
    )
    client = PolymarketMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterProtocolError) as exc_info:
        await client.list_markets()

    assert exc_info.value.retryable is False
    assert exc_info.value.context["http_status"] == "422"
    assert exc_info.value.context["exchange_error_code"] == "validation error"


@pytest.mark.asyncio
async def test_polymarket_rest_market_listing_classifies_rate_limit_error() -> None:
    transport = FakePolymarketRestTransport(
        [
            _response(
                (ERROR_FIXTURE_ROOT / "rate_limited.json").read_text(),
                status_code=429,
                headers={"Retry-After": "3"},
            )
        ]
    )
    client = PolymarketMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterRateLimitError) as exc_info:
        await client.list_markets()

    assert exc_info.value.retryable is True
    assert exc_info.value.context["http_status"] == "429"
    assert exc_info.value.context["exchange_error_code"] == "rate limit"
    assert exc_info.value.context["retry_after_seconds"] == "3"


@pytest.mark.asyncio
async def test_polymarket_rest_market_listing_classifies_service_error() -> None:
    transport = FakePolymarketRestTransport(
        [
            _response(
                (ERROR_FIXTURE_ROOT / "service_unavailable.json").read_text(),
                status_code=503,
            )
        ]
    )
    client = PolymarketMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterTransportError) as exc_info:
        await client.list_markets()

    assert exc_info.value.retryable is True
    assert exc_info.value.context["http_status"] == "503"
    assert exc_info.value.context["exchange_error_code"] == "service unavailable"


@pytest.mark.asyncio
async def test_polymarket_rest_market_listing_handles_unparseable_error_payload_safely() -> None:
    transport = FakePolymarketRestTransport([_response("not json", status_code=502)])
    client = PolymarketMarketDataRestClient(transport=transport)

    with pytest.raises(AdapterTransportError) as exc_info:
        await client.list_markets()

    assert exc_info.value.context["http_status"] == "502"
    assert exc_info.value.context["exchange_error_code"] == "unparseable_error_payload"
    assert "not json" not in str(exc_info.value)


def test_polymarket_rest_models_json_round_trip_and_stable_hash() -> None:
    request = PolymarketRestRequest(
        method="GET",
        path=POLYMARKET_MARKETS_KEYSET_PATH,
        query={"limit": "20"},
        headers={},
        timeout_seconds=10,
    )
    canonical = canonical_json(request)

    assert '"path":"/markets/keyset"' in canonical
    assert PolymarketRestRequest.model_validate_json(canonical) == request
    assert canonical_sha256(request) == canonical_sha256(
        PolymarketRestRequest.model_validate_json(canonical)
    )
