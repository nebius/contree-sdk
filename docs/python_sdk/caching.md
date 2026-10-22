# Reuse uploads and retain their sources

Use `CachedFileTransfer` or `AsyncCachedFileTransfer` to reuse uploads by content.
Pass an explicit lifetime in seconds. A cache hit does not extend that lifetime.
Choose a lifetime shorter than the server's upload retention period. The cache
cannot detect uploads removed from the server before expiry; invalidate them
explicitly when necessary.

## Reuse uploads through the factory

The sandbox factory reuses uploads through its Store. These examples select `ContreeSession` or
`ContreeAsyncSession` because startup `files=` attachments need independent
operations. The factory constructs the cached transfer and its connection scope.
For the default lazy sandbox, see {doc}`files` for writing files through stdin.

::::{tab} Sync

<!--
name: test_factory_upload_cache; fixtures: doc_api
```python
doc_api.complete()
doc_api.complete()
```
-->

```python
from contree_sdk import ContreeSession, create_sandbox_session
from contree_sdk.store import SyncMemoryStore


with SyncMemoryStore() as store:
    with create_sandbox_session(image="tag:alpine:latest", session_type=ContreeSession, store=store) as sandbox:
        sandbox.run("cat", args=["/input.txt"], files={"/input.txt": b"hello"})
        sandbox.run("wc", args=["-c", "/input.txt"], files={"/input.txt": b"hello"})
```

<!--
name: test_factory_upload_cache
```python
assert len(doc_api.sync.calls_for("ensure_file")) == 1
assert len(doc_api.sync.calls_for("spawn_instance")) == 2
```
-->

::::

::::{tab} Async

<!--
name: async test_factory_upload_cache_async; fixtures: doc_api
```python
doc_api.complete()
doc_api.complete()
```
-->

```python
from contree_sdk import ContreeAsyncSession, create_sandbox_session
from contree_sdk.store import AsyncMemoryStore


async with AsyncMemoryStore() as store:
    async with create_sandbox_session(
        image="tag:alpine:latest", session_type=ContreeAsyncSession, store=store
    ) as sandbox:
        await sandbox.run("cat", args=["/input.txt"], files={"/input.txt": b"hello"})
        await sandbox.run("wc", args=["-c", "/input.txt"], files={"/input.txt": b"hello"})
```

<!--
name: test_factory_upload_cache_async
```python
assert len(doc_api.async_client.calls_for("ensure_file")) == 1
assert len(doc_api.async_client.calls_for("spawn_instance")) == 2
```
-->

::::

The factory's default `cache_ttl` is 60 seconds. The caller owns the supplied Store.
Use a SQLite Store to retain history and reusable results across Python restarts.

## Advanced: construct a cached transfer

The transfer creates a temporary copy while hashing a local file in chunks. It
uploads that copy, so later changes to the source cannot change the bytes associated
with the fingerprint. Temporary copies are removed after success, failure, or
cancellation. Concurrent misses can upload the same content more than once.

This example attaches the same local input to two commands. The second command
reuses its uploaded UUID. Each request still supplies its own destination and
permissions. Configure a connection as described in {ref}`sandbox-connection`.

::::{tab} Sync

<!--
name: test_cached_upload; fixtures: doc_api
```python
doc_api.complete()
doc_api.complete()
```
-->

```python
from pathlib import Path

from contree_client import profiles
from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession
from contree_sdk.store import SyncSQLiteStore
from contree_sdk.scope import StoreScope
from contree_sdk.files import ClientFileTransfer
from contree_sdk.upload_cache import CachedFileTransfer


Path("input.txt").write_text("hello")
with (
    ContreeClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client,
    SyncSQLiteStore("uploads.db") as store,
):
    scope = StoreScope.from_client(client, profile="work")
    transfer = CachedFileTransfer(ClientFileTransfer(client), store, scope=scope, ttl=3600)
    session = ContreeSession(client, image="tag:alpine:latest", store=store, file_transfer=transfer)
    session.run("cat", args=["/input"], files={"/input": Path("input.txt")})
    session.run("wc", args=["-c", "/input"], files={"/input": Path("input.txt")})

    uploads = transfer.store.list_sessions(kind="upload-cache").items
    assert len(uploads) == 1
    assert uploads[0].expires_at is not None
    sources = transfer.sources.sources()
    assert sources[0].source == str(Path("input.txt").resolve())

    assert transfer.store.delete_session(uploads[0].session_id)
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
import asyncio
from pathlib import Path

from contree_client import profiles
from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession
from contree_sdk.store import AsyncSQLiteStore
from contree_sdk.scope import StoreScope
from contree_sdk.files import AsyncClientFileTransfer
from contree_sdk.upload_cache import AsyncCachedFileTransfer


await asyncio.to_thread(Path("input.txt").write_text, "hello")
async with (
    ContreeAsyncClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client,
    AsyncSQLiteStore("uploads.db") as store,
):
    scope = StoreScope.from_client(client, profile="work")
    transfer = AsyncCachedFileTransfer(AsyncClientFileTransfer(client), store, scope=scope, ttl=3600)
    session = ContreeAsyncSession(client, image="tag:alpine:latest", store=store, file_transfer=transfer)
    await session.run("cat", args=["/input"], files={"/input": Path("input.txt")})
    await session.run("wc", args=["-c", "/input"], files={"/input": Path("input.txt")})

    uploads = (await transfer.store.list_sessions(kind="upload-cache")).items
    assert len(uploads) == 1
    sources = await transfer.sources.sources()
    assert sources[0].source == str(Path("input.txt").resolve())
    assert await transfer.store.delete_session(uploads[0].session_id)
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

`StoreScope.from_client()` separates the endpoint, project, credential, and optional
profile name. It stores a digest, not the credential. Credential rotation creates
a new scope. Construct the transfer again when switching connection settings.
The caller owns the client, underlying transfer, and Store.

`SyncFileSources` and `AsyncFileSources` also provide `record()`, `sources()`, and
`forget()`. Records can identify local paths or URLs (`kind="url"`). Multiple
sources can refer to the same UUID. They use separate typed trees. Source records
describe provenance; they do not prove that a remote upload still exists or that
the local file still contains those bytes.

## Enumerate retained trees

Upload reuse uses trees with `kind="upload-cache"`. Call
`store.list_sessions(kind="upload-cache", limit=100)` and follow `next_cursor`
to enumerate them. `delete_session(tree.session_id)` invalidates one tree.
Source records use separate `file-sources` trees, so deleting reusable upload
results preserves provenance. Retention for source trees follows the Store's
policy for `ttl=None`; it is not a universal promise of permanent storage.

The same Store can hold user sessions, builds, and upload results. Select
`kind="session"` when listing user sessions. See {doc}`reference/store` for
sync/async examples, pagination, immutable nodes, and TTL semantics.
