"""Expand Dockerfile variables without depending on build contracts."""

import re


SUB_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def substitute(text: str, env: dict[str, str]) -> str:
    # expand $VAR / ${VAR} against env; missing names expand to ""
    def repl(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return env.get(name, "")

    return SUB_RE.sub(repl, text)
