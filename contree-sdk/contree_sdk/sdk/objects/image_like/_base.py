from __future__ import annotations

from asyncio import sleep
from collections.abc import Iterable
from copy import copy
from typing import TYPE_CHECKING, Self
from uuid import UUID

from contree_sdk.api.models.instance import InstanceSpawnRequest, OperationStatus
from contree_sdk.sdk.exceptions.image import ContreeImageParametersError
from contree_sdk.sdk.objects.run import RunRequest
from contree_sdk.utils.codecs import io_decode


if TYPE_CHECKING:
    from contree_sdk.sdk.client.base import _ContreeBase


class _ImageLikeBase:
    uuid: UUID
    # todo think how to represent tag

    def __init__(self, client: _ContreeBase, uuid: UUID | str, tag: str | None):
        self.uuid: UUID | None = UUID(uuid)
        self.tag: str | None = tag
        self._client = client
        self._request: RunRequest | None = None
        self._raw_result: dict | None = None
        self._stdout: str | None = None
        self._stderr: str | None = None

    # command methods
    def command(self, command: str, /) -> Self:
        raise NotImplementedError

    def shell(self, command: str, /) -> Self:
        raise NotImplementedError

    # run arguments methods
    def args(self, *args: str) -> Self:
        raise NotImplementedError

    def stdin(self, stdin, /) -> Self:
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
        stdin: str | None = None,
        tag: str | None = None,
    ) -> Self:
        if not self.uuid:
            raise ContreeImageParametersError
        new_self = self._copy_self()
        if shell is not None:
            command = shell

        new_self._request = RunRequest(
            command=command,
            args=list(args or []),
            shell=shell is not None,
            env=dict(env or {}),
            cwd=cwd or "/",  # todo replace to ~, once supported
            tag=tag or None,  # todo use tag later
        )
        self._process_self(new_self)
        return new_self

    # internal methods

    async def _await(self) -> Self:
        req = self._request

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
            )
        )
        finished = False
        while not finished:  # todo define timeouts
            resp = await self._client._api.get_instance_operation_status(operation_uuid)
            await sleep(0.1)  # todo to config
            # todo backoff
            finished = resp.status in (OperationStatus.FAILED, OperationStatus.SUCCESS, OperationStatus.CANCELLED)

        new_self = self._copy_self()
        new_uuid = resp.result["image"]
        new_self.uuid = new_uuid and UUID(new_uuid)
        new_self.tag = None
        new_self._request = None
        new_self._raw_result = resp.metadata["result"]
        return new_self

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
