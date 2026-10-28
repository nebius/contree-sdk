"""A server may delete any cached upload or intermediate image between builds."""

import asyncio
from contextlib import asynccontextmanager, contextmanager

import pytest

from contree_sdk.docker import ContreeAsyncDockerBuilder, ContreeDockerBuilder
from contree_sdk.store import AsyncMemoryStore, AsyncSQLiteStore, SyncMemoryStore, SyncSQLiteStore
from tests.unit.docker.copy_clients import CopyAsyncClient, CopyClient
from tests.unit.docker.retention_server import RetentionServer


DOCKERFILE = """FROM base AS source
COPY input /seed
RUN compile
RUN source-extra
FROM base AS runtime
COPY config /config
RUN prepare
COPY --from=source /out /app
COPY --from=source /out/tool /bin/tool
RUN finish
"""


@pytest.fixture(params=["sync-memory", "async-memory", "sync-sqlite", "async-sqlite"])
def retained_build(request, tmp_path, monkeypatch):
    asynchronous = request.param.startswith("async")
    persistent = request.param.endswith("sqlite")
    client = CopyAsyncClient() if asynchronous else CopyClient()
    server = RetentionServer()
    server.install(client, monkeypatch)
    memory = AsyncMemoryStore() if asynchronous else SyncMemoryStore()
    database = tmp_path / "cache.sqlite3"
    (tmp_path / "Dockerfile").write_text(DOCKERFILE)
    (tmp_path / "input").write_bytes(b"source")
    (tmp_path / "config").write_bytes(b"config")

    @contextmanager
    def sync_store():
        if persistent:
            with SyncSQLiteStore(database) as store:
                yield store
        else:
            yield memory

    @asynccontextmanager
    async def async_store():
        if persistent:
            async with AsyncSQLiteStore(database) as store:
                yield store
        else:
            yield memory

    def build_sync(**kwargs):
        assert isinstance(client, CopyClient)
        with sync_store() as store:
            return ContreeDockerBuilder(client, store=store, **kwargs).build(tmp_path, session_id="retention")

    async def rebuild(**kwargs):
        if isinstance(client, CopyAsyncClient):
            async with async_store() as store:
                return await ContreeAsyncDockerBuilder(client, store=store, **kwargs).build(
                    tmp_path, session_id="retention"
                )
        return await asyncio.to_thread(build_sync, **kwargs)

    return server, client, rebuild


EVICTIONS = (
    [(layer, None) for layer in range(1, 6)]
    + [(None, file) for file in range(1, 5)]
    + [(layer, file) for layer in range(1, 6) for file in range(1, 5)]
    + [("all", None), (None, "all"), ("all", "all")]
)


@pytest.mark.parametrize(("layer", "file"), EVICTIONS)
async def test_rebuild_after_retention_of_each_layer_and_upload(retained_build, layer, file):
    server, client, rebuild = retained_build
    first = await rebuild()
    expected = dict(server.images[first])
    assert expected["/result"] == b"compiled:sourcecompiled:source"
    assert len(client.calls_for("spawn_instance")) == 5
    assert len(server.files) == 4
    if layer == "all":
        server.images = {"base": {}}
    elif layer is not None:
        del server.images[f"image-op-{layer}"]
    if file == "all":
        server.files.clear()
    elif file is not None:
        del server.files[f"upload-{file}"]
    second = await rebuild()
    assert server.images[second] == expected
    assert not server.missing_requests
    new_spawns = len(client.calls_for("spawn_instance")) - 5
    assert new_spawns == ({None: 0, 1: 4, 2: 3, 3: 3, 4: 2, 5: 1, "all": 5}[layer])
    needs_archive = layer not in {None, 5}
    replaced_uploads = (
        3 + int(needs_archive) if file == "all" else int(file is not None and (file != 3 or needs_archive))
    )
    assert server.upload_sequence == 4 + replaced_uploads
    uploads = server.upload_sequence
    transfers = len(client.calls_for("ensure_file"))
    spawns = len(client.calls_for("spawn_instance"))
    assert await rebuild() == second
    assert len(client.calls_for("spawn_instance")) == spawns
    assert server.upload_sequence == uploads
    assert len(client.calls_for("ensure_file")) == transfers


@pytest.mark.parametrize("keyword", ["COPY", "ADD"])
async def test_local_file_retention_before_rebuilding_its_layer(retained_build, tmp_path, keyword):
    server, client, rebuild = retained_build
    (tmp_path / "Dockerfile").write_text(f"FROM base\n{keyword} input /input\nRUN consume\n")
    first = await rebuild()
    original_file = next(iter(server.files))
    del server.files[original_file]
    del server.images[first]
    result = await rebuild()
    assert server.images[result]["/input"] == b"source"
    assert original_file != client.calls_for("spawn_instance")[-1].kwargs["files"]["/input"].uuid
    assert server.upload_sequence == 2
    assert not server.missing_requests


@pytest.mark.parametrize("honor_conditional", [False, True], ids=["etag-200", "not-modified-304"])
async def test_url_upload_retention_refetches_body(retained_build, tmp_path, honor_conditional):
    server, client, rebuild = retained_build
    (tmp_path / "Dockerfile").write_text("FROM base\nADD https://example.test/input /url\nRUN consume\n")
    headers_seen = []

    def fetch(url, method, headers):
        headers_seen.append(dict(headers))
        status = 304 if honor_conditional and dict(headers).get("If-None-Match") else 200
        return status, [("ETag", '"v1"')], [] if status == 304 else [b"remote"]

    async def fetch_async(url, method, headers):
        status, metadata, chunks = fetch(url, method, headers)

        async def body():
            for chunk in chunks:
                yield chunk

        return status, metadata, body()

    kwargs = {"http_fetch_async": fetch_async} if isinstance(client, CopyAsyncClient) else {"http_fetch": fetch}
    first = await rebuild(**kwargs)
    server.files.clear()
    del server.images[first]
    second = await rebuild(**kwargs)
    assert server.images[second]["/url"] == b"remote"
    assert server.upload_sequence == 2
    assert not headers_seen[1]
    assert not server.missing_requests
    spawns = len(client.calls_for("spawn_instance"))
    assert await rebuild(**kwargs) == second
    assert headers_seen[-1] == {"If-None-Match": '"v1"'}
    assert server.upload_sequence == 2
    assert len(client.calls_for("spawn_instance")) == spawns
