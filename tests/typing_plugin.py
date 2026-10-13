"""Collect *_typing.toml scenarios and check their types with ty."""

import json
import subprocess
import sys
from functools import partial
from pathlib import Path
from typing import Any

import pytest


def pytest_collect_file(file_path: Path, parent: pytest.Collector) -> pytest.File | None:
    if file_path.name.endswith("_typing.toml"):
        return TypingFile.from_parent(parent, path=file_path)
    return None


class TypingFile(pytest.File):
    def collect(self):
        tomllib = pytest.importorskip("tomllib")
        scenarios = tomllib.loads(self.path.read_text())
        for case in scenarios["cases"]:
            yield pytest.Function.from_parent(
                self,
                name=case["name"],
                callobj=partial(check_types, self.config.rootpath, scenarios.get("imports", ""), case),
            )


def check_types(root: Path, imports: str, case: dict[str, Any], tmp_path: Path) -> None:
    path = tmp_path / "scenario.py"
    path.write_text(imports + case["code"])
    result = subprocess.run(  # noqa: S603 - fixed checker and locally generated Python input
        [
            sys.executable,
            "-m",
            "ty",
            "check",
            "--project",
            str(root),
            "--extra-search-path",
            str(root),
            "--output-format",
            "gitlab",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    expected = case.get("errors", [])
    if result.returncode != bool(expected):
        pytest.fail(result.stdout + result.stderr, pytrace=False)
    diagnostics = json.loads(result.stdout)
    actual = [
        {
            "line": item["location"]["positions"]["begin"]["line"] - imports.count("\n"),
            "code": item["check_name"],
        }
        for item in diagnostics
    ]
    if actual != expected:
        pytest.fail(f"Expected diagnostics: {expected}\nActual diagnostics: {actual}\n{result.stdout}", pytrace=False)
