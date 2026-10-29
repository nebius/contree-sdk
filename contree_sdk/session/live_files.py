"""Validation shared by sync and async live operation attachments."""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path, PurePosixPath

from contree_client.models import FileSpec

from contree_sdk.files import RunFiles, UploadFileSpec
from contree_sdk.utils.models.file import DEFAULT_MODE


def prepare_live_sources(files: RunFiles) -> list[str | Path | UploadFileSpec]:
    """Expand inputs while enforcing live placement's fixed metadata.

    Returns:
        Regular file sources with live-compatible destination metadata.

    Raises:
        ValueError: A destination or explicit metadata setting is unsupported.

    """
    sources = files.values() if isinstance(files, dict) else files or ()
    for source in sources:
        if isinstance(source, UploadFileSpec) and (source.uid != 0 or source.gid != 0 or source.mode != DEFAULT_MODE):
            raise ValueError("live file upload cannot set uid, gid, or mode")
    prepared = UploadFileSpec.prepare_files(files or [])
    for file in prepared:
        if not PurePosixPath(str(file.path)).is_absolute() or "\x00" in str(file.path):
            raise ValueError(f"live file destination must be absolute: {file.path!s}")
    return [replace(file, mode=DEFAULT_MODE) for file in prepared]


def validate_live_files(files: Mapping[str, FileSpec]) -> dict[str, str]:
    """Validate file references before any file is applied.

    Returns:
        Destination paths mapped to uploaded UUIDs.

    Raises:
        ValueError: A destination, UUID, or unsupported metadata is invalid.

    """
    validated = {}
    for path, spec in files.items():
        if not PurePosixPath(path).is_absolute() or "\x00" in path:
            raise ValueError(f"live file destination must be absolute: {path!r}")
        if not isinstance(spec.uuid, str) or not spec.uuid:
            raise ValueError(f"live file at {path!r} requires an uploaded file UUID")
        if spec.uid not in {..., 0} or spec.gid not in {..., 0} or spec.mode not in {..., 0o644, "0644"}:
            raise ValueError(f"live file at {path!r} cannot set uid, gid, or mode")
        validated[path] = spec.uuid
    return validated
