"""Helpers for deeply immutable canonical container fields."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType


def freeze_canonical_mapping(
    value: Mapping[str, object],
    *,
    field_name: str,
) -> Mapping[str, object]:
    """Freeze a JSON-shaped mapping without changing its serialized shape."""

    frozen_values: dict[str, object] = {}
    for key, item in value.items():
        _validate_mapping_key(key, field_name=field_name)
        frozen_values[key] = freeze_canonical_value(item, field_name=field_name)
    return MappingProxyType(frozen_values)


def freeze_string_mapping(
    value: Mapping[str, str],
    *,
    field_name: str,
) -> Mapping[str, str]:
    """Freeze a string-to-string mapping without changing its serialized shape."""

    frozen_values: dict[str, str] = {}
    for key, item in value.items():
        _validate_mapping_key(key, field_name=field_name)
        if type(item) is not str:
            msg = f"{field_name} values must be strings"
            raise TypeError(msg)
        if item == "" or item.strip() != item:
            msg = f"{field_name} values must be nonempty strings without surrounding whitespace"
            raise ValueError(msg)
        frozen_values[key] = item
    return MappingProxyType(frozen_values)


def freeze_canonical_value(value: object, *, field_name: str) -> object:
    if isinstance(value, Mapping):
        return freeze_canonical_mapping(value, field_name=field_name)
    if isinstance(value, set | frozenset):
        msg = f"{field_name} values must not contain unordered sets"
        raise TypeError(msg)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(freeze_canonical_value(item, field_name=field_name) for item in value)
    return value


def thaw_canonical_mapping(value: Mapping[str, object]) -> dict[str, object]:
    """Convert immutable canonical containers back to JSON-shaped containers."""

    return {key: thaw_canonical_value(item) for key, item in value.items()}


def thaw_string_mapping(value: Mapping[str, str]) -> dict[str, str]:
    return dict(value)


def thaw_canonical_value(value: object) -> object:
    if isinstance(value, Mapping):
        return thaw_canonical_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [thaw_canonical_value(item) for item in value]
    return value


def _validate_mapping_key(key: object, *, field_name: str) -> None:
    if type(key) is not str:
        msg = f"{field_name} keys must be strings"
        raise TypeError(msg)
    if key == "" or key.strip() != key:
        msg = f"{field_name} keys must be nonempty strings without surrounding whitespace"
        raise ValueError(msg)
