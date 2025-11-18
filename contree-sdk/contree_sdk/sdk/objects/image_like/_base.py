from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Self
from uuid import UUID


if TYPE_CHECKING:
    from contree_sdk.sdk.client.base import _ContreeBase


class _ImageLikeBase:
    uuid: UUID

    def __init__(self, client: _ContreeBase, uuid: UUID):
        self.uuid = uuid
        self._client = client

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

    def env(self, env: dict = None, **envs) -> Self:
        raise NotImplementedError

    def stdout_to(self, stdout, /) -> Self:
        raise NotImplementedError

    def stderr_to(self, stderr, /) -> Self:
        raise NotImplementedError

    # main methods

    def run(
        self,
        command: str = None,
        shell: str = None,
        args: Iterable[str] = None,
        env: dict = None,
    ) -> Self:
        raise NotImplementedError

    # internal methods

    async def _await(self):
        raise NotImplementedError
