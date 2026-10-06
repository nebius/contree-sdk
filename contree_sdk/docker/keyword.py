"""Base class for Dockerfile keywords plus shared helpers."""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar


if TYPE_CHECKING:
    from contree_sdk.docker.context import AsyncBuildContext, BuildContext


SUB_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def substitute(text: str, env: dict[str, str]) -> str:
    # expand $VAR / ${VAR} against env; missing names expand to ""
    def repl(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return env.get(name, "")

    return SUB_RE.sub(repl, text)


def parse_command_form(rest: str) -> tuple[list[str], bool]:
    # returns (parts, shell_form): shell-form is a single-element list, exec-form is JSON
    stripped = rest.lstrip()
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
        except ValueError as exc:
            raise ValueError(f"invalid JSON exec-form: {rest!r}") from exc
        if not isinstance(parsed, list) or not all(isinstance(part, str) for part in parsed):
            raise ValueError(f"exec-form must be a list of strings: {rest!r}")
        parts: list[str] = parsed
        return parts, False
    return [rest], True


def parse_keyval_pairs(rest: str) -> dict[str, str]:
    # KEY1=VAL1 KEY2=VAL2 ... or the legacy two-token KEY VALUE form
    tokens = shlex.split(rest)
    if not tokens:
        return {}
    if "=" not in tokens[0]:
        split = rest.split(None, 1)
        value = split[1] if len(split) > 1 else ""
        return {tokens[0]: value.strip()}
    pairs: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"expected KEY=VALUE, got {token!r}")
        key, _, value = token.partition("=")
        pairs[key] = value
    return pairs


@dataclass(frozen=True, repr=False)
class DockerKeyword:
    """Base class. Subclasses implement `parse`, `serialize`, `execute`."""

    NAME: ClassVar[str] = ""

    @classmethod
    def parse(cls, args_text: str) -> DockerKeyword:
        raise NotImplementedError

    def serialize(self) -> str:
        """Stable text used for layer hashing."""
        raise NotImplementedError

    def execute(self, ctx: BuildContext) -> None:
        raise NotImplementedError

    async def execute_async(self, ctx: AsyncBuildContext) -> None:
        raise NotImplementedError

    def __repr__(self) -> str:
        return self.NAME or self.__class__.__name__
