"""Parse a Dockerfile into a list of `DockerKeyword` instances."""

from __future__ import annotations

import hashlib
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


def parse_dockerfile(text: str) -> list[DockerKeyword]:
    # joins backslash-continued lines, drops comment/blank lines, then dispatches by leading keyword
    merged = join_continuations(text)
    result: list[DockerKeyword] = []
    for raw in merged:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        head, _, rest = line.partition(" ")
        keyword = head.upper()
        if keyword in KEYWORDS:
            result.append(KEYWORDS[keyword].parse(rest))
        elif keyword in SKIPPED_NAMES:
            result.append(SkippedKeyword.of(keyword, rest))
        else:
            raise ValueError(f"unknown Dockerfile directive: {head!r}")
    return result


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
