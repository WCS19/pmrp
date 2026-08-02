"""Tests for shared adapter capability contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pmrp.adapters import AdapterCapabilities
from pmrp.schemas.enums import OrderType, TimeInForce
from pmrp.schemas.serialization import canonical_json, canonical_sha256


def _capabilities_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "exchange": "kalshi",
        "supported_order_types": (OrderType.LIMIT,),
        "supported_time_in_force": (TimeInForce.GTC, TimeInForce.IOC),
        "supports_post_only": True,
        "supports_replace_order": False,
        "supports_client_order_id": True,
        "supports_streaming_order_updates": True,
        "supports_streaming_market_data": True,
        "supports_historical_data": True,
        "supports_sequence_numbers": True,
        "supports_batch_endpoints": False,
        "supports_self_trade_controls": False,
        "max_batch_size": None,
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
def test_adapter_capabilities_accept_valid_payload() -> None:
    capabilities = AdapterCapabilities.model_validate(_capabilities_payload())

    assert capabilities.exchange == "kalshi"
    assert capabilities.has_order_type(OrderType.LIMIT)
    assert not capabilities.has_order_type(OrderType.MARKET)
    assert capabilities.has_time_in_force(TimeInForce.GTC)
    assert not capabilities.has_time_in_force(TimeInForce.FOK)


@pytest.mark.unit
def test_adapter_capabilities_allow_market_data_only_adapter() -> None:
    capabilities = AdapterCapabilities.model_validate(
        _capabilities_payload(
            supported_order_types=(),
            supported_time_in_force=(),
            supports_post_only=False,
            supports_replace_order=False,
            supports_client_order_id=False,
            supports_streaming_order_updates=False,
            supports_batch_endpoints=False,
            supports_self_trade_controls=False,
        )
    )

    assert capabilities.supported_order_types == ()
    assert capabilities.supported_time_in_force == ()
    assert capabilities.supports_streaming_market_data is True


@pytest.mark.unit
def test_adapter_capabilities_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AdapterCapabilities.model_validate(_capabilities_payload(unexpected=True))


@pytest.mark.unit
def test_adapter_capabilities_reject_blank_exchange() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        AdapterCapabilities.model_validate(_capabilities_payload(exchange=" kalshi "))


@pytest.mark.unit
def test_adapter_capabilities_reject_raw_enum_strings() -> None:
    with pytest.raises(ValidationError, match="Input should be an instance of OrderType"):
        AdapterCapabilities.model_validate(_capabilities_payload(supported_order_types=("limit",)))


@pytest.mark.unit
def test_adapter_capabilities_reject_duplicate_order_types() -> None:
    with pytest.raises(ValidationError, match="supported_order_types"):
        AdapterCapabilities.model_validate(
            _capabilities_payload(
                supported_order_types=(OrderType.LIMIT, OrderType.LIMIT),
            )
        )


@pytest.mark.unit
def test_adapter_capabilities_reject_duplicate_time_in_force_values() -> None:
    with pytest.raises(ValidationError, match="supported_time_in_force"):
        AdapterCapabilities.model_validate(
            _capabilities_payload(
                supported_time_in_force=(TimeInForce.GTC, TimeInForce.GTC),
            )
        )


@pytest.mark.unit
def test_adapter_capabilities_reject_nonpositive_max_batch_size() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        AdapterCapabilities.model_validate(_capabilities_payload(max_batch_size=0))


@pytest.mark.unit
def test_adapter_capabilities_allow_known_batch_size() -> None:
    capabilities = AdapterCapabilities.model_validate(
        _capabilities_payload(
            supports_batch_endpoints=True,
            max_batch_size=20,
        )
    )

    assert capabilities.supports_batch_endpoints is True
    assert capabilities.max_batch_size == 20


@pytest.mark.unit
def test_adapter_capabilities_are_immutable_after_validation() -> None:
    capabilities = AdapterCapabilities.model_validate(_capabilities_payload())
    original_hash = canonical_sha256(capabilities)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        capabilities.supports_post_only = False

    assert canonical_sha256(capabilities) == original_hash


@pytest.mark.unit
def test_adapter_capabilities_json_round_trip_and_stable_hash() -> None:
    capabilities = AdapterCapabilities.model_validate(_capabilities_payload())
    canonical = canonical_json(capabilities)

    assert '"supported_order_types":["limit"]' in canonical
    assert AdapterCapabilities.model_validate_json(canonical) == capabilities
    assert canonical_sha256(capabilities) == canonical_sha256(
        AdapterCapabilities.model_validate_json(canonical)
    )


@pytest.mark.unit
def test_adapter_capabilities_json_schema_generation() -> None:
    json_schema = AdapterCapabilities.model_json_schema()

    assert json_schema["title"] == "AdapterCapabilities"
    assert "supports_sequence_numbers" in json_schema["properties"]
