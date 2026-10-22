import inspect
from pathlib import Path

import pytest

from contree_sdk.store import AsyncMemoryStore, AsyncSQLiteStore, SyncMemoryStore, SyncSQLiteStore


@pytest.fixture(params=["memory", "sqlite", "async-memory", "async-sqlite"])
async def cache_case(request: pytest.FixtureRequest, tmp_path: Path):
    now = [1000.0]
    factories = {
        "memory": lambda: SyncMemoryStore(clock=lambda: now[0]),
        "sqlite": lambda: SyncSQLiteStore(tmp_path / "cache.db", clock=lambda: now[0]),
        "async-memory": lambda: AsyncMemoryStore(clock=lambda: now[0]),
        "async-sqlite": lambda: AsyncSQLiteStore(tmp_path / "cache.db", clock=lambda: now[0]),
    }
    cache = factories[request.param]()
    yield cache, now
    result = cache.close()
    if inspect.isawaitable(result):
        await result
