"""Parse and match `.dockerignore` rules against build-context paths.

Rules are matched in order against POSIX-style paths relative to the context
root. The last matching rule wins (`!` re-includes a previously ignored
path). Globs: `*` matches anything except `/`, `**` matches zero or more
path components, `?` matches one character, `[...]` is a character class.
Only a pattern containing `**` (explicit) crosses directory depth; a bare
pattern with no `/` at all (e.g. `secret.txt`) is anchored to the context
root, matching Docker's own documented `.dockerignore` behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DockerignoreRule:
    """One compiled `.dockerignore` line."""

    negate: bool
    regex: re.Pattern[str]
    raw: str


def parse_dockerignore(context_dir: Path) -> tuple[DockerignoreRule, ...]:
    path = context_dir / ".dockerignore"
    if not path.is_file():
        return ()
    rules: list[DockerignoreRule] = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        if negate:
            line = line[1:].strip()
        rules.append(DockerignoreRule(negate=negate, regex=ignored_pattern(line), raw=raw_line))
    return tuple(rules)


def is_ignored(rel_path: str, rules: tuple[DockerignoreRule, ...]) -> bool:
    # rules apply in order; the last match wins (negation re-includes)
    ignored = False
    for rule in rules:
        if rule.regex.fullmatch(rel_path):
            ignored = not rule.negate
    return ignored


def ignored_pattern(line: str) -> re.Pattern[str]:
    # trailing / = dir+contents, ** = any path depth, * = one segment, ? = one char, [...] = class
    is_dir = line.endswith("/")
    if is_dir:
        line = line.rstrip("/")
    line = line.lstrip("/")

    out: list[str] = []
    i = 0
    while i < len(line):
        match line[i : i + 3], line[i : i + 2], line[i]:
            case ("**/", _, _):
                out.append("(?:.*/)?")
                i += 3
            case (_, "**", _):
                out.append(".*")
                i += 2
            case (_, _, "*"):
                out.append("[^/]*")
                i += 1
            case (_, _, "?"):
                out.append("[^/]")
                i += 1
            case (_, _, "["):
                end = line.find("]", i + 1)
                if end == -1:
                    out.append(re.escape("["))
                    i += 1
                else:
                    out.append(line[i : end + 1])
                    i = end + 1
            case (_, _, "/"):
                out.append("/")
                i += 1
            case (_, _, ch):
                out.append(re.escape(ch))
                i += 1

    regex = "".join(out)
    if is_dir:
        regex += "(?:/.*)?"
    return re.compile(regex)
