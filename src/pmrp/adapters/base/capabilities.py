"""Common adapter capability declaration model."""

from __future__ import annotations

from typing import Self

from pydantic import Field, field_validator, model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import OrderType, TimeInForce

_ADAPTER_LABEL_MAX_LENGTH = 128


class AdapterCapabilities(CanonicalModel):
    """Exchange adapter feature declaration used before adapter operations."""

    exchange: str = Field(min_length=1, max_length=_ADAPTER_LABEL_MAX_LENGTH)

    supported_order_types: tuple[OrderType, ...]
    supported_time_in_force: tuple[TimeInForce, ...]

    supports_post_only: bool
    supports_replace_order: bool
    supports_client_order_id: bool
    supports_streaming_order_updates: bool
    supports_streaming_market_data: bool
    supports_historical_data: bool
    supports_sequence_numbers: bool
    supports_batch_endpoints: bool
    supports_self_trade_controls: bool

    max_batch_size: int | None = Field(default=None, gt=0)

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, value: str) -> str:
        return _validate_required_text(value, field_name="exchange")

    @model_validator(mode="after")
    def validate_unique_capability_values(self) -> Self:
        _validate_unique_values(
            self.supported_order_types,
            field_name="supported_order_types",
        )
        _validate_unique_values(
            self.supported_time_in_force,
            field_name="supported_time_in_force",
        )
        return self

    def has_order_type(self, order_type: OrderType) -> bool:
        """Return whether this adapter supports the requested order type."""

        return order_type in self.supported_order_types

    def has_time_in_force(self, time_in_force: TimeInForce) -> bool:
        """Return whether this adapter supports the requested time-in-force value."""

        return time_in_force in self.supported_time_in_force


def _validate_unique_values(values: tuple[object, ...], *, field_name: str) -> None:
    if len(set(values)) != len(values):
        msg = f"{field_name} must not contain duplicate values"
        raise ValueError(msg)


def _validate_required_text(value: str, *, field_name: str) -> str:
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
