"""Canonical simulation configuration schemas."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType

from pydantic import Field, field_serializer, field_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.numeric import parse_decimal

_SIMULATION_MODEL_MAX_LENGTH = 128
_SIMULATION_VERSION_MAX_LENGTH = 128


class SimulationConfiguration(CanonicalModel):
    simulation_version: str = Field(min_length=1, max_length=_SIMULATION_VERSION_MAX_LENGTH)

    fill_model: str = Field(min_length=1, max_length=_SIMULATION_MODEL_MAX_LENGTH)
    queue_model: str = Field(min_length=1, max_length=_SIMULATION_MODEL_MAX_LENGTH)
    latency_model: str = Field(min_length=1, max_length=_SIMULATION_MODEL_MAX_LENGTH)
    fee_model: str = Field(min_length=1, max_length=_SIMULATION_MODEL_MAX_LENGTH)
    rejection_model: str = Field(min_length=1, max_length=_SIMULATION_MODEL_MAX_LENGTH)
    slippage_model: str = Field(min_length=1, max_length=_SIMULATION_MODEL_MAX_LENGTH)
    settlement_model: str = Field(min_length=1, max_length=_SIMULATION_MODEL_MAX_LENGTH)

    random_seed: int = Field(ge=0)

    fixed_latency_ms: int | None = Field(default=None, ge=0)
    maker_fill_probability: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("1"))
    taker_slippage_bps: Decimal | None = Field(default=None, ge=Decimal("0"))

    parameters: Mapping[str, str] = Field(default_factory=dict)

    @field_validator("maker_fill_probability", "taker_slippage_bps", mode="before")
    @classmethod
    def parse_optional_decimal_fields(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        return parse_decimal(value, field_name="simulation configuration decimal field")

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        _validate_string_mapping(value, field_name="simulation parameter")
        return MappingProxyType(dict(value))

    @field_serializer("parameters")
    def serialize_parameters(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)


def _validate_string_mapping(value: Mapping[str, str], *, field_name: str) -> None:
    for key, item in value.items():
        if key == "" or key.strip() != key:
            msg = f"{field_name} keys must be nonempty strings without surrounding whitespace"
            raise ValueError(msg)
        if item == "" or item.strip() != item:
            msg = f"{field_name} values must be nonempty strings without surrounding whitespace"
            raise ValueError(msg)
