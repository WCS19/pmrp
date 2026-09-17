"""Strategy state checkpoint primitives."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from pmrp.schemas.identifiers import EventId, StrategyId
from pmrp.schemas.immutability import freeze_canonical_mapping, thaw_canonical_mapping
from pmrp.schemas.serialization import canonical_sha256
from pmrp.strategies.errors import StrategyStateStoreError

_STATE_NAMESPACE_PATTERN = re.compile(r"^[a-z][a-z0-9_:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class StrategyStateCheckpoint:
    """Immutable point-in-time state payload for one strategy namespace."""

    strategy_id: StrategyId
    namespace: str
    version: int
    state: Mapping[str, object]
    state_hash: str
    source_event_id: EventId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, StrategyId):
            msg = "strategy_id must be a StrategyId"
            raise TypeError(msg)
        namespace = _validate_namespace(self.namespace)
        version = _validate_version(self.version)
        frozen_state = freeze_canonical_mapping(self.state, field_name="strategy state")
        state_hash = _validate_state_hash(self.state_hash, frozen_state)
        if self.source_event_id is not None and not isinstance(self.source_event_id, EventId):
            msg = "source_event_id must be an EventId when provided"
            raise TypeError(msg)

        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "state", frozen_state)
        object.__setattr__(self, "state_hash", state_hash)


class StrategyStateStore(Protocol):
    """Checkpoint store contract for isolated strategy state namespaces."""

    def save_checkpoint(
        self,
        *,
        strategy_id: StrategyId,
        state: Mapping[str, object],
        namespace: str = "default",
        source_event_id: EventId | None = None,
    ) -> StrategyStateCheckpoint:
        """Persist one state checkpoint and return the immutable stored view."""
        ...

    def load_latest(
        self,
        *,
        strategy_id: StrategyId,
        namespace: str = "default",
    ) -> StrategyStateCheckpoint | None:
        """Return the latest checkpoint for one strategy namespace."""
        ...

    def load_checkpoint(
        self,
        *,
        strategy_id: StrategyId,
        version: int,
        namespace: str = "default",
    ) -> StrategyStateCheckpoint | None:
        """Return one checkpoint version for one strategy namespace."""
        ...

    def list_checkpoints(
        self,
        *,
        strategy_id: StrategyId,
        namespace: str = "default",
    ) -> tuple[StrategyStateCheckpoint, ...]:
        """Return checkpoint history for one strategy namespace."""
        ...


class InMemoryStrategyStateStore:
    """Deterministic in-memory checkpoint store for tests, replay, and local runtime use."""

    def __init__(self) -> None:
        self._checkpoints: dict[tuple[StrategyId, str], list[StrategyStateCheckpoint]] = {}

    def save_checkpoint(
        self,
        *,
        strategy_id: StrategyId,
        state: Mapping[str, object],
        namespace: str = "default",
        source_event_id: EventId | None = None,
    ) -> StrategyStateCheckpoint:
        """Save an immutable checkpoint with a monotonically increasing namespace version."""

        _validate_strategy_id(strategy_id)
        namespace = _validate_namespace(namespace)
        frozen_state = freeze_canonical_mapping(state, field_name="strategy state")
        key = (strategy_id, namespace)
        version = len(self._checkpoints.get(key, ())) + 1
        checkpoint = StrategyStateCheckpoint(
            strategy_id=strategy_id,
            namespace=namespace,
            version=version,
            state=frozen_state,
            state_hash=canonical_sha256(frozen_state),
            source_event_id=source_event_id,
        )
        self._checkpoints.setdefault(key, []).append(checkpoint)
        return checkpoint

    def load_latest(
        self,
        *,
        strategy_id: StrategyId,
        namespace: str = "default",
    ) -> StrategyStateCheckpoint | None:
        """Return the latest checkpoint for one strategy namespace."""

        checkpoints = self.list_checkpoints(strategy_id=strategy_id, namespace=namespace)
        if not checkpoints:
            return None
        return checkpoints[-1]

    def load_checkpoint(
        self,
        *,
        strategy_id: StrategyId,
        version: int,
        namespace: str = "default",
    ) -> StrategyStateCheckpoint | None:
        """Return one checkpoint version for one strategy namespace."""

        _validate_version(version)
        for checkpoint in self.list_checkpoints(strategy_id=strategy_id, namespace=namespace):
            if checkpoint.version == version:
                return checkpoint
        return None

    def list_checkpoints(
        self,
        *,
        strategy_id: StrategyId,
        namespace: str = "default",
    ) -> tuple[StrategyStateCheckpoint, ...]:
        """Return checkpoint history for one strategy namespace."""

        _validate_strategy_id(strategy_id)
        namespace = _validate_namespace(namespace)
        return tuple(self._checkpoints.get((strategy_id, namespace), ()))

    def clear_strategy(self, strategy_id: StrategyId) -> None:
        """Remove all checkpoints for one strategy instance."""

        _validate_strategy_id(strategy_id)
        keys = tuple(key for key in self._checkpoints if key[0] == strategy_id)
        for key in keys:
            del self._checkpoints[key]


def _validate_strategy_id(strategy_id: StrategyId) -> None:
    if not isinstance(strategy_id, StrategyId):
        raise StrategyStateStoreError(
            "strategy_id must be a StrategyId",
            reason_code="strategy_state_store_strategy_id_invalid",
        )


def _validate_namespace(namespace: str) -> str:
    if type(namespace) is not str:
        raise StrategyStateStoreError(
            "strategy state namespace must be a string",
            reason_code="strategy_state_store_namespace_invalid",
        )
    if _STATE_NAMESPACE_PATTERN.fullmatch(namespace) is None:
        raise StrategyStateStoreError(
            "strategy state namespace must use a lowercase safe identifier",
            reason_code="strategy_state_store_namespace_invalid",
            context={
                "namespace": namespace if isinstance(namespace, str) else type(namespace).__name__,
            },
        )
    return namespace


def _validate_version(version: int) -> int:
    if type(version) is not int:
        raise StrategyStateStoreError(
            "strategy state checkpoint version must be an int",
            reason_code="strategy_state_store_version_invalid",
        )
    if version < 1:
        raise StrategyStateStoreError(
            "strategy state checkpoint version must be positive",
            reason_code="strategy_state_store_version_invalid",
            context={"version": str(version)},
        )
    return version


def _validate_state_hash(state_hash: str, state: Mapping[str, object]) -> str:
    if type(state_hash) is not str:
        msg = "state_hash must be a string"
        raise TypeError(msg)
    expected_hash = canonical_sha256(state)
    if state_hash != expected_hash:
        msg = "state_hash must match the canonical strategy state payload"
        raise ValueError(msg)
    return state_hash


def thaw_checkpoint_state(checkpoint: StrategyStateCheckpoint) -> dict[str, object]:
    """Return a mutable JSON-shaped copy of checkpoint state for read-model consumers."""

    return thaw_canonical_mapping(checkpoint.state)
