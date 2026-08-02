"""Tests for Kalshi adapter capability declarations."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pmrp.adapters.base import AdapterCapabilities
from pmrp.adapters.kalshi import KALSHI_CAPABILITIES, kalshi_capabilities
from pmrp.adapters.kalshi.capabilities import KALSHI_EXCHANGE
from pmrp.schemas.enums import OrderType, TimeInForce
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit


def test_kalshi_capabilities_are_declared_for_kalshi_exchange() -> None:
    capabilities = kalshi_capabilities()

    assert capabilities is KALSHI_CAPABILITIES
    assert isinstance(capabilities, AdapterCapabilities)
    assert capabilities.exchange == KALSHI_EXCHANGE


def test_kalshi_capabilities_cover_m5_market_data_scope() -> None:
    capabilities = kalshi_capabilities()

    assert capabilities.supports_streaming_market_data is True
    assert capabilities.supports_historical_data is True
    assert capabilities.supports_sequence_numbers is True
    assert capabilities.supports_streaming_order_updates is False


def test_kalshi_capabilities_cover_deferred_execution_metadata() -> None:
    capabilities = kalshi_capabilities()

    assert capabilities.has_order_type(OrderType.LIMIT)
    assert capabilities.has_order_type(OrderType.MARKET)
    assert capabilities.has_time_in_force(TimeInForce.GTC)
    assert capabilities.has_time_in_force(TimeInForce.IOC)
    assert capabilities.supports_client_order_id is True
    assert capabilities.supports_post_only is True
    assert capabilities.supports_replace_order is False
    assert capabilities.supports_batch_endpoints is False
    assert capabilities.supports_self_trade_controls is False


def test_kalshi_capabilities_are_immutable_after_validation() -> None:
    capabilities = kalshi_capabilities()
    original_hash = canonical_sha256(capabilities)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        capabilities.supports_replace_order = True

    assert canonical_sha256(capabilities) == original_hash


def test_kalshi_capabilities_json_round_trip_and_stable_hash() -> None:
    capabilities = kalshi_capabilities()
    canonical = canonical_json(capabilities)

    assert '"exchange":"kalshi"' in canonical
    assert AdapterCapabilities.model_validate_json(canonical) == capabilities
    assert canonical_sha256(capabilities) == canonical_sha256(
        AdapterCapabilities.model_validate_json(canonical)
    )
