import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import MarketStatus, OutcomeType
from pmrp.schemas.markets import Contract, Market, Outcome
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _market_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "market_id": "mkt_01j00000000000000000000000",
        "canonical_event_id": "evt_01j00000000000000000000000",
        "exchange": "kalshi",
        "exchange_market_id": "FED-26SEP-T4.50",
        "exchange_event_id": "FED-26SEP",
        "title": "Will the target range be above 4.50 percent?",
        "subtitle": "Federal Reserve target range",
        "description": "Resolution follows exchange rules.",
        "category": "economics",
        "tags": ("federal_reserve", "interest_rates"),
        "outcome_type": OutcomeType.BINARY,
        "status": MarketStatus.OPEN,
        "opens_at": "2026-01-01T00:00:00Z",
        "closes_at": "2026-09-16T18:00:00Z",
        "resolves_at": "2026-09-16T20:00:00Z",
        "finalized_at": None,
        "currency": "USD",
        "payout_per_unit": "1",
        "tick_size": "0.01",
        "quantity_increment": "1",
        "rules_text": "Resolution follows the published exchange rules.",
        "rules_url": "https://example.test/rules/fed",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-07-28T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def _outcome_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "outcome_id": "out_yes",
        "market_id": "mkt_01j00000000000000000000000",
        "exchange_outcome_id": "yes",
        "name": "Yes",
        "normalized_name": "yes",
        "index": 0,
        "is_tradeable": True,
        "is_winning": None,
        "payout_per_unit": "1",
        "metadata": {"display": "YES"},
    }
    payload.update(overrides)
    return payload


def _contract_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_id": "ctr_01j00000000000000000000000",
        "market_id": "mkt_01j00000000000000000000000",
        "outcome_id": "out_yes",
        "exchange_contract_id": "FED-26SEP-T4.50-YES",
        "symbol": "FEDYES",
        "display_name": "Yes",
        "tick_size": "0.01",
        "quantity_increment": "1",
        "min_order_quantity": "1",
        "max_order_quantity": "1000",
        "active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-07-28T12:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_market_accepts_valid_payload_and_exact_decimals() -> None:
    market = Market.model_validate(_market_payload())

    assert market.market_id == "mkt_01j00000000000000000000000"
    assert market.payout_per_unit == Decimal("1")
    assert market.tick_size == Decimal("0.01")
    assert market.quantity_increment == Decimal("1")


def test_market_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Market.model_validate(_market_payload(unexpected=True))


def test_market_rejects_float_decimal_input() -> None:
    with pytest.raises(TypeError, match="float input"):
        Market.model_validate(_market_payload(tick_size=0.01))


def test_market_rejects_non_positive_tick_size() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        Market.model_validate(_market_payload(tick_size="0"))


def test_market_rejects_invalid_currency() -> None:
    with pytest.raises(ValidationError, match="three-letter uppercase"):
        Market.model_validate(_market_payload(currency="usd"))


def test_market_rejects_closes_at_before_opens_at() -> None:
    with pytest.raises(ValidationError, match="closes_at must not precede opens_at"):
        Market.model_validate(
            _market_payload(
                opens_at="2026-09-16T18:00:00Z",
                closes_at="2026-01-01T00:00:00Z",
            )
        )


def test_market_rejects_naive_created_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Market.model_validate(
            _market_payload(created_at=datetime.fromisoformat("2026-01-01T00:00:00"))
        )


def test_market_json_round_trip_preserves_canonical_values() -> None:
    market = Market.model_validate_json(json.dumps({**_market_payload(), "tags": ["economics"]}))

    assert market.tags == ("economics",)
    assert Market.model_validate_json(canonical_json(market)) == market


def test_outcome_accepts_valid_payload() -> None:
    outcome = Outcome.model_validate(_outcome_payload())

    assert outcome.outcome_id == "out_yes"
    assert outcome.payout_per_unit == Decimal("1")


def test_outcome_metadata_is_immutable_after_validation() -> None:
    outcome = Outcome.model_validate(_outcome_payload())
    original_hash = canonical_sha256(outcome)

    with pytest.raises(TypeError, match="does not support item assignment"):
        outcome.metadata["display"] = "NO"

    assert canonical_sha256(outcome) == original_hash


def test_outcome_rejects_invalid_metadata_key() -> None:
    with pytest.raises(ValidationError, match="keys must be nonempty"):
        Outcome.model_validate(_outcome_payload(metadata={" display": "YES"}))


def test_outcome_rejects_invalid_metadata_value() -> None:
    with pytest.raises(ValidationError, match="values must be nonempty"):
        Outcome.model_validate(_outcome_payload(metadata={"display": " YES"}))


def test_outcome_rejects_negative_index() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Outcome.model_validate(_outcome_payload(index=-1))


def test_outcome_rejects_float_payout() -> None:
    with pytest.raises(TypeError, match="float input"):
        Outcome.model_validate(_outcome_payload(payout_per_unit=1.0))


def test_contract_accepts_valid_payload() -> None:
    contract = Contract.model_validate(_contract_payload())

    assert contract.contract_id == "ctr_01j00000000000000000000000"
    assert contract.min_order_quantity == Decimal("1")


def test_contract_rejects_invalid_quantity_bounds() -> None:
    with pytest.raises(ValidationError, match="max_order_quantity"):
        Contract.model_validate(_contract_payload(min_order_quantity="10", max_order_quantity="1"))


def test_contract_rejects_float_quantity_increment() -> None:
    with pytest.raises(TypeError, match="float input"):
        Contract.model_validate(_contract_payload(quantity_increment=1.0))


def test_market_catalog_schema_registry_entries_exist() -> None:
    assert get_schema_model("market", 1) is Market
    assert get_schema_model("outcome", 1) is Outcome
    assert get_schema_model("contract", 1) is Contract
    assert get_schema_registration("market", 1).model_path == "pmrp.schemas.markets.Market"


def test_market_json_schema_generation() -> None:
    json_schema = Market.model_json_schema()

    assert json_schema["title"] == "Market"
    assert "market_id" in json_schema["properties"]
