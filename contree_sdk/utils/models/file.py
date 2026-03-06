from __future__ import annotations

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

    source: str | Path | UploadedFile

    @classmethod
    def _prepare_files(
        cls,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec],
        default_image_path: str = "/",
    ) -> list[UploadFileSpec]:
        if isinstance(files, dict):
            entries = files.items()
        else:
            entries = (
                (f.path if isinstance(f, UploadFileSpec) else PurePosixPath(default_image_path) / Path(f).name, f)
                for f in files
            )
        prepared_by_image_paths = {}
        for image_path, source in entries:
            if image_path is None:
                raise ValueError(f"UploadFileSpec must have a path when used in a list: {source}")
            if isinstance(source, UploadFileSpec):
                item = replace(source, path=PurePosixPath(image_path))
            else:
                if isinstance(source, str):
                    source = Path(source)
                item = cls(
                    path=PurePosixPath(image_path),
                    source=source,
                )

            if item.path in prepared_by_image_paths:
                raise ValueError(
                    f"Duplicate destination path `{item.path}`: {prepared_by_image_paths[item.path]} and {item}"
                )
            prepared_by_image_paths[item.path] = item

        return list(prepared_by_image_paths.values())
