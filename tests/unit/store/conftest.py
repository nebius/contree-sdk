from pathlib import Path

import pytest

from contree_sdk.store import MemoryStore, SQLiteStore, Store


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Store:
    if request.param == "memory":
        return MemoryStore()
    return SQLiteStore(tmp_path / "sessions.db")
