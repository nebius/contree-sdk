from asyncio import to_thread
from base64 import b64encode
from dataclasses import dataclass, field

from contree_client.models import ClosableStreamRepr

from contree_sdk._internals.io.typing import INPUT_TYPES, OUTPUT_REQUEST_TYPES
from contree_sdk._internals.io.wiring import read_input
from contree_sdk.utils.models.file import UploadFileSpec


def _encode_stdin(value: str | bytes) -> ClosableStreamRepr:
    if isinstance(value, str):
        return ClosableStreamRepr(value=value, encoding="ascii")
    return ClosableStreamRepr(value=b64encode(value).decode("ascii"), encoding="base64")


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

    stderr: OUTPUT_REQUEST_TYPES | None = str
    stdout: OUTPUT_REQUEST_TYPES | None = str

    truncate_output_at: int | None = None

    preserve_env: bool = False

    async def _read_stdin(self) -> ClosableStreamRepr:
        value = await read_input(self.stdin)
        return await to_thread(_encode_stdin, value)
