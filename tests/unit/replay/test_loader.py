"""Tests for replay manifest and dataset loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmrp.replay import (
    ReplayChecksumError,
    ReplayDataset,
    ReplayDatasetLoadError,
    ReplayManifestLoadError,
    calculate_replay_dataset_checksum,
    load_replay_dataset,
    load_replay_events_jsonl,
    load_replay_manifest,
)
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.unit

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "replay" / "basic_market"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
EVENTS_PATH = FIXTURE_ROOT / "events.jsonl"


def test_load_replay_manifest_validates_fixture_metadata() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)

    assert manifest.replay_session_id == "rpl_01j00000000000000000000000"
    assert manifest.dataset_id == "dataset_basic_market"
    assert manifest.dataset_checksum.startswith("sha256:")
    assert manifest.event_ordering_policy_version == "occurred-sequence-received-v1"
    assert manifest.strategy_versions == {"strat_threshold_v1": "1.0.0"}


def test_load_replay_manifest_requires_manifest_filename() -> None:
    with pytest.raises(ReplayManifestLoadError) as exc_info:
        load_replay_manifest(FIXTURE_ROOT / "events.jsonl")

    assert str(exc_info.value) == "Replay manifest path must end with manifest.json"
    assert exc_info.value.reason_code == "replay_manifest_path_invalid"
    assert exc_info.value.context["path"].endswith("events.jsonl")
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_load_replay_manifest_rejects_invalid_json_without_raw_payload(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"dataset_id":"raw_payload_sentinel"', encoding="utf-8")

    with pytest.raises(ReplayManifestLoadError) as exc_info:
        load_replay_manifest(manifest_path)

    assert str(exc_info.value) == "Replay manifest is invalid"
    assert exc_info.value.reason_code == "replay_manifest_invalid"
    assert "raw_payload_sentinel" not in str(exc_info.value)
    assert "raw_payload_sentinel" not in exc_info.value.context.values()
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_load_replay_manifest_wraps_float_type_errors_safely(tmp_path: Path) -> None:
    manifest_payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_payload["speed"] = 1.0
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    with pytest.raises(ReplayManifestLoadError) as exc_info:
        load_replay_manifest(manifest_path)

    assert str(exc_info.value) == "Replay manifest is invalid"
    assert exc_info.value.reason_code == "replay_manifest_invalid"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_load_replay_events_jsonl_returns_canonical_events_in_file_order() -> None:
    events = load_replay_events_jsonl(EVENTS_PATH)

    assert [event.event_id for event in events] == ["evt_replay_0001", "evt_replay_0002"]
    assert [event.replay_session_id for event in events] == [
        "rpl_01j00000000000000000000000",
        "rpl_01j00000000000000000000000",
    ]
    assert [event.event_type for event in events] == [
        "market.order_book_snapshot",
        "market.trade_observed",
    ]
    assert events[1].causation_id == "evt_replay_0001"


def test_load_replay_events_jsonl_requires_jsonl_suffix() -> None:
    with pytest.raises(ReplayDatasetLoadError) as exc_info:
        load_replay_events_jsonl(MANIFEST_PATH)

    assert str(exc_info.value) == "Replay event path must end with .jsonl"
    assert exc_info.value.reason_code == "replay_event_path_invalid"
    assert exc_info.value.context["path"].endswith("manifest.json")
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_load_replay_events_jsonl_rejects_invalid_line_without_raw_payload(
    tmp_path: Path,
) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text('{"event_id":"raw_payload_sentinel"\n', encoding="utf-8")

    with pytest.raises(ReplayDatasetLoadError) as exc_info:
        load_replay_events_jsonl(event_path)

    assert str(exc_info.value) == "Replay event line is invalid"
    assert exc_info.value.reason_code == "replay_event_line_invalid"
    assert exc_info.value.context["line_number"] == "1"
    assert "raw_payload_sentinel" not in str(exc_info.value)
    assert "raw_payload_sentinel" not in exc_info.value.context.values()
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_load_replay_events_jsonl_wraps_float_attribute_type_errors_safely(
    tmp_path: Path,
) -> None:
    event_payload = json.loads(EVENTS_PATH.read_text(encoding="utf-8").splitlines()[0])
    event_payload["attributes"] = {"float_value": 1.0}
    event_path = tmp_path / "events.jsonl"
    event_path.write_text(json.dumps(event_payload), encoding="utf-8")

    with pytest.raises(ReplayDatasetLoadError) as exc_info:
        load_replay_events_jsonl(event_path)

    assert str(exc_info.value) == "Replay event line is invalid"
    assert exc_info.value.reason_code == "replay_event_line_invalid"
    assert exc_info.value.context["line_number"] == "1"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_load_replay_events_jsonl_rejects_empty_event_files(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text("\n\n", encoding="utf-8")

    with pytest.raises(ReplayDatasetLoadError) as exc_info:
        load_replay_events_jsonl(event_path)

    assert str(exc_info.value) == "Replay event file did not contain events"
    assert exc_info.value.reason_code == "replay_event_file_empty"


def test_calculate_replay_dataset_checksum_matches_manifest() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    events = load_replay_events_jsonl(EVENTS_PATH)

    assert calculate_replay_dataset_checksum(events) == manifest.dataset_checksum
    assert calculate_replay_dataset_checksum(events) == calculate_replay_dataset_checksum(events)


def test_load_replay_dataset_validates_manifest_checksum_and_serializes_stably() -> None:
    dataset = load_replay_dataset(
        manifest_path=MANIFEST_PATH,
        event_paths=(EVENTS_PATH,),
    )
    original_hash = canonical_sha256(dataset)
    canonical = canonical_json(dataset)

    assert dataset.dataset_checksum == dataset.manifest.dataset_checksum
    assert len(dataset.events) == 2
    assert ReplayDataset.model_validate_json(canonical) == dataset
    assert canonical_sha256(ReplayDataset.model_validate_json(canonical)) == original_hash


def test_load_replay_dataset_requires_event_paths() -> None:
    with pytest.raises(ReplayDatasetLoadError) as exc_info:
        load_replay_dataset(manifest_path=MANIFEST_PATH, event_paths=())

    assert str(exc_info.value) == "Replay dataset requires at least one event file"
    assert exc_info.value.reason_code == "replay_dataset_event_paths_required"


def test_load_replay_dataset_rejects_checksum_mismatch(tmp_path: Path) -> None:
    manifest_payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_payload["dataset_checksum"] = "sha256:mismatch"
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    with pytest.raises(ReplayChecksumError) as exc_info:
        load_replay_dataset(manifest_path=manifest_path, event_paths=(EVENTS_PATH,))

    assert str(exc_info.value) == "Replay dataset checksum does not match manifest"
    assert exc_info.value.reason_code == "replay_dataset_checksum_mismatch"
    assert exc_info.value.context["dataset_id"] == "dataset_basic_market"
    assert exc_info.value.context["expected_checksum"] == "sha256:mismatch"
    assert exc_info.value.context["actual_checksum"].startswith("sha256:")
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None


def test_replay_dataset_rejects_events_without_matching_replay_session() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    event = _fixture_event_with(replay_session_id="rpl_01j11111111111111111111111")

    with pytest.raises(ValidationError, match="replay_session_id must match"):
        ReplayDataset(
            manifest=manifest,
            events=(event,),
            dataset_checksum=manifest.dataset_checksum,
        )


def test_replay_dataset_rejects_events_outside_manifest_window() -> None:
    manifest = load_replay_manifest(MANIFEST_PATH)
    event = _fixture_event_with(occurred_at="2026-07-28T16:00:01Z")

    with pytest.raises(ValidationError, match="within manifest replay window"):
        ReplayDataset(
            manifest=manifest,
            events=(event,),
            dataset_checksum=manifest.dataset_checksum,
        )


def test_replay_package_does_not_import_live_boundaries() -> None:
    replay_root = Path(__file__).resolve().parents[3] / "src" / "pmrp" / "replay"
    source = "\n".join(path.read_text(encoding="utf-8") for path in replay_root.glob("*.py"))

    assert "pmrp.adapters" not in source
    assert "pmrp.execution" not in source
    assert "sqlalchemy" not in source
    assert "asyncpg" not in source
    assert "httpx" not in source


def _fixture_event_with(**overrides: object) -> EventEnvelope:
    payload = json.loads(canonical_json(load_replay_events_jsonl(EVENTS_PATH)[0]))
    payload.update(overrides)
    return EventEnvelope.model_validate_json(json.dumps(payload))
