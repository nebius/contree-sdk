import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from contree_sdk.exceptions import SessionConflictError
from contree_sdk.store import AsyncSQLiteStore, SyncSQLiteStore


def test_sqlite_connections_cannot_overwrite_the_same_tip(tmp_path):
    stores = [SyncSQLiteStore(tmp_path / "history.db") for _ in range(2)]
    try:
        root = stores[0].append("s", image_uuid="base", parent_id=None)
        barrier = Barrier(2)

        def commit(index):
            barrier.wait(timeout=5)
            try:
                return stores[index].append("s", image_uuid=f"image-{index}", parent_id=root.id, expected_tip=root.id)
            except SessionConflictError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(commit, index) for index in range(2)]
            results = [future.result(timeout=5) for future in futures]
        assert sum(result is not None for result in results) == 1
        entries, _ = stores[0].history_dag("s")
        assert len(entries) == 2
        assert stores[1].tip("s") == entries[-1]
    finally:
        for store in stores:
            store.close()


async def test_async_sqlite_connections_cannot_overwrite_the_same_tip(tmp_path):
    stores = [AsyncSQLiteStore(tmp_path / "history.db") for _ in range(2)]
    try:
        root = await stores[0].append("s", image_uuid="base", parent_id=None)
        await stores[1].ensure_connection()
        results = await asyncio.gather(
            *(
                store.append("s", image_uuid=f"image-{i}", parent_id=root.id, expected_tip=root.id)
                for i, store in enumerate(stores)
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(result, SessionConflictError) for result in results) == 1
        entries, _ = await stores[0].history_dag("s")
        assert len(entries) == 2
        assert await stores[1].tip("s") == entries[-1]
    finally:
        for store in stores:
            await store.close()
