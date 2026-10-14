"""Dockerfile command parsing and public directive exports."""

from __future__ import annotations

import json
import shlex

from .context import DockerKeyword
from .interpolation import substitute


__all__ = ["DockerKeyword", "parse_command_form", "parse_keyval_pairs", "substitute"]


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
