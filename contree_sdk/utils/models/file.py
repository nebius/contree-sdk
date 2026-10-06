from __future__ import annotations

import fnmatch
import posixpath
import stat
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath


@dataclass
class UploadedFile:
    uuid: str
    sha256: str


DEFAULT_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH


@dataclass(kw_only=True)
class UploadFileSpec:
    uid: int = 0
    gid: int = 0
    mode: int = DEFAULT_MODE
    path: PurePosixPath | str | None = None

    source: str | Path | bytes | UploadedFile

    @classmethod
    def prepare_files(
        cls,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec],
        default_image_path: str = "/",
    ) -> list[UploadFileSpec]:
        entries = files.items() if isinstance(files, dict) else ((None, f) for f in files)
        prepared_by_image_paths = {}
        directories: set[str] = set()
        for image_path, source in entries:
            if isinstance(source, UploadFileSpec):
                image_path = image_path or source.path
                if image_path is None:
                    if isinstance(source.source, (UploadedFile, bytes)):
                        raise ValueError(f"In file item {source} there's no information about path")
                    image_path = PurePosixPath(default_image_path) / Path(source.source).name
                item = replace(source, path=PurePosixPath(image_path))
            else:
                if image_path is None:
                    if isinstance(source, bytes):
                        raise ValueError("File item with bytes source must have a path")
                    image_path = PurePosixPath(default_image_path) / Path(source).name
                if isinstance(source, str):
                    source = Path(source)
                item = cls(
                    path=PurePosixPath(image_path),
                    source=source,
                )

            if item.path is None:
                raise ValueError(f"File item must have a path: {item}")
            if isinstance(item.source, (str, Path)) and Path(item.source).is_dir():
                tree = prepare_file_tree(
                    item.source,
                    str(item.path),
                    uid=item.uid,
                    gid=item.gid,
                    mode=item.mode if isinstance(source, UploadFileSpec) else None,
                )
            else:
                tree = [item]
            for member in tree:
                add_prepared_file(prepared_by_image_paths, directories, member)

        return list(prepared_by_image_paths.values())


def add_prepared_file(prepared: dict[str, UploadFileSpec], directories: set[str], item: UploadFileSpec) -> None:
    if item.path is None:
        raise ValueError("file destination is required")
    destination = posixpath.normpath(str(item.path))
    parents = {str(parent) for parent in PurePosixPath(destination).parents}
    if destination in prepared or destination in directories or parents.intersection(prepared):
        raise ValueError(f"Duplicate destination path or file/directory conflict: {destination}")
    directories.update(parents)
    prepared[destination] = replace(item, path=PurePosixPath(destination))


def prepare_file_tree(
    source: str | Path,
    destination: str = "/",
    *,
    exclude: tuple[str, ...] = (),
    uid: int = 0,
    gid: int = 0,
    mode: int | None = None,
) -> list[UploadFileSpec]:
    """Expand directory contents into regular files in stable relative-path order.

    Patterns match POSIX relative paths, or basenames when they contain no slash.
    Excluded directories are pruned. Symlinks and special files raise ValueError.
    Empty directories cannot be represented by spawn attachments and are omitted.
    mode=None preserves permission bits; ownership defaults to uid=gid=0.

    Returns:
        Prepared attachments in relative-path order.

    Raises:
        ValueError: The source is not a directory, or an included entry is not a regular file or directory.

    """
    root = Path(source)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"expected a regular directory: {root}")
    files = []

    def walk(directory: Path) -> None:
        for entry in sorted(directory.iterdir()):
            relative = entry.relative_to(root).as_posix()
            if any(
                fnmatch.fnmatchcase(relative, pattern)
                or ("/" not in pattern and fnmatch.fnmatchcase(entry.name, pattern))
                for pattern in exclude
            ):
                continue
            metadata = entry.lstat()
            if stat.S_ISDIR(metadata.st_mode):
                walk(entry)
            elif stat.S_ISREG(metadata.st_mode):
                files.append(
                    UploadFileSpec(
                        source=entry,
                        path=PurePosixPath(destination) / relative,
                        uid=uid,
                        gid=gid,
                        mode=stat.S_IMODE(metadata.st_mode) if mode is None else mode,
                    )
                )
            else:
                raise ValueError(f"symlinks and special files are not supported: {entry}")

    walk(root)
    return files
