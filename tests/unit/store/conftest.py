from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from contree_sdk.store import (
    AsyncMemoryStore,
    AsyncSQLiteStore,
    AsyncStore,
    SyncMemoryStore,
    SyncSQLiteStore,
    SyncStore,
)


@pytest.fixture(params=["memory", "sqlite"])
def sync_store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[SyncStore]:
    if request.param == "memory":
        yield SyncMemoryStore()
        return
    store = SyncSQLiteStore(tmp_path / "sessions.db")
    yield store
    store.close()


@pytest.fixture(params=["memory", "sqlite"])
async def async_store(request: pytest.FixtureRequest, tmp_path: Path) -> AsyncIterator[AsyncStore]:
    if request.param == "memory":
        yield AsyncMemoryStore()
        return
    store = AsyncSQLiteStore(tmp_path / "sessions.db")
    yield store
    await store.close()
