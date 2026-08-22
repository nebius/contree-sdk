"""Local build context: the host directory + `.dockerignore` filter.

Encapsulates everything needed to assemble the set of files that will be
uploaded to the API as part of a build: the root directory, the parsed
`.dockerignore` rules, and the directory-walking logic that turns
`COPY`/`ADD` source specs into concrete `MappedFile` entries.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import posixpath
from dataclasses import dataclass, field
from pathlib import Path

from .dockerignore import DockerignoreRule, is_ignored, parse_dockerignore


DEFAULT_FILE_EXCLUDES = (
    ".*",
    ".git",
    "*.pyc",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "node_modules",
    "dist",
    "build",
)


@dataclass(frozen=True, slots=True)
class MappedFile:
    host_path: str
    instance_path: str
    uid: int
    gid: int
    mode: int

    def sha256(self) -> str:
        # hex SHA256 digest of the host file (streamed)
        digest = hashlib.sha256()
        with Path(self.host_path).open("rb") as handle:
            while chunk := handle.read(256 * 1024):
                digest.update(chunk)
        return digest.hexdigest()


@dataclass(frozen=True)
class LocalContext:
    """Read-only handle for the local build context directory."""

    root: Path
    dockerignore: tuple[DockerignoreRule, ...] = field(default_factory=tuple)

    @classmethod
    def from_dir(cls, root: Path) -> LocalContext:
        return cls(root=root.resolve(), dockerignore=parse_dockerignore(root))

    def is_ignored(self, rel_path: str) -> bool:
        if is_ignored(rel_path, self.dockerignore):
            return True
        return matches_default_excludes(rel_path)

    def collect(
        self, sources: tuple[str, ...], dest: str, *, uid: int, gid: int, mode_override: int | None
    ) -> list[MappedFile]:
        # walk every source, return MappedFile rows for upload
        mapped: list[MappedFile] = []
        for src in sources:
            host_path = (self.root / src).resolve()
            if not str(host_path).startswith(str(self.root)):
                raise ValueError(f"COPY/ADD source escapes context: {src!r}")
            mapped.extend(self.walk(host_path, dest, sources, uid, gid, mode_override))
        return mapped

    def walk(
        self, host_path: Path, dest: str, sources: tuple[str, ...], uid: int, gid: int, mode_override: int | None
    ) -> list[MappedFile]:
        if host_path.is_file():
            return self.walk_file(host_path, dest, sources, uid, gid, mode_override)
        if host_path.is_dir():
            return self.walk_dir(host_path, dest, uid, gid, mode_override)
        raise FileNotFoundError(f"COPY/ADD source not found: {host_path}")

    def walk_file(
        self, host_path: Path, dest: str, sources: tuple[str, ...], uid: int, gid: int, mode_override: int | None
    ) -> list[MappedFile]:
        rel = host_path.relative_to(self.root).as_posix()
        if self.is_ignored(rel):
            return []
        dest_is_dir = dest.endswith("/") or len(sources) > 1
        instance_path = posixpath.join(dest.rstrip("/"), host_path.name) if dest_is_dir else dest
        mode = mode_override if mode_override is not None else (host_path.stat().st_mode & 0o7777)
        return [MappedFile(host_path=str(host_path), instance_path=instance_path, uid=uid, gid=gid, mode=mode)]

    def walk_dir(self, host_path: Path, dest: str, uid: int, gid: int, mode_override: int | None) -> list[MappedFile]:
        # preserves the directory's internal layout under dest - Docker copies a directory
        # source's *contents*, not the directory itself
        base = dest.rstrip("/") or "/"
        result: list[MappedFile] = []
        for root, dirs, files in os.walk(str(host_path), topdown=True):
            rel_root = os.path.relpath(root, str(self.root))
            rel_root_posix = "" if rel_root == "." else rel_root.replace(os.sep, "/")
            dirs[:] = [name for name in dirs if not self.is_ignored(join_rel(rel_root_posix, name))]
            for name in files:
                rel_file = join_rel(rel_root_posix, name)
                if self.is_ignored(rel_file):
                    continue
                full = os.path.join(root, name)
                if not Path(full).is_file():
                    continue
                rel_to_source = os.path.relpath(full, str(host_path)).replace(os.sep, "/")
                instance_path = f"{base.rstrip('/')}/{rel_to_source}"
                mode = mode_override if mode_override is not None else (Path(full).stat().st_mode & 0o7777)
                result.append(MappedFile(host_path=full, instance_path=instance_path, uid=uid, gid=gid, mode=mode))
        return result


def join_rel(rel_root: str, name: str) -> str:
    return name if not rel_root else f"{rel_root}/{name}"


def matches_default_excludes(rel_path: str) -> bool:
    parts = rel_path.split("/")
    for pattern in DEFAULT_FILE_EXCLUDES:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False
