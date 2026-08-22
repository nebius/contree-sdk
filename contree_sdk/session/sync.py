from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING

from contree_sdk._internals.io.typing import INPUT_TYPES
from contree_sdk._internals.io.wiring import read_input_sync
from contree_sdk.session.base import (
    RunFiles,
    exit_code_of,
    file_spec_for,
    instance_result,
    new_session_id,
    require_str,
    stream_repr_for_stdin,
    validate_command,
)
from contree_sdk.store import HistoryEntry, SyncMemoryStore, SyncStore
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec


if TYPE_CHECKING:
    from contree_client.models import FileSpec, InstanceResult
    from contree_client.types import ContreeSyncClient


class ContreeSession:
    """A durable, resumable ConTree session backed by a Store (sync)."""

    def __init__(
        self,
        client: ContreeSyncClient,
        *,
        image: str | None = None,
        session_id: str | None = None,
        store: SyncStore | None = None,
        cwd: str | None = None,
    ) -> None:
        if image is None and session_id is None:
            raise ValueError("either image or session_id must be provided")
        self.client = client
        self.store = store or SyncMemoryStore()
        self.session_id = session_id or new_session_id()
        self.cwd = cwd

        tip = self.store.tip(self.session_id)
        if tip is not None:
            self.image_uuid = tip.image_uuid
            self.tip_id = tip.id
        elif image is not None:
            resolved = client.resolve_image(image)
            entry = self.store.append(self.session_id, image_uuid=resolved, parent_id=None, kind="init")
            self.image_uuid = entry.image_uuid
            self.tip_id = entry.id
        else:
            raise ValueError(f"session {self.session_id!r} has no history and no image was given")

    def upload_file(self, file: UploadFileSpec) -> FileSpec:
        source = file.source
        if isinstance(source, UploadedFile):
            uploaded = source
        else:
            path = Path(source) if isinstance(source, str) else source
            content = path.read_bytes() if isinstance(path, Path) else path
            response = self.client.ensure_file(content)
            uploaded = UploadedFile(uuid=response.uuid, sha256=response.sha256)
        return file_spec_for(uploaded, file)

    def build_files(self, files: RunFiles) -> dict[str, FileSpec] | None:
        prepared = UploadFileSpec.prepare_files(files or [])
        if not prepared:
            return None
        return {str(file.path): self.upload_file(file) for file in prepared}

    def run(
        self,
        command: str | None = None,
        *,
        shell: str | None = None,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdin: INPUT_TYPES | None = None,
        files: RunFiles = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
        hostname: str | None = None,
        branch: str | None = None,
    ) -> InstanceResult:
        resolved_command = validate_command(command, shell)
        image_uuid = require_str(self.image_uuid, "session has no resolved image")

        if isinstance(timeout, timedelta):
            timeout = timeout.total_seconds()

        file_specs = self.build_files(files)
        stdin_repr = stream_repr_for_stdin(read_input_sync(stdin)) if stdin is not None else None

        response = self.client.spawn_instance(
            resolved_command,
            image_uuid,
            disposable=disposable,
            shell=shell is not None,
            args=list(args),
            env=env,
            cwd=cwd if cwd is not None else (self.cwd if self.cwd is not None else ...),
            preserve_env=preserve_env,
            hostname=hostname if hostname is not None else ...,
            timeout=ceil(timeout) if timeout is not None else ...,
            truncate_output_at=truncate_output_at if truncate_output_at is not None else ...,
            files=file_specs if file_specs is not None else ...,
            stdin=stdin_repr if stdin_repr is not None else ...,
        )
        operation_uuid = require_str(response.uuid, "spawn_instance response missing operation uuid")
        operation = self.client.wait_operation(operation_uuid, timeout=timeout)
        result = instance_result(operation)

        if not disposable:
            result_image_uuid = require_str(
                operation.result_image_uuid, "operation succeeded but reported no result image"
            )
            entry = self.store.append(
                self.session_id,
                image_uuid=result_image_uuid,
                parent_id=self.tip_id,
                kind="run",
                title=resolved_command,
                operation_uuid=operation_uuid,
                exit_code=exit_code_of(result),
                branch=branch,
            )
            self.tip_id = entry.id
            self.image_uuid = entry.image_uuid

        return result

    def refresh_from_entry(self, entry: HistoryEntry) -> None:
        self.tip_id = entry.id
        self.image_uuid = entry.image_uuid

    def create_branch(self, name: str, *, from_branch: str | None = None) -> None:
        self.store.create_branch(self.session_id, name, from_branch=from_branch)

    def switch_branch(self, name: str) -> None:
        entry = self.store.switch_branch(self.session_id, name)
        self.refresh_from_entry(entry)

    def list_branches(self) -> list[tuple[str, bool]]:
        return self.store.list_branches(self.session_id)

    def delete_branch(self, name: str) -> None:
        self.store.delete_branch(self.session_id, name)

    def rollback(self, steps: int = 1) -> None:
        entry = self.store.rollback(self.session_id, steps)
        self.refresh_from_entry(entry)

    def navigate(self, target: int) -> None:
        entry = self.store.navigate(self.session_id, target)
        self.refresh_from_entry(entry)

    def navigate_forward(self, steps: int = 1) -> None:
        entry = self.store.navigate_forward(self.session_id, steps)
        self.refresh_from_entry(entry)

    def history(self) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        return self.store.history_dag(self.session_id)
