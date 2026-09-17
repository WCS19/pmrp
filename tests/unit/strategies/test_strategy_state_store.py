"""Strategy state checkpoint store tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

import pytest

from pmrp.schemas.identifiers import EventId, StrategyId
from pmrp.schemas.serialization import canonical_sha256
from pmrp.strategies import (
    InMemoryStrategyStateStore,
    StrategyStateCheckpoint,
    StrategyStateStoreError,
    thaw_checkpoint_state,
)

pytestmark = pytest.mark.unit


def test_in_memory_strategy_state_store_saves_versioned_checkpoints() -> None:
    store = InMemoryStrategyStateStore()
    strategy_id = StrategyId("strat_state_store_test")

    first = store.save_checkpoint(
        strategy_id=strategy_id,
        namespace="signals",
        state={"position": Decimal("2"), "seen_events": ["evt_a"]},
        source_event_id=EventId("evt_state_store_source_a"),
    )
    second = store.save_checkpoint(
        strategy_id=strategy_id,
        namespace="signals",
        state={"position": Decimal("3"), "seen_events": ["evt_a", "evt_b"]},
        source_event_id=EventId("evt_state_store_source_b"),
    )

    assert first.version == 1
    assert second.version == 2
    assert second.source_event_id == "evt_state_store_source_b"
    assert store.load_latest(strategy_id=strategy_id, namespace="signals") == second
    assert store.load_checkpoint(strategy_id=strategy_id, namespace="signals", version=1) == first
    assert store.list_checkpoints(strategy_id=strategy_id, namespace="signals") == (
        first,
        second,
    )


def test_strategy_state_store_isolates_strategy_and_namespace() -> None:
    store = InMemoryStrategyStateStore()
    first_strategy_id = StrategyId("strat_state_store_first")
    second_strategy_id = StrategyId("strat_state_store_second")

    default_checkpoint = store.save_checkpoint(
        strategy_id=first_strategy_id,
        state={"value": "default"},
    )
    private_checkpoint = store.save_checkpoint(
        strategy_id=first_strategy_id,
        namespace="private",
        state={"value": "private"},
    )
    other_checkpoint = store.save_checkpoint(
        strategy_id=second_strategy_id,
        state={"value": "other"},
    )

    assert default_checkpoint.version == 1
    assert private_checkpoint.version == 1
    assert other_checkpoint.version == 1
    assert store.load_latest(strategy_id=first_strategy_id) == default_checkpoint
    assert (
        store.load_latest(strategy_id=first_strategy_id, namespace="private") == private_checkpoint
    )
    assert store.load_latest(strategy_id=second_strategy_id) == other_checkpoint
    assert store.load_latest(strategy_id=StrategyId("strat_state_store_missing")) is None


def test_strategy_state_checkpoint_freezes_state_and_hashes_canonical_payload() -> None:
    source_state: dict[str, object] = {
        "position": Decimal("2"),
        "nested": {"thresholds": [Decimal("0.51"), Decimal("0.62")]},
    }
    checkpoint = InMemoryStrategyStateStore().save_checkpoint(
        strategy_id=StrategyId("strat_state_store_immutable"),
        state=source_state,
    )
    original_hash = checkpoint.state_hash

    source_state["position"] = Decimal("99")
    with pytest.raises(TypeError, match="does not support item assignment"):
        cast(Any, checkpoint.state)["position"] = Decimal("4")

    thawed_state = thaw_checkpoint_state(checkpoint)
    assert thawed_state == {
        "position": Decimal("2"),
        "nested": {"thresholds": [Decimal("0.51"), Decimal("0.62")]},
    }
    assert checkpoint.state_hash == canonical_sha256(checkpoint.state)
    assert checkpoint.state_hash == original_hash


def test_strategy_state_store_rejects_noncanonical_state_values() -> None:
    store = InMemoryStrategyStateStore()

    with pytest.raises(TypeError, match="must not contain floats"):
        store.save_checkpoint(
            strategy_id=StrategyId("strat_state_store_float"),
            state={"probability": 0.5},
        )

    with pytest.raises(TypeError, match="must not contain unordered sets"):
        store.save_checkpoint(
            strategy_id=StrategyId("strat_state_store_set"),
            state={"seen": {"evt_a", "evt_b"}},
        )


def test_strategy_state_store_rejects_invalid_scope_and_version_inputs() -> None:
    store = InMemoryStrategyStateStore()

    with pytest.raises(StrategyStateStoreError) as strategy_error:
        store.save_checkpoint(
            strategy_id=cast(Any, "strat_state_store_bad"),
            state={"value": "bad"},
        )

    assert strategy_error.value.reason_code == "strategy_state_store_strategy_id_invalid"

    with pytest.raises(StrategyStateStoreError) as namespace_error:
        store.save_checkpoint(
            strategy_id=StrategyId("strat_state_store_bad_namespace"),
            namespace="Bad Namespace",
            state={"value": "bad"},
        )

    assert namespace_error.value.reason_code == "strategy_state_store_namespace_invalid"

    with pytest.raises(StrategyStateStoreError) as version_error:
        store.load_checkpoint(
            strategy_id=StrategyId("strat_state_store_bad_version"),
            version=0,
        )

    assert version_error.value.reason_code == "strategy_state_store_version_invalid"


def test_strategy_state_checkpoint_rejects_hash_and_source_event_mismatch() -> None:
    with pytest.raises(ValueError, match="state_hash must match"):
        StrategyStateCheckpoint(
            strategy_id=StrategyId("strat_state_store_hash"),
            namespace="default",
            version=1,
            state={"value": "current"},
            state_hash="sha256:incorrect",
        )

    with pytest.raises(TypeError, match="source_event_id"):
        StrategyStateCheckpoint(
            strategy_id=StrategyId("strat_state_store_event"),
            namespace="default",
            version=1,
            state={"value": "current"},
            state_hash=canonical_sha256({"value": "current"}),
            source_event_id=cast(Any, "evt_state_store_source"),
        )


def test_strategy_state_store_clears_all_namespaces_for_strategy() -> None:
    store = InMemoryStrategyStateStore()
    strategy_id = StrategyId("strat_state_store_clear")

    store.save_checkpoint(strategy_id=strategy_id, state={"value": "default"})
    store.save_checkpoint(strategy_id=strategy_id, namespace="private", state={"value": "private"})
    store.save_checkpoint(
        strategy_id=StrategyId("strat_state_store_clear_other"),
        state={"value": "other"},
    )

    store.clear_strategy(strategy_id)

    assert store.load_latest(strategy_id=strategy_id) is None
    assert store.load_latest(strategy_id=strategy_id, namespace="private") is None
    assert store.load_latest(strategy_id=StrategyId("strat_state_store_clear_other")) is not None
