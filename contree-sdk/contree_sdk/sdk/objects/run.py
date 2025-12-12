from dataclasses import dataclass, field

from contree_sdk.utils.io_wrap import IO_TYPES
from contree_sdk.utils.models.file import UploadFileSpec


REQUEST_IO_TYPES = IO_TYPES | type[str | bytes] | None


@dataclass(frozen=True, kw_only=True)
class RunRequest:
    command: str | None = None
    args: list[str] | None = None
    shell: bool | None = None
    env: dict[str, str] = field(default_factory=dict)
    cwd: str
    hostname: str | None = None

    files: list[UploadFileSpec] = field(default_factory=list)

    timeout: float | None = None
    disposable: bool
    tag: str | None = None  # tag to be assigned to result
    stdin: IO_TYPES | None = None

    stderr: REQUEST_IO_TYPES = None
    stdout: REQUEST_IO_TYPES = None
