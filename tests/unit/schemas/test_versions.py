import pytest
from pydantic import ValidationError

from pmrp.schemas.numeric import Money
from pmrp.schemas.versions import (
    SchemaRegistration,
    get_schema_model,
    get_schema_registration,
    list_schema_registrations,
    parse_schema_version,
    schema_json_schema,
)

pytestmark = pytest.mark.unit


def test_parse_schema_version_accepts_positive_integer() -> None:
    assert parse_schema_version(1) == 1


def test_parse_schema_version_rejects_zero() -> None:
    with pytest.raises(ValueError, match="positive"):
        parse_schema_version(0)


def test_parse_schema_version_rejects_bool() -> None:
    with pytest.raises(TypeError, match="positive integer"):
        parse_schema_version(True)


def test_schema_registration_rejects_invalid_version() -> None:
    with pytest.raises(ValidationError, match="schema version must be positive"):
        SchemaRegistration(
            schema_name="money",
            schema_version=0,
            schema_category="value_object",
            model_path="pmrp.schemas.numeric.Money",
        )


def test_registry_lookup_returns_registered_schema_model() -> None:
    assert get_schema_model("money", 1) is Money


def test_registry_lookup_returns_registration_metadata() -> None:
    registration = get_schema_registration("money", 1)

    assert registration.schema_name == "money"
    assert registration.schema_version == 1
    assert registration.model_path == "pmrp.schemas.numeric.Money"


def test_registry_lookup_rejects_unknown_schema() -> None:
    with pytest.raises(KeyError, match="schema is not registered"):
        get_schema_model("not_registered", 1)


def test_list_schema_registrations_includes_foundational_schemas() -> None:
    schema_names = {registration.schema_name for registration in list_schema_registrations()}

    assert {"money", "price", "probability", "quantity"}.issubset(schema_names)


def test_registered_schema_json_schema_can_be_generated() -> None:
    json_schema = schema_json_schema("money", 1)

    assert json_schema["title"] == "Money"
    assert "amount" in json_schema["properties"]
