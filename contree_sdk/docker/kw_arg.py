"""`ARG NAME[=DEFAULT]` - declare a build-time variable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .context import AsyncBuildContext, BuildContext
from .keyword import DockerKeyword


@dataclass(frozen=True, repr=False)
class ArgKeyword(DockerKeyword):
    NAME: ClassVar[str] = "ARG"
    name: str = ""
    default: str | None = None

    def __repr__(self) -> str:
        if self.default is None:
            return f"ARG {self.name}"
        return f"ARG {self.name}={self.default}"

    @classmethod
    def parse(cls, args_text: str) -> ArgKeyword:
        raw = args_text.strip()
        if not raw:
            raise ValueError("ARG requires a name")
        if "=" in raw:
            name, _, default = raw.partition("=")
            return cls(name=name.strip(), default=default.strip())
        return cls(name=raw, default=None)

    def serialize(self) -> str:
        if self.default is None:
            return f"ARG {self.name}"
        return f"ARG {self.name}={self.default}"

    def execute(self, ctx: BuildContext) -> None:
        ctx.declared_args.add(self.name)
        if self.default is not None and self.name not in ctx.arg_defaults:
            ctx.arg_defaults[self.name] = ctx.substitute(self.default)

    async def execute_async(self, ctx: AsyncBuildContext) -> None:
        ctx.declared_args.add(self.name)
        if self.default is not None and self.name not in ctx.arg_defaults:
            ctx.arg_defaults[self.name] = ctx.substitute(self.default)
