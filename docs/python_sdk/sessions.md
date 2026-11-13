---
icon: database
---

# Save and resume a session

A session runs commands and records saved states in a **Store**. The Store keeps
the session's history and references to its filesystem images. ConTree keeps the
images on the server. To continue later, open the same Store and select the same
session.

This guide starts with memory storage, then saves work in SQLite and opens it
again. Configure your connection as described in {ref}`sandbox-connection`.
Async SQLite examples require the `contree-sdk[async]` extra.

## 1. Choose where to keep history

Store is a storage interface. The SDK includes two implementations:

| Store                                  | Where history lives                      | When to use it                    |
| -------------------------------------- | ---------------------------------------- | --------------------------------- |
| `SyncMemoryStore` / `AsyncMemoryStore` | In memory, while that Store remains open | Work within one Python program.   |
| `SyncSQLiteStore` / `AsyncSQLiteStore` | In a local SQLite file                   | Continue work after Python exits. |

Without `store=`, `create_sandbox_session()` creates a memory Store for that
context. To share history between contexts, create a Store yourself and pass it
through `store=`. The outer context below keeps that Store open until both
sessions have finished.

Both sessions use `session_id="demo"`. The second context opens the first
session's saved state and reads its file.

::::{tab} Sync

<!--
name: test_store_memory_sync; fixtures: sandbox_api, capsys
```python
sandbox_api.download(b"saved\n")
```
-->

```python
from contree_sdk import create_sandbox_session
from contree_sdk.store import SyncMemoryStore

with SyncMemoryStore() as store:
    with create_sandbox_session(image="tag:alpine:latest", store=store, session_id="demo") as session:
        session.run(shell="echo saved > /saved.txt")

    with create_sandbox_session(store=store, session_id="demo") as session:
        content = session.read_file("/saved.txt")
        print(content.decode())
```

<!--
name: test_store_memory_sync
```python
assert capsys.readouterr().out == "saved\n\n"
assert len(sandbox_api.sync.calls_for("resolve_image")) == 1
assert sandbox_api.sync.calls_for("inspect_image_download")[0].args == ("image-op-1", "/saved.txt")
```
-->

::::

::::{tab} Async

<!--
name: test_store_memory_async; fixtures: sandbox_api, capsys
```python
sandbox_api.download(b"saved\n")
```
-->

```python
import asyncio

from contree_sdk import create_sandbox_session
from contree_sdk.store import AsyncMemoryStore


async def main() -> None:
    async with AsyncMemoryStore() as store:
        async with create_sandbox_session(image="tag:alpine:latest", store=store, session_id="demo") as session:
            await session.run(shell="echo saved > /saved.txt")

        async with create_sandbox_session(store=store, session_id="demo") as session:
            content = await session.read_file("/saved.txt")
            print(content.decode())


asyncio.run(main())
```

<!--
name: test_store_memory_async
```python
assert capsys.readouterr().out == "saved\n\n"
assert len(sandbox_api.async_client.calls_for("resolve_image")) == 1
assert sandbox_api.async_client.calls_for("inspect_image_download")[0].args == ("image-op-1", "/saved.txt")
```
-->

::::

Output:

```text
saved
```

Closing the memory Store discards its history. A new memory Store starts empty,
even if you reuse the same session ID. Use SQLite to keep history between runs.

## 2. Save work in a SQLite file

Replace the memory Store with a SQLite Store. This program creates `sessions.db`
in the current directory and records a session named `my-project`.

Run this program first. Normal exit from the session context saves the filesystem
changes and records the saved image in the Store. Then the outer context closes
the database.

::::{tab} Sync

<!-- name: test_store_resume_sync; fixtures: sandbox_api, capsys -->

```python
from contree_sdk import create_sandbox_session
from contree_sdk.store import SyncSQLiteStore

with SyncSQLiteStore("sessions.db") as store:
    with create_sandbox_session(image="tag:alpine:latest", store=store, session_id="my-project") as session:
        session.run(shell="echo saved > /saved.txt")
```

::::

::::{tab} Async

<!-- name: test_store_resume_async; fixtures: sandbox_api, capsys -->

```python
import asyncio

from contree_sdk import create_sandbox_session
from contree_sdk.store import AsyncSQLiteStore


async def main() -> None:
    async with AsyncSQLiteStore("sessions.db") as store:
        async with create_sandbox_session(image="tag:alpine:latest", store=store, session_id="my-project") as session:
            await session.run(shell="echo saved > /saved.txt")


asyncio.run(main())
```

::::

There are now two different files: `sessions.db` is local history, and
`/saved.txt` is inside the filesystem image stored by ConTree. The SQLite file
does not contain a copy of that filesystem.

## 3. Continue in another program

Run this second program from the same directory. It opens the existing database
and selects `my-project`. No `image=` argument is needed: the session gets its
saved image from the Store.

The command reads the file created by the first program. You can run more
commands in this context; normal exit saves their filesystem changes too.

::::{tab} Sync

<!--
name: test_store_resume_sync
```python
sandbox_api.command("saved\n")
```
-->

```python
from contree_sdk import create_sandbox_session
from contree_sdk.store import SyncSQLiteStore

with SyncSQLiteStore("sessions.db") as store:
    with create_sandbox_session(store=store, session_id="my-project") as session:
        result = session.run("cat", args=["/saved.txt"])
        print(result.stdout)
```

<!--
name: test_store_resume_sync
```python
assert capsys.readouterr().out == "saved\n\n"
assert len(sandbox_api.sync.calls_for("resolve_image")) == 1
assert sandbox_api.sync.calls_for("spawn_instance")[1].args[1] == "image-op-1"

with SyncSQLiteStore("sessions.db") as reopened:
    nodes = reopened.list_nodes("my-project").items
    assert any(node.data.get("image_uuid") == "image-op-2" for node in nodes)
```
-->

::::

::::{tab} Async

<!--
name: test_store_resume_async
```python
sandbox_api.command("saved\n")
```
-->

```python
import asyncio

from contree_sdk import create_sandbox_session
from contree_sdk.store import AsyncSQLiteStore


async def main() -> None:
    async with AsyncSQLiteStore("sessions.db") as store:
        async with create_sandbox_session(store=store, session_id="my-project") as session:
            result = await session.run("cat", args=["/saved.txt"])
            print(result.stdout)


asyncio.run(main())
```

<!--
name: test_store_resume_async
```python
assert capsys.readouterr().out == "saved\n\n"
assert len(sandbox_api.async_client.calls_for("resolve_image")) == 1
assert sandbox_api.async_client.calls_for("spawn_instance")[1].args[1] == "image-op-1"
from contree_sdk.store import SyncSQLiteStore

with SyncSQLiteStore("sessions.db") as reopened:
    nodes = reopened.list_nodes("my-project").items
    assert any(node.data.get("image_uuid") == "image-op-2" for node in nodes)
```
-->

::::

Output:

```text
saved
```

Keep the same database path, session ID, and access to the same ConTree server
and project. A different working directory can make `"sessions.db"` refer to a
different file. Use an absolute path when programs run from different directories.

An unknown session ID without `image=` raises `ValueError`. If you provide an
image and an unused ID, the SDK creates a new session. An existing ID resumes its
saved state even when you pass `image=`. Use a new ID for independent work.

## 4. Keep several sessions in one file

One Store can hold many sessions. Each `session_id` identifies a separate history
within that Store. These two sessions start from the same base image, then save
different contents at the same path.

Run this program to create a separate `projects.db` for the next steps.

::::{tab} Sync

<!-- name: test_store_catalog_sync; fixtures: sandbox_api, capsys -->

```python
from contree_sdk import create_sandbox_session
from contree_sdk.store import SyncSQLiteStore

with SyncSQLiteStore("projects.db") as store:
    for name in ("project-a", "project-b"):
        with create_sandbox_session(image="tag:alpine:latest", store=store, session_id=name) as session:
            session.run(shell=f"echo {name} > /project.txt")
```

::::

::::{tab} Async

<!-- name: test_store_catalog_async; fixtures: sandbox_api, capsys -->

```python
import asyncio

from contree_sdk import create_sandbox_session
from contree_sdk.store import AsyncSQLiteStore


async def main() -> None:
    async with AsyncSQLiteStore("projects.db") as store:
        for name in ("project-a", "project-b"):
            async with create_sandbox_session(image="tag:alpine:latest", store=store, session_id=name) as session:
                await session.run(shell=f"echo {name} > /project.txt")


asyncio.run(main())
```

::::

The shared database does not combine the files or histories of these sessions.
Omit `session_id` to generate a new ID automatically; read `session.session_id`
if you need to keep that ID.

## 5. Find a saved session

Open the database and call `list_sessions(kind="session")`. The filter selects
user session histories and excludes records used for builds or upload reuse.
Listing stored sessions does not start a VM or contact ConTree.

Results arrive in pages. Print each page, then pass `next_cursor` to read the next
one. Stop when it is `None`. This example requests one item per page so you can
see pagination with just two sessions; increase `limit` for larger lists.

::::{tab} Sync

<!-- name: test_store_catalog_sync -->

```python
from contree_sdk.store import SyncSQLiteStore

with SyncSQLiteStore("projects.db") as store:
    cursor = None
    while True:
        page = store.list_sessions(kind="session", limit=1, cursor=cursor)
        for saved in page.items:
            print(saved.session_id)
        cursor = page.next_cursor
        if cursor is None:
            break
```

<!--
name: test_store_catalog_sync
```python
assert capsys.readouterr().out == "project-a\nproject-b\n"
assert len(sandbox_api.sync.calls_for("spawn_instance")) == 2
```
-->

::::

::::{tab} Async

<!-- name: test_store_catalog_async -->

```python
import asyncio

from contree_sdk.store import AsyncSQLiteStore


async def main() -> None:
    async with AsyncSQLiteStore("projects.db") as store:
        cursor = None
        while True:
            page = await store.list_sessions(kind="session", limit=1, cursor=cursor)
            for saved in page.items:
                print(saved.session_id)
            cursor = page.next_cursor
            if cursor is None:
                break


asyncio.run(main())
```

<!--
name: test_store_catalog_async
```python
assert capsys.readouterr().out == "project-a\nproject-b\n"
assert len(sandbox_api.async_client.calls_for("spawn_instance")) == 2
```
-->

::::

Output:

```text
project-a
project-b
```

The list is ordered by session ID, not by last activity. Each item also contains
`created_at` and `expires_at`. Pass `prefix="project-"` to select IDs with that
prefix.

## 6. Continue the session you chose

Copy an ID from the list into `session_id`. This program selects `project-b` and
reads its saved file. To open `project-a`, change only that ID.

::::{tab} Sync

<!--
name: test_store_catalog_sync
```python
sandbox_api.download(b"project-b\n")
```
-->

```python
from contree_sdk import create_sandbox_session
from contree_sdk.store import SyncSQLiteStore

with SyncSQLiteStore("projects.db") as store:
    with create_sandbox_session(store=store, session_id="project-b") as session:
        content = session.read_file("/project.txt")
        print(content.decode())
```

<!--
name: test_store_catalog_sync
```python
assert capsys.readouterr().out == "project-b\n\n"
assert sandbox_api.sync.calls_for("inspect_image_download")[0].args == ("image-op-2", "/project.txt")
assert len(sandbox_api.sync.calls_for("spawn_instance")) == 2
assert all(call.args[1] == "base" for call in sandbox_api.sync.calls_for("spawn_instance"))
```
-->

::::

::::{tab} Async

<!--
name: test_store_catalog_async
```python
sandbox_api.download(b"project-b\n")
```
-->

```python
import asyncio

from contree_sdk import create_sandbox_session
from contree_sdk.store import AsyncSQLiteStore


async def main() -> None:
    async with AsyncSQLiteStore("projects.db") as store:
        async with create_sandbox_session(store=store, session_id="project-b") as session:
            content = await session.read_file("/project.txt")
            print(content.decode())


asyncio.run(main())
```

<!--
name: test_store_catalog_async
```python
assert capsys.readouterr().out == "project-b\n\n"
assert sandbox_api.async_client.calls_for("inspect_image_download")[0].args == ("image-op-2", "/project.txt")
assert len(sandbox_api.async_client.calls_for("spawn_instance")) == 2
assert all(call.args[1] == "base" for call in sandbox_api.async_client.calls_for("spawn_instance"))
```
-->

::::

Output:

```text
project-b
```

## Resume a selected node

The examples above each have one continuation, so a session ID is enough.
After branching, a history can contain several continuations. The SDK then
raises `ValueError` unless you pass `node_id=` to select a saved state.

Keep the entry ID returned by `snapshot()` when you need an exact checkpoint.
Pass it as `node_id=` together with `session_id=` when reopening. A session ID
selects the history; a node ID selects a point within that history. See
{doc}`branching` for checkpoints and branches.

The Store does not retain the last selected position or local branch names.
Even with one continuation, reopening can select a later saved state than the
one you selected with `rollback()`. Keep the selected node ID for exact resume.
Independent clients can resume the same node and create separate continuations.

## What must remain available?

- Keep the SQLite database and access to the same ConTree server and project.
- Keep the referenced images on that server. SQLite cannot restore a deleted image.
- Save filesystem changes before stopping Python. Normal context exit saves them;
  `snapshot()` saves an earlier checkpoint. An exception discards changes since
  the last completed snapshot. Abrupt process termination does not guarantee a save.
- Snapshots save files, not running processes or VM memory. Continuing a session
  starts new processes from the saved filesystem.

An unchanged filesystem can produce the same image UUID at several checkpoints.
History entry IDs still distinguish them. For automatic saving after each
command, see [Save after every command](session-model.md#save-after-every-command).
A nonzero command exit code can still produce a saved image; inspect the result
before continuing or rolling back.

## Use another storage backend

For your own database or service, implement `SyncStore` or `AsyncStore` and pass
the object through `store=`. See {doc}`custom-store` in Advanced Usage for an
example and the implementation requirements.

The application closes any Store it supplies. Keep the Store context outside all
session contexts that use it, as in these examples. See {doc}`manual-sandbox` for
explicit component construction and cleanup, and {doc}`reference/store` for the
complete storage API.

## Configure session networking

Set `network_policy` to a UUID, `tag:name`, or a sequence of references, and
`network_enabled` to a boolean. UUIDs are checked for existence and tags resolve
when supplied; saved selections are reused without lookups. Create
policies and manage tags through `contree-client`. This example assumes an
existing `restricted` tag.

<!--
name: test_networking; fixtures: sandbox_api
```python
from contree_client.models import NetworkPolicyTag

sandbox_api.sync.mock(
    "get_network_policy_tag", NetworkPolicyTag(tag="restricted", uuid="11111111-1111-4111-8111-111111111111")
)
```
-->

```python
from contree_client.sync import ContreeClient

from contree_sdk import create_sandbox_session

with ContreeClient.from_profile() as client:
    with create_sandbox_session(
        client=client, image="tag:alpine:latest", network_policy="tag:restricted", network_enabled=True
    ) as session:
        session.run("echo", args=("networking configured",))
        session.change_network_enabled(False)
        session.run("echo", args=("no network interface",))
        session.change_network_enabled(True)  # Retains the selected policy.
        session.change_network_policy(None)  # Restore default network access.
```

<!--
name: test_networking
```python
calls = sandbox_api.sync.calls_for("spawn_instance")
assert [call.kwargs["networking"].to_dict() for call in calls] == [
    {"enabled": True, "policy": ["11111111-1111-4111-8111-111111111111"]},
    {"enabled": False, "policy": ["11111111-1111-4111-8111-111111111111"]},
]
assert calls[1].args[1] == "image-op-1"
```
-->

Use `await` with async sessions. Both change methods update session defaults
and save a configuration history step. On a lazy session, they first snapshot
the active VM, stopping its processes.

- `change_network_policy(None)` or `[]` clears the selection and restores backend
  default access. To deny all traffic, select a policy with empty rules.
- `change_network_enabled(False)` disables the network interface while retaining
  selected policies. The setter requires `True` or `False`; `None` is rejected.
- Regular operations accept `network_policy` and `network_enabled` overrides;
  `None` inherits session defaults. Lazy operations reject these overrides.
- Reopening or navigating a session restores its saved network defaults.

Read `session.network_enabled` and `session.network_policy_uuids` for the current
settings. `HistoryEntry.network_enabled` and `HistoryEntry.network_policy_uuids`
expose the saved session defaults for a history entry, excluding per-operation
overrides. Entries saved before networking settings were introduced default to
enabled networking with no selected policies.

See [migration notes](migration.md#networking-and-extension-hooks) for
legacy `networking=` compatibility.
