"""`ENV KEY=VALUE [KEY=VALUE ...]` - set persistent environment variables."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from .context import AsyncBuildContext, BuildContext
from .keyword import DockerKeyword, parse_keyval_pairs


@dataclass(frozen=True, repr=False)
class EnvKeyword(DockerKeyword):
    NAME: ClassVar[str] = "ENV"
    pairs: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def __repr__(self) -> str:
        return "ENV " + " ".join(f"{key}={value}" for key, value in self.pairs)

    @classmethod
    def parse(cls, args_text: str) -> EnvKeyword:
        raw = args_text.strip()
        if not raw:
            raise ValueError("ENV requires KEY=VALUE")
        pairs = parse_keyval_pairs(raw)
        return cls(pairs=tuple(pairs.items()))

    def serialize(self) -> str:
        return "ENV " + " ".join(f"{key}={value}" for key, value in self.pairs)

    def execute(self, ctx: BuildContext) -> None:
        for key, value in self.pairs:
            ctx.env[key] = ctx.substitute(value)

    async def execute_async(self, ctx: AsyncBuildContext) -> None:
        for key, value in self.pairs:
            ctx.env[key] = ctx.substitute(value)
