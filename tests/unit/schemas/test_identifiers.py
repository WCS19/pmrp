import pytest
from pydantic import ValidationError

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.identifiers import SUPPORTED_IDENTIFIER_PREFIXES, EventId, MarketId

pytestmark = pytest.mark.unit


class IdentifierModel(CanonicalModel):
    event_id: EventId
    market_id: MarketId


def test_identifier_model_accepts_valid_typed_identifiers() -> None:
    model = IdentifierModel(
        event_id=EventId("evt_01j00000000000000000000000"),
        market_id=MarketId("mkt_01j00000000000000000000000"),
    )

    assert isinstance(model.event_id, EventId)
    assert isinstance(model.market_id, MarketId)
    assert str(model.event_id) == "evt_01j00000000000000000000000"


def test_identifier_model_accepts_valid_json_strings() -> None:
    model = IdentifierModel.model_validate_json(
        """
        {
          "event_id": "evt_01j00000000000000000000000",
          "market_id": "mkt_01j00000000000000000000000"
        }
        """
    )

    assert model.event_id == EventId("evt_01j00000000000000000000000")


def test_identifier_rejects_wrong_prefix() -> None:
    with pytest.raises(ValueError, match="must start with 'evt_'"):
        EventId("cmd_01j00000000000000000000000")


def test_identifier_rejects_empty_value() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        EventId("")


def test_identifier_rejects_unsupported_characters() -> None:
    with pytest.raises(ValueError, match="unsupported characters"):
        EventId("evt_invalid value")


def test_identifier_rejects_values_longer_than_maximum() -> None:
    with pytest.raises(ValueError, match="at most 128 characters"):
        EventId("evt_" + ("a" * 125))


def test_identifier_pydantic_validation_rejects_non_string() -> None:
    with pytest.raises(ValidationError, match="Input should be a valid string"):
        IdentifierModel(
            event_id=123,
            market_id=MarketId("mkt_01j00000000000000000000000"),
        )


def test_supported_identifier_prefixes_are_unique() -> None:
    assert len(SUPPORTED_IDENTIFIER_PREFIXES) == len(set(SUPPORTED_IDENTIFIER_PREFIXES))
