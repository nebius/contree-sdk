"""Collect standalone scripts and reject examples without embedded tests."""

from fnmatch import fnmatch
from pathlib import Path

import pytest


class ExampleModule(pytest.Module):
    def collect(self):
        items = list(super().collect())
        if not items:
            raise self.CollectError(f"{self.path}: add a test_ function to this example")
        return items


def pytest_collect_file(file_path: Path, parent: pytest.Collector):
    if file_path.suffix != ".py" or file_path.name in {"conftest.py", "__init__.py"}:
        return None
    # Let pytest collect conventional test filenames without a duplicate item.
    if any(fnmatch(file_path.name, pattern) for pattern in parent.config.getini("python_files")):
        return None
    return ExampleModule.from_parent(parent, path=file_path)


def pytest_pycollect_makemodule(module_path: Path, parent: pytest.Collector):
    return ExampleModule.from_parent(parent, path=module_path)
