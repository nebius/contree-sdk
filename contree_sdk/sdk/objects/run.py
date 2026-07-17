from dataclasses import dataclass, field

from contree_sdk._internals.io.typing import INPUT_TYPES, OUTPUT_REQUEST_TYPES
from contree_sdk.utils.models.file import UploadFileSpec


@dataclass(frozen=True, kw_only=True)
class RunRequest:
    command: str
    args: list[str] | None = None
    shell: bool | None = None
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    hostname: str | None = None

    files: list[UploadFileSpec] = field(default_factory=list)

    timeout: float | None = None
    disposable: bool
    tag: str | None = None  # tag to be assigned to result
    stdin: INPUT_TYPES | None = None

    stderr: OUTPUT_REQUEST_TYPES = str
    stdout: OUTPUT_REQUEST_TYPES = str

    truncate_output_at: int | None = None

    preserve_env: bool = False
