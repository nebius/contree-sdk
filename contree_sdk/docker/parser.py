"""Parse a Dockerfile into a list of `DockerKeyword` instances."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path

from .keyword import DockerKeyword
from .kw_add import AddKeyword
from .kw_arg import ArgKeyword
from .kw_copy import CopyKeyword
from .kw_env import EnvKeyword
from .kw_from import FromKeyword
from .kw_run import RunKeyword
from .kw_skipped import SkippedKeyword
from .kw_user import UserKeyword
from .kw_workdir import WorkdirKeyword


KEYWORDS: dict[str, type[DockerKeyword]] = {
    "FROM": FromKeyword,
    "RUN": RunKeyword,
    "COPY": CopyKeyword,
    "ADD": AddKeyword,
    "WORKDIR": WorkdirKeyword,
    "ENV": EnvKeyword,
    "ARG": ArgKeyword,
    "USER": UserKeyword,
}


SKIPPED_NAMES = frozenset({
    "CMD",
    "ENTRYPOINT",
    "LABEL",
    "EXPOSE",
    "VOLUME",
    "STOPSIGNAL",
    "MAINTAINER",
    "HEALTHCHECK",
    "ONBUILD",
    "SHELL",
})


class DockerfileParser:
    """A per-instance directive registry. Subclass or register custom DockerKeyword classes."""

    def __init__(
        self, *, keywords: Mapping[str, type[DockerKeyword]] | None = None, skipped: Iterable[str] | None = None
    ) -> None:
        self.keywords = dict(KEYWORDS if keywords is None else keywords)
        self.skipped = set(SKIPPED_NAMES if skipped is None else skipped)

    def register(self, keyword: type[DockerKeyword]) -> None:
        name = keyword.NAME.upper()
        if not name or any(char.isspace() for char in name):
            raise ValueError("keyword NAME must be a non-empty token")
        self.keywords[name] = keyword
        self.skipped.discard(name)

    def parse(self, text: str) -> list[DockerKeyword]:
        """Return directives using this parser's registry.

        Returns:
            The parsed directives in source order.

        Raises:
            ValueError: A directive is unknown or has invalid arguments.

        """
        result: list[DockerKeyword] = []
        for raw in join_continuations(text):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(maxsplit=1)
            head = parts[0].upper()
            rest = parts[1] if len(parts) > 1 else ""
            if head in self.keywords:
                result.append(self.keywords[head].parse(rest))
            elif head in self.skipped:
                result.append(SkippedKeyword.of(head, rest))
            else:
                raise ValueError(f"unknown Dockerfile directive: {head!r}")
        return result


def parse_dockerfile(text: str) -> list[DockerKeyword]:
    return DockerfileParser().parse(text)


def join_continuations(text: str) -> list[str]:
    # merge lines ending with a backslash into single logical lines
    out: list[str] = []
    buf: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.endswith("\\"):
            buf.append(line[:-1])
            continue
        if buf:
            buf.append(line)
            out.append(" ".join(part.strip() for part in buf))
            buf = []
        else:
            out.append(line)
    if buf:
        out.append(" ".join(part.strip() for part in buf))
    return out


def validate_first_directive(directives: list[DockerKeyword]) -> bool:
    for directive in directives:
        if isinstance(directive, FromKeyword):
            return True
        if isinstance(directive, ArgKeyword):
            continue
        return False
    return False


def make_session_key(context_dir: Path) -> str:
    digest = hashlib.sha256(str(context_dir).encode()).hexdigest()
    return f"build:{digest[:16]}"
