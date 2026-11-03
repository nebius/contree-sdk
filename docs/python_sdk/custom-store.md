# Implement a custom Store

Use your own Store when session history must live in your database or service.
Inherit `SyncStore` or `AsyncStore` from `contree_sdk.store`, implement its methods,
and pass an instance through `store=`. The session uses the same interface to save
history and resume work, regardless of the storage backend.

Start with {doc}`sessions` for memory and SQLite examples. This page covers
extension points and the guarantees a custom implementation must preserve.

## Extend an existing implementation

If you only need different defaults, subclass a supplied Store. This example
gives newly created trees a seven-day lifetime unless the caller supplies a TTL.
SQLite still handles persistence, atomic writes, and pagination.

The program saves a file, closes the Store, and opens the same session through a
new Store instance. It prints `saved`. Configure a connection as described in
{ref}`sandbox-connection`.

::::{tab} Sync

<!--
name: test_custom_store_sync; fixtures: sandbox_api, capsys
```python
sandbox_api.command()
sandbox_api.download(b"saved\n")
```
-->

```python
from contree_sdk import create_sandbox_session
from contree_sdk.store import SessionInfo, SyncSQLiteStore


class RetainedSQLiteStore(SyncSQLiteStore):
    def create_session(
        self, session_id: str, *, kind: str = "session", ttl: float | None = None
    ) -> SessionInfo:
        lifetime = 7 * 24 * 60 * 60 if ttl is None else ttl
        return super().create_session(session_id, kind=kind, ttl=lifetime)


with RetainedSQLiteStore("history.db") as store:
    with create_sandbox_session(
        image="tag:alpine:latest", store=store, session_id="my-project"
    ) as session:
        session.run(shell="echo saved > /saved.txt")

with RetainedSQLiteStore("history.db") as store:
    with create_sandbox_session(store=store, session_id="my-project") as session:
        content = session.read_file("/saved.txt")
        print(content.decode())
```

<!--
name: test_custom_store_sync
```python
with RetainedSQLiteStore("history.db") as store:
    info = store.get_session("my-project")
assert info is not None
assert abs(info.expires_at - info.created_at - 7 * 24 * 60 * 60) < 0.001
assert capsys.readouterr().out == "saved\n\n"
assert len(sandbox_api.sync.calls_for("resolve_image")) == 1
assert sandbox_api.sync.calls_for("inspect_image_download")[0].args == ("image-op-1", "/saved.txt")
with RetainedSQLiteStore("history.db") as store:
    assert store.create_session("my-project").expires_at == info.expires_at
    explicit = store.create_session("short-lived", ttl=60)
    assert abs(explicit.expires_at - explicit.created_at - 60) < 0.001
```
-->

::::

::::{tab} Async

<!--
name: async test_custom_store_async; fixtures: sandbox_api, capsys
```python
sandbox_api.command()
sandbox_api.download(b"saved\n")
```
-->

```python
from contree_sdk import create_sandbox_session
from contree_sdk.store import AsyncSQLiteStore, SessionInfo


class RetainedSQLiteStore(AsyncSQLiteStore):
    async def create_session(
        self, session_id: str, *, kind: str = "session", ttl: float | None = None
    ) -> SessionInfo:
        lifetime = 7 * 24 * 60 * 60 if ttl is None else ttl
        return await super().create_session(session_id, kind=kind, ttl=lifetime)


async with RetainedSQLiteStore("history.db") as store:
    async with create_sandbox_session(
        image="tag:alpine:latest", store=store, session_id="my-project"
    ) as session:
        await session.run(shell="echo saved > /saved.txt")

async with RetainedSQLiteStore("history.db") as store:
    async with create_sandbox_session(store=store, session_id="my-project") as session:
        content = await session.read_file("/saved.txt")
        print(content.decode())
```

<!--
name: test_custom_store_async
```python
async with RetainedSQLiteStore("history.db") as store:
    info = await store.get_session("my-project")
assert info is not None
assert abs(info.expires_at - info.created_at - 7 * 24 * 60 * 60) < 0.001
assert capsys.readouterr().out == "saved\n\n"
assert len(sandbox_api.async_client.calls_for("resolve_image")) == 1
assert sandbox_api.async_client.calls_for("inspect_image_download")[0].args == ("image-op-1", "/saved.txt")
async with RetainedSQLiteStore("history.db") as store:
    assert (await store.create_session("my-project")).expires_at == info.expires_at
    explicit = await store.create_session("short-lived", ttl=60)
    assert abs(explicit.expires_at - explicit.created_at - 60) < 0.001
```
-->

::::

Run the async example inside an async function or a notebook that supports
top-level `await`. The supplied Store stays open after the session context exits.
The outer Store context closes it.

Reopening a tree does not renew its expiry. Use `set_session_ttl()` to change an
existing tree's lifetime. Expiry makes its history unavailable; it does not delete
server images or stop running operations. The example changes the default for
tree creation only. Other methods retain the supplied SQLite behavior.

## Implement storage in another database

For a different backend, inherit `SyncStore` or `AsyncStore` directly. Implement
every abstract method below with your database client. PostgreSQL and Redis are
possible application backends; the SDK does not include implementations for them.

| Methods                                 | Responsibility                                             |
| --------------------------------------- | ---------------------------------------------------------- |
| `create_session()`, `get_session()`     | Create or read a tree's identity, kind, and expiry.        |
| `set_session_ttl()`, `delete_session()` | Change retention or remove the whole tree.                 |
| `list_sessions()`                       | Filter and page through stored trees.                      |
| `append()`                              | Atomically add an immutable node with its explicit parent. |
| `get_node()`, `get_nodes()`             | Read one node or an atomic batch of known identities.      |
| `list_nodes()`, `list_children()`       | Filter and page through nodes or direct children.          |
| `list_history()`                        | Follow parents from a selected node toward the root.       |
| `close()`                               | Release connections and resources owned by the Store.      |

The async interface has the same methods and results, with `async def` and
`await`. Use an async database client or explicitly offload blocking I/O. The base
classes supply the matching context-manager methods through `close()`.

Store preserves `Node.id`, `parent_id`, `kind`, and JSON-object `data`. A tree also
has a `kind`: sessions, builds, and upload reuse can share a backend. Your Store
must preserve their data without interpreting session commands or Docker hashes.
Use {doc}`reference/store` for exact signatures, limits, and error behavior.

## Preserve the storage guarantees

- Make each call atomic across all clients, including separate processes and
  database connections. A lock in one Python object is insufficient.
- Require a live tree and an existing parent in that tree for `append()`. Allow
  only one root. A late append must not recreate a deleted or expired tree.
- Accept an identical repeated node without duplication. Raise
  `NodeConflictError` if the same identity has different contents or a second root
  is inserted. Do not overwrite saved nodes.
- Return independent JSON values. Changes to a caller's dictionary must not
  change stored data. Preserve atomic batch reads in `get_nodes()`.
- Apply filters before pagination. Order identity-based lists by ID and history
  by ancestry. Return opaque continuation cursors; pages need not share a snapshot.
- Apply TTL to the whole tree. Reads and appends must not extend its lifetime.
  Define the backend policy for `ttl=None` and preserve the contract's expiry errors.

Test retries, conflicting inserts, pagination, expiry, and deletion through
separate connections before using a new backend. Also test saving a session and
resuming it through a new Store instance. The [Store contract](reference/store.md#contract)
defines the complete requirements.

Store saves history and references to remote images. Session controls execution,
the selected node, and local branch names. A custom Store does not need to run
commands or choose a shared current position. Pass it through `store=` to sessions
or helpers, and close it after all users finish.
