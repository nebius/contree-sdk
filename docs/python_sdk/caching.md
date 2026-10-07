# Reuse uploads and retain their sources

Use `CachedFileTransfer` or `AsyncCachedFileTransfer` to reuse uploads by content.
Pass an explicit lifetime in seconds. A cache hit does not extend that lifetime.
Choose a lifetime shorter than the server's upload retention period. The cache
cannot detect uploads removed from the server before expiry; invalidate them
explicitly when necessary.

## Reuse local files across commands

The transfer creates a temporary copy while hashing a local file in chunks. It
uploads that copy, so later changes to the source cannot change the bytes associated
with the fingerprint. Temporary copies are removed after success, failure, or
cancellation. Concurrent misses can upload the same content more than once.

This example attaches the same local input to two commands. The second command
reuses its uploaded UUID. Each request still supplies its own destination and
permissions. Set the environment variables described in {doc}`getting-started`.

::::{tab} Sync

<!--
name: test_cached_upload; fixtures: doc_api
```python
doc_api.complete()
doc_api.complete()
```
-->

```python
import os
from pathlib import Path

from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession
from contree_sdk.cache import CacheScope, SyncSQLiteCache
from contree_sdk.files import ClientFileTransfer
from contree_sdk.upload_cache import CachedFileTransfer

Path("input.txt").write_text("hello")
with (
    ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client,
    SyncSQLiteCache("uploads.db") as cache,
):
    scope = CacheScope.from_client(client, profile="work")
    transfer = CachedFileTransfer(ClientFileTransfer(client), cache, scope=scope, ttl=3600)
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"], file_transfer=transfer)
    session.run("cat", args=["/input"], files={"/input": Path("input.txt")})
    session.run("wc", args=["-c", "/input"], files={"/input": Path("input.txt")})

    uploads = transfer.cache.entries(namespace="uploads")
    assert len(uploads) == 1
    assert uploads[0].expires_at is not None
    sources = transfer.sources.sources(uploads[0].value["uuid"])
    assert sources[0].source == str(Path("input.txt").resolve())

    assert transfer.cache.invalidate(namespace="uploads") == 1
    assert transfer.sources.sources() == sources
```

<!--
name: test_cached_upload
```python
assert len(doc_api.sync.calls_for("ensure_file")) == 1
assert len(doc_api.sync.calls_for("spawn_instance")) == 2
```
-->

::::

::::{tab} Async

<!--
name: async test_cached_upload_async; fixtures: doc_api
```python
doc_api.complete()
doc_api.complete()
```
-->

```python
import os
import asyncio
from pathlib import Path

from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession
from contree_sdk.cache import AsyncSQLiteCache, CacheScope
from contree_sdk.files import AsyncClientFileTransfer
from contree_sdk.upload_cache import AsyncCachedFileTransfer

await asyncio.to_thread(Path("input.txt").write_text, "hello")
async with (
    ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client,
    AsyncSQLiteCache("uploads.db") as cache,
):
    scope = CacheScope.from_client(client, profile="work")
    transfer = AsyncCachedFileTransfer(AsyncClientFileTransfer(client), cache, scope=scope, ttl=3600)
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"], file_transfer=transfer)
    await session.run("cat", args=["/input"], files={"/input": Path("input.txt")})
    await session.run("wc", args=["-c", "/input"], files={"/input": Path("input.txt")})

    uploads = await transfer.cache.entries(namespace="uploads")
    assert len(uploads) == 1
    sources = await transfer.sources.sources(uploads[0].value["uuid"])
    assert sources[0].source == str(Path("input.txt").resolve())
    assert await transfer.cache.invalidate(namespace="uploads") == 1
    assert await transfer.sources.sources() == sources
```

<!--
name: test_cached_upload_async
```python
assert len(doc_api.async_client.calls_for("ensure_file")) == 1
assert len(doc_api.async_client.calls_for("spawn_instance")) == 2
```
-->

::::

`CacheScope.from_client()` separates the endpoint, project, credential, and optional
profile name. It stores a digest, not the credential. Credential rotation creates
a new scope. Construct the transfer again when switching connection settings.
The caller owns the client, underlying transfer, and cache.

`SyncFileSources` and `AsyncFileSources` also provide `record()`, `sources()`, and
`forget()`. Records can identify local paths or URLs (`kind="url"`). Multiple
sources can refer to the same UUID. They use a separate permanent namespace, so
upload expiry and upload invalidation preserve them. SQLite retains them across
restarts. Removing the database or clearing their namespace removes these records.
Source records describe provenance; they do not prove that a remote upload still
exists or that the local file still contains those bytes. Operation state belongs
in the session store, separately from these caches.

## Enumerate and invalidate cache entries

All native caches store detached JSON values. Memory and SQLite have the same
contract. `get_entry()` distinguishes a missing entry from a stored JSON `null`.
`entries()` returns live entries sorted by key. Prefixes are literal and case
sensitive. Delete and invalidation counts include expired records still stored.

<!--
name: test_cache_contract
-->

```python
from contree_sdk.cache import SyncMemoryCache

now = [100.0]
cache = SyncMemoryCache(clock=lambda: now[0])
cache.set("images/base", {"uuid": "base"}, namespace="completion", ttl=10)
cache.set("images/final", None, namespace="completion")
assert [entry.key for entry in cache.entries(namespace="completion", prefix="images/")] == [
    "images/base",
    "images/final",
]
now[0] = 110
assert cache.get_entry("images/base", namespace="completion") is None
assert cache.get_entry("images/final", namespace="completion").value is None
assert cache.invalidate(namespace="completion", prefix="images/") == 2
```

`ttl=None` retains an entry until deletion. `ttl=0` expires it immediately. Negative
or nonfinite lifetimes raise `ValueError`. Setting a key replaces its value and
expiry; reading never renews it. Native caches accept an injectable clock for tests.

Use `ScopedSyncCache(cache, scope)` or `ScopedAsyncCache(cache, scope)` when managing
namespaces directly. Closing a scoped view does not close the underlying cache.
SQLite uses `cache_v2`; old disposable `cache_v1` records are not reused.
