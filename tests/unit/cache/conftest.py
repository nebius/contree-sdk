from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from contree_sdk.cache import (
    AsyncCache,
    AsyncMemoryCache,
    AsyncSQLiteCache,
    SyncCache,
    SyncMemoryCache,
    SyncSQLiteCache,
)


@pytest.fixture(params=["memory", "sqlite"])
def sync_cache(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[SyncCache]:
    if request.param == "memory":
        yield SyncMemoryCache()
        return
    cache = SyncSQLiteCache(tmp_path / "cache.db")
    yield cache
    cache.close()


@pytest.fixture(params=["memory", "sqlite"])
async def async_cache(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[AsyncCache]:
    if request.param == "memory":
        yield AsyncMemoryCache()
        return
    cache = AsyncSQLiteCache(tmp_path / "cache.db")
    yield cache
    await cache.close()
