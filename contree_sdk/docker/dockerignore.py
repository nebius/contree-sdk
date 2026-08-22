"""Parse and match `.dockerignore` rules against build-context paths.

Rules are matched in order against POSIX-style paths relative to the context
root. The last matching rule wins (`!` re-includes a previously ignored
path). Globs: `*` matches anything except `/`, `**` matches zero or more
path components, `?` matches one character, `[...]` is a character class.
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
        regex_str = pattern_to_regex(line)
        rules.append(DockerignoreRule(negate=negate, regex=re.compile(regex_str), raw=raw_line))
    return tuple(rules)


def is_ignored(rel_path: str, rules: tuple[DockerignoreRule, ...]) -> bool:
    # rules apply in order; the last match wins (negation re-includes)
    ignored = False
    for rule in rules:
        if rule.regex.fullmatch(rel_path):
            ignored = not rule.negate
    return ignored


def pattern_to_regex(pattern: str) -> str:
    # trailing / = dir+contents, ** = any path depth, * = one segment, ? = one char, [...] = class
    is_dir = pattern.endswith("/")
    if is_dir:
        pattern = pattern.rstrip("/")
    pattern = pattern.lstrip("/")

    out: list[str] = []
    i = 0
    while i < len(pattern):
        match pattern[i : i + 3], pattern[i : i + 2], pattern[i]:
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
                end = pattern.find("]", i + 1)
                if end == -1:
                    out.append(re.escape("["))
                    i += 1
                else:
                    out.append(pattern[i : end + 1])
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
    return regex
