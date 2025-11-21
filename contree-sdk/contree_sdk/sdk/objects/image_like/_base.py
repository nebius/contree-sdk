from __future__ import annotations

from asyncio import gather, sleep, to_thread
from collections.abc import Iterable
from copy import copy
from dataclasses import replace
from pathlib import Path
from typing import IO, TYPE_CHECKING, Self
from uuid import UUID

from contree_sdk.api.models.instance import InstanceFileSpec, InstanceSpawnRequest, OperationStatus
from contree_sdk.sdk.exceptions.image import ContreeImageParametersError
from contree_sdk.sdk.objects.image_like.state import ImageState
from contree_sdk.sdk.objects.run import RunRequest
from contree_sdk.utils.codecs import io_decode, io_encode
from contree_sdk.utils.io_wrap import IO_TYPES, IOMode, get_io_by_obj
from contree_sdk.utils.objects.file import UploadedFile, UploadFileSpec
from contree_sdk.utils.objects.stream import StreamDescription


if TYPE_CHECKING:
    from contree_sdk.sdk.client._base import _ContreeBase

_PREPARATION_STATES = frozenset({ImageState.PREPARING, ImageState.PREPARED})

# Permitted stated transmissions
# from_state: to_states
_STATE_MACHINE = {
    ImageState.PULLED: _PREPARATION_STATES,
    ImageState.PREPARING: _PREPARATION_STATES,
    ImageState.PREPARED: frozenset({ImageState.EXECUTING}),
    ImageState.EXECUTING: frozenset({ImageState.SUCCEEDED}),
    ImageState.SUCCEEDED: _PREPARATION_STATES,
}


class _ImageLikeBase:
    uuid: UUID
    # todo think how to represent tag

    def __init__(self, client: _ContreeBase, uuid: UUID | str, tag: str | None):
        self.uuid: UUID | None = UUID(uuid)
        self.tag: str | None = tag
        self._client = client
        self._request: RunRequest | None = None
        self._raw_result: dict | None = None
        self._stdin = None
        self._stdout: str | None = None
        self._stderr: str | None = None
        self._state = ImageState.PULLED

    # command methods
    def command(self, command: str, /) -> Self:
        raise NotImplementedError

    def shell(self, command: str, /) -> Self:
        raise NotImplementedError

    # run arguments methods
    def args(self, *args: str) -> Self:
        raise NotImplementedError

    def stdin_from(self, stdin: IO_TYPES, /) -> Self:
        raise NotImplementedError

    def cwd(self, cwd, /) -> Self:
        raise NotImplementedError

    def env(self, env: dict = None, **envs) -> Self:
        raise NotImplementedError

    def stdout_to(self, stdout, /) -> Self:
        raise NotImplementedError

    def stderr_to(self, stderr, /) -> Self:
        raise NotImplementedError

    def use_tag(self, tag: str, /) -> Self:
        raise NotImplementedError

    # utils methods

    def _copy_self(self, clear=True) -> Self:
        # todo make an actual copy when developing chaining
        new_self = copy(self)
        if clear:
            new_self._stdout = new_self._stderr = new_self._raw_result = None
        return new_self

    def _process_self(self, new_self: Self) -> Self:
        # todo make an actual copy when developing chaining
        return new_self

    # main methods

    def run(
        self,
        command: str = None,
        shell: str = None,
        args: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdin: IO_TYPES | None = None,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec] | None = None,
    ) -> Self:
        if not self.uuid:
            raise ContreeImageParametersError
        new_self = self._copy_self()
        new_self._transition_state(ImageState.PREPARED)
        if shell is not None:
            command = shell

        new_self._request = RunRequest(
            command=command,
            args=list(args or []),
            shell=shell is not None,
            env=dict(env or {}),
            cwd=cwd or "/",
            tag=tag or None,  # todo use tag later
            stdin=stdin,
            files=self._prepare_files(files or []),
        )
        self._process_self(new_self)
        return new_self

    def _prepare_files(
        self,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec],
        default_image_path: str = "/",
    ) -> list[UploadFileSpec]:
        prepared = []
        if isinstance(files, dict):
            for image_path, file in files:
                if isinstance(file, UploadFileSpec):
                    item = replace(file, path=Path(image_path))
                else:
                    item = UploadFileSpec(
                        path=Path(image_path),
                        source=file,
                    )
                prepared.append(item)
            return prepared
        for file in files:
            if isinstance(file, UploadFileSpec):
                prepared.append(file)
            else:
                local_path = Path(file)
                image_path = Path(default_image_path) / local_path.name
                prepared.append(
                    UploadFileSpec(
                        path=Path(image_path),
                        source=local_path,
                    )
                )
        return prepared

    async def _prepare_files_for_api(self, files: list[UploadFileSpec]) -> dict[str, InstanceFileSpec]:
        async def _upload_file(file: UploadFileSpec) -> tuple[str, InstanceFileSpec]:
            if not isinstance(file.source, UploadedFile):
                file = replace(file, source=await self._client.files._upload_file(file.source))
            return str(file.path), InstanceFileSpec(
                uuid=file.source.uuid,
                mode=f"{file.mode:04o}",
                uid=file.uid,
                gid=file.gid,
            )

        return dict(await gather(*(_upload_file(i) for i in files)))

    def _prepare_stdin(self, stdin: IO_TYPES | None) -> StreamDescription:
        stdin = stdin or ""
        io_obj = get_io_by_obj(stdin, IOMode.read)
        self._stdin = io_obj
        return io_encode(io_obj.read())

    # internal methods

    def _can_transition(self, state: ImageState):
        possible_states = _STATE_MACHINE.get(self._state, set())
        if state not in possible_states:
            raise ContreeImageParametersError  # todo proper exceptions

    def _transition_state(self, state: ImageState):
        self._can_transition(state)
        self._state = state

    @property
    def state(self) -> ImageState:
        return self._state

    async def _await(self) -> Self:
        req = self._request
        self._transition_state(ImageState.EXECUTING)

        files, stdin = await gather(self._prepare_files_for_api(req.files), to_thread(self._prepare_stdin, req.stdin))
        operation_uuid = await self._client._api.spawn_instance(
            InstanceSpawnRequest(
                command=req.command,
                image=str(self.uuid),
                hostname="hostname",  # todo support it
                args=req.args,
                env=req.env,
                shell=req.shell,
                cwd=req.cwd,
                disposable=True,  # todo support disposables
                timeout=60,  # todo support timeout
                stdin=stdin,
                files=files,
            )
        )
        # todo move to unified operation awaiting
        finished = False
        while not finished:  # todo define timeouts
            resp = await self._client._api.get_instance_operation_status(operation_uuid)
            await sleep(0.1)  # todo to config
            # todo backoff
            finished = resp.status in (OperationStatus.FAILED, OperationStatus.SUCCESS, OperationStatus.CANCELLED)

        new_self = self._copy_self()
        new_self._transition_state(ImageState.SUCCEEDED)
        new_uuid = resp.result["image"]
        new_self.uuid = new_uuid and UUID(new_uuid)
        new_self.tag = None
        new_self._request = None
        new_self._raw_result = resp.metadata["result"]
        return new_self

    async def _ls(self, path: str = "/"):
        await self._client._api.list_image_files(self.uuid, path)
        # todo parse once inspect api is ready

    async def _files(self, path: str = "/"):
        pass

    def __repr__(self):
        other = ""
        if self.tag:
            other += f", tag={self.tag}"
        return f"{type(self).__name__}(uuid={self.uuid!r}, state={self.state!r}{other})"

    # result methods

    @property
    def stdin(self) -> IO | None:
        return self._stdin

    @property
    def stdout(self) -> str:
        if self._stdout is None:
            self._stdout = io_decode(**self._raw_result["stdout"])
        return self._stdout

    @property
    def stderr(self) -> str:
        if self._stderr is None:
            self._stderr = io_decode(**self._raw_result["stderr"])
        return self._stderr

    @property
    def exit_code(self) -> int:
        return int(self._raw_result["state"]["exit_code"])
