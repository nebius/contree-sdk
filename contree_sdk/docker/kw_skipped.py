"""Keywords that are recognised but not implemented (CMD, LABEL, EXPOSE, ...)."""

from __future__ import annotations

from dataclasses import dataclass

from .context import AsyncBuildContext, BuildContext
from .keyword import DockerKeyword


@dataclass(frozen=True, repr=False)
class SkippedKeyword(DockerKeyword):
    name: str = ""
    raw: str = ""

    def __repr__(self) -> str:
        return f"{self.name} {self.raw}".rstrip()

    @classmethod
    def of(cls, name: str, raw: str) -> SkippedKeyword:
        return cls(name=name.upper(), raw=raw)

    def serialize(self) -> str:
        return f"{self.name}:{self.raw}"

    def execute(self, ctx: BuildContext) -> None:  # noqa: PLR6301
        del ctx  # no-op: recognised but has no effect on the build

    async def execute_async(self, ctx: AsyncBuildContext) -> None:  # noqa: PLR6301
        del ctx
