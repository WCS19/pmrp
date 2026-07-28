from typing import Final

import pytest
from pydantic import ValidationError

from pmrp.schemas.base import CanonicalModel

pytestmark = pytest.mark.unit


class ExampleCanonicalModel(CanonicalModel):
    name: str
    count: int


def test_canonical_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExampleCanonicalModel(name="market", count=1, unexpected=True)


def test_canonical_model_is_frozen() -> None:
    model = ExampleCanonicalModel(name="market", count=1)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        model.count = 2


def test_canonical_model_rejects_dangerous_implicit_coercion() -> None:
    with pytest.raises(ValidationError, match="valid integer"):
        ExampleCanonicalModel(name="market", count="1")


def test_canonical_model_validates_defaults() -> None:
    class InvalidDefaultModel(CanonicalModel):
        count: int = "1"  # type: ignore[assignment]

    with pytest.raises(ValidationError, match="valid integer"):
        InvalidDefaultModel()


def test_canonical_model_preserves_whitespace() -> None:
    value: Final = "  keep spacing  "

    model = ExampleCanonicalModel(name=value, count=1)

    assert model.name == value
