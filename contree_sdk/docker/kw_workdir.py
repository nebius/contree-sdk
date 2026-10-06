"""`WORKDIR /path` - set the working directory for subsequent directives."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import ClassVar

from .context import AsyncBuildContext, BuildContext
from .keyword import DockerKeyword


@dataclass(frozen=True, repr=False)
class WorkdirKeyword(DockerKeyword):
    NAME: ClassVar[str] = "WORKDIR"
    path: str = ""

    def __repr__(self) -> str:
        return f"WORKDIR {self.path}"

    @classmethod
    def parse(cls, args_text: str) -> WorkdirKeyword:
        raw = args_text.strip()
        if not raw:
            raise ValueError("WORKDIR requires a path")
        return cls(path=raw)

    def serialize(self) -> str:
        return f"WORKDIR {self.path}"

    def execute(self, ctx: BuildContext) -> None:
        target = ctx.substitute(self.path)
        if posixpath.isabs(target):
            ctx.workdir = posixpath.normpath(target)
        else:
            base = ctx.workdir or "/"
            ctx.workdir = posixpath.normpath(posixpath.join(base, target))

    async def execute_async(self, ctx: AsyncBuildContext) -> None:
        target = ctx.substitute(self.path)
        if posixpath.isabs(target):
            ctx.workdir = posixpath.normpath(target)
        else:
            base = ctx.workdir or "/"
            ctx.workdir = posixpath.normpath(posixpath.join(base, target))
