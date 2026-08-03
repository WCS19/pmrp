"""Tests for Kalshi raw error payload models."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.adapters.kalshi import KalshiRawErrorResponse, parse_kalshi_error_json
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "kalshi" / "errors"


def _error_payload(
    *,
    error_overrides: Mapping[str, object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    error: dict[str, object] = {
        "code": "service_unavailable",
        "message": "synthetic service error Kalshi fixture",
    }
    if error_overrides is not None:
        error.update(error_overrides)
    payload: dict[str, object] = {
        "http_status": 503,
        "request_id": "req_fixture_service_error_0001",
        "endpoint": "/trade-api/v2/markets",
        "error": error,
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("fixture_name", "expected_status", "expected_code", "expected_retry_after"),
    [
        ("unauthorized.json", 401, "unauthorized", None),
        ("rate_limited.json", 429, "rate_limited", 3),
        ("service_error.json", 503, "service_unavailable", None),
        ("malformed.json", 400, "malformed_payload", None),
    ],
)
def test_kalshi_error_fixtures_parse(
    fixture_name: str,
    expected_status: int,
    expected_code: str,
    expected_retry_after: int | None,
) -> None:
    error = parse_kalshi_error_json((FIXTURE_ROOT / fixture_name).read_text())

    assert error.http_status == expected_status
    assert error.error_code == expected_code
    assert error.request_id.startswith("req_fixture_")
    assert error.endpoint == "/trade-api/v2/markets"
    assert error.retry_after_seconds == expected_retry_after
    assert error.raw_payload["http_status"] == expected_status


def test_kalshi_error_accepts_flat_exchange_payload() -> None:
    error = KalshiRawErrorResponse.from_exchange_payload(
        {
            "status_code": 429,
            "x_request_id": "req_fixture_rate_limited_0001",
            "endpoint": "/trade-api/v2/markets",
            "error_code": "rate_limited",
            "detail": "synthetic rate limit Kalshi fixture",
            "retry_after": 3,
        }
    )

    assert error.http_status == 429
    assert error.error_code == "rate_limited"
    assert error.message == "synthetic rate limit Kalshi fixture"
    assert error.request_id == "req_fixture_rate_limited_0001"
    assert error.retry_after_seconds == 3


def test_kalshi_error_rejects_unknown_model_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        KalshiRawErrorResponse.model_validate(
            {
                "http_status": 503,
                "error_code": "service_unavailable",
                "message": "synthetic service error Kalshi fixture",
                "raw_payload": _error_payload(),
                "unexpected": "not allowed outside raw_payload",
            }
        )


def test_kalshi_error_rejects_invalid_status_and_retry_after() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 100"):
        KalshiRawErrorResponse.from_exchange_payload(_error_payload(http_status=99))
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        KalshiRawErrorResponse.from_exchange_payload(
            _error_payload(error_overrides={"retry_after_seconds": -1})
        )


def test_kalshi_error_rejects_float_retry_after() -> None:
    with pytest.raises(ValidationError, match="Input should be a valid integer"):
        KalshiRawErrorResponse.from_exchange_payload(
            _error_payload(error_overrides={"retry_after_seconds": 1.5})
        )


def test_kalshi_error_requires_code_or_message() -> None:
    with pytest.raises(ValidationError, match="error code or message"):
        KalshiRawErrorResponse.from_exchange_payload(
            _error_payload(error_overrides={"code": None, "message": None})
        )


def test_kalshi_error_rejects_blank_text_fields() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        KalshiRawErrorResponse.from_exchange_payload(
            _error_payload(error_overrides={"code": " unauthorized "})
        )
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        KalshiRawErrorResponse.from_exchange_payload(_error_payload(request_id=" req "))


def test_kalshi_error_rejects_non_object_nested_error() -> None:
    with pytest.raises(ValueError, match="error must be a JSON object"):
        KalshiRawErrorResponse.from_exchange_payload(
            {
                "http_status": 503,
                "error": "service_unavailable",
            }
        )


def test_kalshi_error_json_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        parse_kalshi_error_json("{")


def test_kalshi_error_json_rejects_non_object_json() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        parse_kalshi_error_json("[]")


def test_kalshi_error_raw_payload_is_immutable_after_validation() -> None:
    error = KalshiRawErrorResponse.from_exchange_payload(_error_payload())
    original_hash = canonical_sha256(error)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        error.http_status = 500
    with pytest.raises(TypeError):
        error.raw_payload["http_status"] = 500

    assert canonical_sha256(error) == original_hash


def test_kalshi_error_json_round_trip_and_stable_hash() -> None:
    error = KalshiRawErrorResponse.from_exchange_payload(_error_payload())
    canonical = canonical_json(error)

    assert '"error_code":"service_unavailable"' in canonical
    assert KalshiRawErrorResponse.model_validate_json(canonical) == error
    assert canonical_sha256(error) == canonical_sha256(
        KalshiRawErrorResponse.model_validate_json(canonical)
    )


def test_kalshi_error_json_schema_generation() -> None:
    assert KalshiRawErrorResponse.model_json_schema()["title"] == "KalshiRawErrorResponse"
