"""Narrow repository protocols for storage implementations."""

from __future__ import annotations

from typing import Protocol, TypeVar

IdentifierT = TypeVar("IdentifierT", contravariant=True)
EntityT_co = TypeVar("EntityT_co", covariant=True)
VersionedEntityT = TypeVar("VersionedEntityT")


class Repository(Protocol[IdentifierT, EntityT_co]):
    """Read interface shared by storage-backed repositories."""

    async def get(self, entity_id: IdentifierT) -> EntityT_co | None:
        """Return the entity for an identifier, or ``None`` when absent."""
        ...


class VersionedRepository(
    Repository[IdentifierT, VersionedEntityT],
    Protocol[IdentifierT, VersionedEntityT],
):
    """Repository interface for optimistic-concurrency-protected aggregates."""

    async def add(self, entity: VersionedEntityT) -> None:
        """Persist a new entity."""
        ...

    async def save(self, entity: VersionedEntityT, *, expected_version: int) -> None:
        """Persist changes only when the durable version matches."""
        ...
