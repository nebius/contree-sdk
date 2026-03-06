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
        entries = files.items() if isinstance(files, dict) else ((None, f) for f in files)
        prepared_by_image_paths = {}
        for image_path, source in entries:
            if isinstance(source, UploadFileSpec):
                if image_path is None:
                    if isinstance(source.source, UploadedFile):
                        raise ValueError(f"In file item {source} there's no information about path")

                    image_path = PurePosixPath(default_image_path) / Path(source.source).name
                item = replace(source, path=PurePosixPath(image_path))
            else:
                if image_path is None:
                    image_path = PurePosixPath(default_image_path) / Path(source).name
                if isinstance(source, str):
                    source = Path(source)
                item = cls(
                    path=PurePosixPath(image_path),
                    source=source,
                )

            if item.path is None:
                raise ValueError(f"File item must have a path: {item}")
            if item.path in prepared_by_image_paths:
                raise ValueError(
                    f"Duplicate destination path `{item.path}`: {prepared_by_image_paths[item.path]} and {item}"
                )
            prepared_by_image_paths[item.path] = item

        return list(prepared_by_image_paths.values())
