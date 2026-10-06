from pathlib import Path

import pytest


pytest_plugins = ["tests.docs_fixtures"]


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    if collection_path.name in {"_build", "_autosummary", "_tmp"}:
        return True
    return None


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.suffix in {".md", ".markdown"}:
            item.add_marker(pytest.mark.markdown)
