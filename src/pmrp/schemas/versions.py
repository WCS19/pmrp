"""Schema version validation and the initial schema registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from typing import Annotated

from pydantic import BeforeValidator, Field

from pmrp.schemas.base import CanonicalModel


def parse_schema_version(value: object) -> int:
    if isinstance(value, bool):
        msg = "schema version must be a positive integer"
        raise TypeError(msg)
    if not isinstance(value, int):
        msg = "schema version must be a positive integer"
        raise TypeError(msg)
    if value < 1:
        msg = "schema version must be positive"
        raise ValueError(msg)
    return value


type SchemaVersion = Annotated[
    int,
    BeforeValidator(parse_schema_version),
    Field(ge=1),
]


class SchemaCategory(StrEnum):
    VALUE_OBJECT = "value_object"
    METADATA = "metadata"
    REGISTRY = "registry"


class SchemaRegistration(CanonicalModel):
    schema_name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    schema_version: SchemaVersion
    schema_category: SchemaCategory
    model_path: str = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class RegisteredSchema:
    schema_name: str
    schema_version: int
    schema_category: SchemaCategory
    model: type[CanonicalModel]

    def as_registration(self) -> SchemaRegistration:
        return SchemaRegistration(
            schema_name=self.schema_name,
            schema_version=self.schema_version,
            schema_category=self.schema_category,
            model_path=f"{self.model.__module__}.{self.model.__qualname__}",
        )


@cache
def _registered_schemas() -> tuple[RegisteredSchema, ...]:
    from pmrp.schemas.metadata import (
        AuditMetadata,
        FlexibleMetadata,
        SourceMetadata,
        VersionMetadata,
    )
    from pmrp.schemas.numeric import Money, Price, Probability, Quantity

    return (
        RegisteredSchema("price", 1, SchemaCategory.VALUE_OBJECT, Price),
        RegisteredSchema("probability", 1, SchemaCategory.VALUE_OBJECT, Probability),
        RegisteredSchema("quantity", 1, SchemaCategory.VALUE_OBJECT, Quantity),
        RegisteredSchema("money", 1, SchemaCategory.VALUE_OBJECT, Money),
        RegisteredSchema("source_metadata", 1, SchemaCategory.METADATA, SourceMetadata),
        RegisteredSchema("version_metadata", 1, SchemaCategory.METADATA, VersionMetadata),
        RegisteredSchema("audit_metadata", 1, SchemaCategory.METADATA, AuditMetadata),
        RegisteredSchema("flexible_metadata", 1, SchemaCategory.METADATA, FlexibleMetadata),
        RegisteredSchema("schema_registration", 1, SchemaCategory.REGISTRY, SchemaRegistration),
    )


def list_schema_registrations() -> tuple[SchemaRegistration, ...]:
    return tuple(schema.as_registration() for schema in _registered_schemas())


def get_schema_registration(schema_name: str, schema_version: int = 1) -> SchemaRegistration:
    registered_schema = _lookup_registered_schema(schema_name, schema_version)
    return registered_schema.as_registration()


def get_schema_model(schema_name: str, schema_version: int = 1) -> type[CanonicalModel]:
    return _lookup_registered_schema(schema_name, schema_version).model


def schema_json_schema(schema_name: str, schema_version: int = 1) -> dict[str, object]:
    model = get_schema_model(schema_name, schema_version)
    return model.model_json_schema()


def _lookup_registered_schema(schema_name: str, schema_version: int) -> RegisteredSchema:
    version = parse_schema_version(schema_version)
    for registered_schema in _registered_schemas():
        if (
            registered_schema.schema_name == schema_name
            and registered_schema.schema_version == version
        ):
            return registered_schema
    msg = f"schema is not registered: {schema_name} v{version}"
    raise KeyError(msg)
