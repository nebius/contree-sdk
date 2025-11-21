from dataclasses import dataclass, field

from contree_sdk.utils.io_wrap import IO_TYPES
from contree_sdk.utils.objects.file import UploadFileSpec


@dataclass(frozen=True, kw_only=True)
class RunRequest:
    command: str | None = None
    args: list[str] | None = None
    shell: bool | None = None
    env: dict[str, str] = field(default_factory=dict)
    cwd: str

    files: list[UploadFileSpec] = field(default_factory=list)

    tag: str | None = None  # tag to be assigned to result
    stdin: IO_TYPES | None = None

    stderr: IO_TYPES | None = None
    stdout: IO_TYPES | None = None
