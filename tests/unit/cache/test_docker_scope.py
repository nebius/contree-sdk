"""Docker file and layer reuse must stay within its server scope."""

import pytest
from contree_client.models import FileResponse
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk.cache import AsyncCache, AsyncMemoryCache, SyncMemoryCache
from contree_sdk.docker import ContreeAsyncDockerBuilder, ContreeDockerBuilder
from contree_sdk.docker.context import AsyncBuildContext, BuildContext
from contree_sdk.docker.kw_add import fetch_url, fetch_url_async
from contree_sdk.docker.kw_copy import upload_files, upload_files_async
from contree_sdk.docker.local_context import LocalContext
from contree_sdk.exceptions import DockerBuildError
from contree_sdk.store import AsyncMemoryStore, SyncMemoryStore
from tests.unit.cache.test_upload_cache import call
from tests.unit.session.factories import mock_completion, operation_response, spawn_response


def context(cache, tmp_path):
    if isinstance(cache, AsyncCache):
        return AsyncBuildContext(
            client=ContreeAsyncClient(),
            cache=cache,
            store=AsyncMemoryStore(),
            local=LocalContext(tmp_path),
            upload_cache_ttl=10,
        )
    return BuildContext(
        client=ContreeClient(),
        cache=cache,
        store=SyncMemoryStore(),
        local=LocalContext(tmp_path),
        upload_cache_ttl=10,
    )


def builder_for(client, store, cache):
    if isinstance(client, ContreeAsyncClient):
        return ContreeAsyncDockerBuilder(client, store=store, cache=cache)
    return ContreeDockerBuilder(client, store=store, cache=cache)


async def test_copy_expiry_and_source_records(cache_case, tmp_path):
    cache, now = cache_case
    ctx = context(cache, tmp_path)
    client = ctx.client
    client.mock("ensure_file", FileResponse(uuid="file", sha256="hash", size=4))
    path = tmp_path / "file"
    path.write_bytes(b"data")
    mapped = ctx.local.collect(("file",), "/file", uid=0, gid=0, mode_override=None)

    async def upload():
        if isinstance(ctx, AsyncBuildContext):
            return await upload_files_async(ctx, mapped)
        return upload_files(ctx, mapped)

    await upload()
    now[0] += 9
    await upload()
    assert len(client.calls_for("ensure_file")) == 1
    now[0] += 1
    await upload()
    assert len(client.calls_for("ensure_file")) == 2
    assert (await call(ctx.file_sources, "sources", "file"))[0].source == str(path)


async def test_url_304_does_not_extend_upload_lifetime(cache_case, tmp_path):
    cache, now = cache_case
    ctx = context(cache, tmp_path)
    client = ctx.client
    client.mock("ensure_file", FileResponse(uuid="file", sha256="hash", size=4))
    statuses = iter([200, 304, 304, 503])
    request_headers = []

    def fetch(url, method, headers):
        request_headers.append(list(headers))
        return next(statuses), [("ETag", "etag")], iter([b"data"])

    async def fetch_async(url, method, headers):
        status, response_headers, chunks = fetch(url, method, headers)

        async def body():
            for chunk in chunks:
                yield chunk

        return status, response_headers, body()

    if isinstance(ctx, AsyncBuildContext):
        ctx.http_fetch_async = fetch_async
    else:
        ctx.http_fetch = fetch
    url = "https://example.invalid/file"

    async def upload():
        if isinstance(ctx, AsyncBuildContext):
            return await fetch_url_async(ctx, url)
        return fetch_url(ctx, url)

    first = await upload()
    now[0] += 9
    assert await upload() == first
    assert request_headers[-1] == [("If-None-Match", "etag")]
    now[0] += 1
    with pytest.raises(DockerBuildError, match="304"):
        await upload()
    assert request_headers[-1] == []
    with pytest.raises(DockerBuildError, match="503"):
        await upload()
    assert len(client.calls_for("ensure_file")) == 1
    assert (await call(ctx.file_sources, "sources", "file"))[0].source == url


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_shared_layer_store_does_not_reuse_another_server_image(tmp_path, asynchronous):
    (tmp_path / "Dockerfile").write_text("FROM tag:base\nCOPY file /file\nRUN true\n")
    (tmp_path / "file").write_bytes(b"data")
    store = AsyncMemoryStore() if asynchronous else SyncMemoryStore()
    cache = AsyncMemoryCache() if asynchronous else SyncMemoryCache()
    for endpoint in ("https://one.invalid", "https://two.invalid"):
        client = (ContreeAsyncClient if asynchronous else ContreeClient)(base_url=endpoint)
        client.mock("resolve_image", "same-base-uuid")
        client.mock("ensure_file", FileResponse(uuid="file", sha256="hash", size=4))
        client.mock("spawn_instance", spawn_response())
        mock_completion(client, operation_response(result_image_uuid="result", exit_code=0))
        builder = builder_for(client, store, cache)
        assert await call(builder, "build", tmp_path, session_id="shared") == "result"
        assert len(client.calls_for("spawn_instance")) == 1
        assert len(client.calls_for("ensure_file")) == 1
