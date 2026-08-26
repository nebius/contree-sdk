from dataclasses import dataclass, field

from contree_sdk.sdk.io.typing import INPUT_TYPES, OUTPUT_REQUEST_TYPES
from contree_sdk.utils.models.file import UploadFileSpec


@dataclass(frozen=True, kw_only=True)
class RunRequest:
    """Pure data: what to run and how.

    No I/O -- reading `stdin` into a wire payload is the sync/async
    caller's job (`contree_sdk.sdk.io.wiring.read_stdin` /
    `read_stdin_sync`), since that step differs by variant.
    """

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

    stderr: OUTPUT_REQUEST_TYPES | None = str
    stdout: OUTPUT_REQUEST_TYPES | None = str

    truncate_output_at: int | None = None

    preserve_env: bool = False
