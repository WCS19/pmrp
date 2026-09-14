"""Replay dataset loading."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, ValidationError, model_validator

from pmrp.replay.checksum import calculate_replay_dataset_checksum
from pmrp.replay.errors import ReplayChecksumError, ReplayDatasetLoadError
from pmrp.replay.manifest import PathLike, load_replay_manifest
from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.events import EventEnvelope
from pmrp.schemas.replay import ReplayManifest


class ReplayDataset(CanonicalModel):
    """Loaded replay manifest and event sequence."""

    manifest: ReplayManifest
    events: tuple[EventEnvelope, ...] = Field(min_length=1)
    dataset_checksum: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_dataset(self) -> ReplayDataset:
        if self.dataset_checksum != self.manifest.dataset_checksum:
            msg = "dataset_checksum must match manifest dataset_checksum"
            raise ValueError(msg)
        for event in self.events:
            if event.replay_session_id != self.manifest.replay_session_id:
                msg = "event replay_session_id must match manifest replay_session_id"
                raise ValueError(msg)
            if (
                event.occurred_at < self.manifest.starts_at
                or event.occurred_at > self.manifest.ends_at
            ):
                msg = "event occurred_at must be within manifest replay window"
                raise ValueError(msg)
        return self


def load_replay_dataset(
    *,
    manifest_path: PathLike,
    event_paths: tuple[PathLike, ...],
) -> ReplayDataset:
    """Load a replay manifest and JSONL event files with checksum validation."""

    if not event_paths:
        raise ReplayDatasetLoadError(
            "Replay dataset requires at least one event file",
            reason_code="replay_dataset_event_paths_required",
        )
    manifest = load_replay_manifest(manifest_path)
    events = _load_replay_event_files(event_paths)
    dataset_checksum = calculate_replay_dataset_checksum(events)
    if dataset_checksum != manifest.dataset_checksum:
        raise ReplayChecksumError(
            "Replay dataset checksum does not match manifest",
            reason_code="replay_dataset_checksum_mismatch",
            context={
                "dataset_id": manifest.dataset_id,
                "expected_checksum": manifest.dataset_checksum,
                "actual_checksum": dataset_checksum,
            },
        )
    dataset = _try_build_dataset(
        manifest=manifest,
        events=events,
        dataset_checksum=dataset_checksum,
    )
    if dataset is None:
        raise ReplayDatasetLoadError(
            "Replay dataset is invalid",
            reason_code="replay_dataset_invalid",
            context={"dataset_id": manifest.dataset_id},
        )
    return dataset


def load_replay_events_jsonl(path: PathLike) -> tuple[EventEnvelope, ...]:
    """Load canonical event envelopes from one JSON Lines replay file."""

    event_path = _event_path(path)
    lines = _try_read_event_lines(event_path)
    if lines is None:
        raise ReplayDatasetLoadError(
            "Replay event file could not be read",
            reason_code="replay_event_file_read_failed",
            context={"path": str(event_path)},
        )

    events: list[EventEnvelope] = []
    for line_number, line in enumerate(lines, start=1):
        if line == "" or line.isspace():
            continue
        event = _try_parse_event_line(line)
        if event is None:
            raise ReplayDatasetLoadError(
                "Replay event line is invalid",
                reason_code="replay_event_line_invalid",
                context={"path": str(event_path), "line_number": str(line_number)},
            )
        events.append(event)
    if not events:
        raise ReplayDatasetLoadError(
            "Replay event file did not contain events",
            reason_code="replay_event_file_empty",
            context={"path": str(event_path)},
        )
    return tuple(events)


def _load_replay_event_files(event_paths: tuple[PathLike, ...]) -> tuple[EventEnvelope, ...]:
    events: list[EventEnvelope] = []
    for event_path in event_paths:
        events.extend(load_replay_events_jsonl(event_path))
    return tuple(events)


def _event_path(path: PathLike) -> Path:
    event_path = Path(path)
    if event_path.suffix != ".jsonl":
        raise ReplayDatasetLoadError(
            "Replay event path must end with .jsonl",
            reason_code="replay_event_path_invalid",
            context={"path": str(event_path)},
        )
    return event_path


def _try_read_event_lines(event_path: Path) -> tuple[str, ...] | None:
    try:
        return tuple(event_path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return None


def _try_parse_event_line(line: str) -> EventEnvelope | None:
    try:
        return EventEnvelope.model_validate_json(line)
    except (ValueError, ValidationError):
        return None


def _try_build_dataset(
    *,
    manifest: ReplayManifest,
    events: tuple[EventEnvelope, ...],
    dataset_checksum: str,
) -> ReplayDataset | None:
    try:
        return ReplayDataset(
            manifest=manifest,
            events=events,
            dataset_checksum=dataset_checksum,
        )
    except (TypeError, ValueError, ValidationError):
        return None
