"""Shared Pydantic base for immutable canonical contracts."""

from pydantic import BaseModel, ConfigDict


class CanonicalModel(BaseModel):
    """Base class for canonical, persisted, and transmitted PMRP schemas."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=False,
        strict=True,
        validate_assignment=False,
        validate_default=True,
    )
