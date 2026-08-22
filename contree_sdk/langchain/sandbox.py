"""deepagents `BaseSandbox` backed by a ConTree session."""

from __future__ import annotations

import base64
import shlex
import threading
from uuid import uuid4

from contree_sdk.session import ContreeSession
from contree_sdk.session.base import RunFiles, or_none


try:
    from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
    from deepagents.backends.sandbox import BaseSandbox

    DEEPAGENTS_AVAILABLE = True
except ImportError:
    DEEPAGENTS_AVAILABLE = False
    BaseSandbox = object  # ty: ignore[invalid-assignment]


class ContreeSandbox(BaseSandbox):
    """A deepagents sandbox backed by a (sync) `ContreeSession`.

    deepagents only requires `execute()`, `upload_files()`, `download_files()`
    and `id`; its async counterparts (`aexecute()`, etc.) already bridge to
    these via `asyncio.to_thread`, so no separate async implementation is
    needed here - which also means concurrent agent tool calls can invoke
    `execute()`/`upload_files()` on separate OS threads against the same
    session at once. `self.lock` serializes them so two concurrent
    non-disposable runs can't both read `session.image_uuid` before either
    commits and silently drop one operation's effect on the session pointer.

    Requires the `deepagents` package (`contree-sdk[langchain]`), which in
    turn requires Python >= 3.11; `__init__` raises a clear `ImportError` on
    older interpreters instead of the class failing to import at all.
    """

    def __init__(self, session: ContreeSession) -> None:
        if not DEEPAGENTS_AVAILABLE:
            raise ImportError(
                "ContreeSandbox requires the 'deepagents' package, which requires Python >= 3.11; "
                'install it via `pip install "contree-sdk[langchain]"` on Python >= 3.11'
            )
        self.session = session
        self.sandbox_id = f"contree-{session.session_id}-{uuid4().hex[:8]}"
        self.lock = threading.Lock()

    @property
    def id(self) -> str:
        return self.sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        with self.lock:
            result = self.session.run(
                shell=command, timeout=timeout, disposable=False, truncate_output_at=10 * 1024 * 1024
            )
        stdout = or_none(result.stdout)
        stderr = or_none(result.stderr)
        state = or_none(result.state)
        output = (stdout.as_text() if stdout is not None else "") + (stderr.as_text() if stderr is not None else "")
        exit_code = or_none(state.exit_code) if state is not None else None
        truncated = bool(or_none(stdout.truncated) if stdout is not None else False) or bool(
            or_none(stderr.truncated) if stderr is not None else False
        )
        return ExecuteResponse(output=output, exit_code=exit_code, truncated=truncated)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        valid: RunFiles = {path: content for path, content in files if path.startswith("/")}
        if valid:
            with self.lock:
                self.session.run(shell=":", files=valid, disposable=False)
        return [FileUploadResponse(path=path, error=None if path in valid else "invalid_path") for path, _ in files]

    def download_one_file(self, path: str) -> FileDownloadResponse:
        if not path.startswith("/"):
            return FileDownloadResponse(path=path, error="invalid_path")
        with self.lock:
            result = self.session.run(shell=f"base64 {shlex.quote(path)} 2>/dev/null")
        state = or_none(result.state)
        exit_code = or_none(state.exit_code) if state is not None else None
        stdout = or_none(result.stdout)
        if exit_code != 0 or stdout is None:
            return FileDownloadResponse(path=path, error="file_not_found")
        return FileDownloadResponse(path=path, content=base64.b64decode(stdout.as_text()))

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [self.download_one_file(path) for path in paths]
