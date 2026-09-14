"""Replay manifest loading."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from pmrp.replay.errors import ReplayManifestLoadError
from pmrp.schemas.replay import ReplayManifest

type PathLike = str | Path


def load_replay_manifest(path: PathLike) -> ReplayManifest:
    """Load and validate a replay manifest JSON file."""

    manifest_path = _manifest_path(path)
    manifest_text = _try_read_manifest_text(manifest_path)
    if manifest_text is None:
        raise ReplayManifestLoadError(
            "Replay manifest could not be read",
            reason_code="replay_manifest_read_failed",
            context={"path": str(manifest_path)},
        )
    manifest = _try_parse_manifest(manifest_text)
    if manifest is None:
        raise ReplayManifestLoadError(
            "Replay manifest is invalid",
            reason_code="replay_manifest_invalid",
            context={"path": str(manifest_path)},
        )
    return manifest


def _manifest_path(path: PathLike) -> Path:
    manifest_path = Path(path)
    if manifest_path.name != "manifest.json":
        raise ReplayManifestLoadError(
            "Replay manifest path must end with manifest.json",
            reason_code="replay_manifest_path_invalid",
            context={"path": str(manifest_path)},
        )
    return manifest_path


def _try_read_manifest_text(manifest_path: Path) -> str | None:
    try:
        return manifest_path.read_text(encoding="utf-8")
    except OSError:
        return None


def _try_parse_manifest(manifest_text: str) -> ReplayManifest | None:
    try:
        return ReplayManifest.model_validate_json(manifest_text)
    except (ValueError, ValidationError):
        return None
