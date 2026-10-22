import os

import pytest
from contree_client.asyncio import ContreeAsyncClient
from contree_client.models import StreamRepr
from contree_client.sync import ContreeClient

from contree_sdk.session import ContreeAsyncSession, ContreeSession
from contree_sdk.store import AsyncSQLiteStore, SyncSQLiteStore


@pytest.fixture
def image() -> str:
    image = os.getenv("CONTREE_E2E_IMAGE")
    if not image:
        pytest.skip("Set CONTREE_E2E_IMAGE to a shell-capable image and configure a ConTree profile")
    return image


def test_files_branching_and_persistent_resume(image, tmp_path):
    store = SyncSQLiteStore(tmp_path / "sessions.db")
    try:
        with ContreeClient.from_profile() as client:
            session = ContreeSession(client, image=image, store=store, session_id="test")
            result = session.run(
                shell="cat /contree-test-input", files={"/contree-test-input": b"first"}, disposable=False
            )
            assert isinstance(result.stdout, StreamRepr)
            assert result.stdout.as_bytes() == b"first"
            session.create_branch("experiment")
            session.switch_branch("experiment")
            session.run(shell="echo second > /contree-test-input", disposable=False)
            session.switch_branch("main")
            assert client.inspect_image_download(session.image_uuid, "/contree-test-input") == b"first"
            store.close()
            store = SyncSQLiteStore(tmp_path / "sessions.db")
            resumed = ContreeSession(client, store=store, session_id="test")
            assert resumed.image_uuid == session.image_uuid
    finally:
        store.close()


async def test_async_files_branching_and_persistent_resume(image, tmp_path):
    store = AsyncSQLiteStore(tmp_path / "sessions.db")
    try:
        async with ContreeAsyncClient.from_profile() as client:
            session = ContreeAsyncSession(client, image=image, store=store, session_id="test")
            result = await session.run(
                shell="cat /contree-test-input", files={"/contree-test-input": b"first"}, disposable=False
            )
            assert isinstance(result.stdout, StreamRepr)
            assert result.stdout.as_bytes() == b"first"
            await session.create_branch("experiment")
            await session.switch_branch("experiment")
            await session.run(shell="echo second > /contree-test-input", disposable=False)
            await session.switch_branch("main")
            assert session.image_uuid is not None
            assert await client.inspect_image_download(session.image_uuid, "/contree-test-input") == b"first"
            await store.close()
            store = AsyncSQLiteStore(tmp_path / "sessions.db")
            resumed = ContreeAsyncSession(client, store=store, session_id="test")
            await resumed.ensure_ready()
            assert resumed.image_uuid == session.image_uuid
    finally:
        await store.close()
