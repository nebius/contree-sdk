---
icon: database
---

# Save and resume a session

Use a SQLite store when a workflow must continue after Python exits.
The database keeps typed history trees, saved results, and recorded command defaults.
The filesystem images stay on the ConTree server.

Branch names and the selected position belong to each Session object. They are
not shared through the database. A linear history can resume without a selector.
When a tree has several continuations, pass `node_id` to select the saved state.
See {doc}`reference/store` for the storage contract.

## Save work, close the store, and reopen it

This program writes `/saved.txt`, closes the database, then resumes the same session.
It prints `saved`. Configure a connection as described in {ref}`sandbox-connection`.

::::{tab} Sync

<!--
name: test_resume; fixtures: sandbox_api, capsys
```python
sandbox_api.command()
sandbox_api.download(b"saved\n")
```
-->

```python
"""Save a session and reopen its filesystem state."""

from contree_sdk import create_sandbox_session
from contree_sdk.store import SyncSQLiteStore


def main() -> None:
    with SyncSQLiteStore("sessions.db") as store:
        with create_sandbox_session(image="tag:alpine:latest", store=store, session_id="demo") as session:
            session.run(shell="echo saved > /saved.txt")

    # Reopen the same database. No base image is needed to resume.
    with SyncSQLiteStore("sessions.db") as store:
        with create_sandbox_session(store=store, session_id="demo") as resumed:
            content = resumed.read_file("/saved.txt")
            print(content.decode(), end="")


main()
```

<!--
name: test_resume
```python
assert len(sandbox_api.sync.calls_for("resolve_image")) == 1
assert sandbox_api.sync.calls_for("inspect_image_download")[0].args == ("image-op-1", "/saved.txt")
assert capsys.readouterr().out == "saved\n"
```
-->

::::

::::{tab} Async

<!--
name: test_resume_async; fixtures: sandbox_api, capsys
```python
sandbox_api.command()
sandbox_api.download(b"saved\n")
```
-->

```python
import asyncio

from contree_sdk import create_sandbox_session
from contree_sdk.store import AsyncSQLiteStore


async def main() -> None:
    async with AsyncSQLiteStore("sessions.db") as store:
        async with create_sandbox_session(image="tag:alpine:latest", store=store, session_id="demo") as session:
            await session.run(shell="echo saved > /saved.txt")

    # Reopen the same database. No base image is needed to resume.
    async with AsyncSQLiteStore("sessions.db") as store:
        async with create_sandbox_session(store=store, session_id="demo") as resumed:
            content = await resumed.read_file("/saved.txt")
            print(content.decode(), end="")


asyncio.run(main())
```

<!--
name: test_resume_async
```python
assert len(sandbox_api.async_client.calls_for("resolve_image")) == 1
assert sandbox_api.async_client.calls_for("inspect_image_download")[0].args == ("image-op-1", "/saved.txt")
assert capsys.readouterr().out == "saved\n"
```
-->

::::

The second store block can run in a different Python process. It needs the same
database, `session_id="demo"`, and access to the same ConTree server. It does not
need the original `image=` argument. An unknown session ID without an image raises
`ValueError`.

If a store already contains that session ID, the selected saved image takes precedence
over `image=`. Use a new session ID to start from a different base image.

Snapshots are lightweight and can save work after every command, but each one
stops the running VM. If files have not changed, the image UUID can stay the same.
Store history still identifies each checkpoint. For automatic saving after each
command, see [Save after every command](session-model.md#save-after-every-command).

## Choose what to retain

| Resource                   | Default lifetime                        | How to retain it                                           |
| -------------------------- | --------------------------------------- | ---------------------------------------------------------- |
| Command filesystem changes | Saved on normal sandbox exit            | Call `snapshot()` for an earlier checkpoint.               |
| Session history            | A memory-store instance                 | Supply a SQLite store and keep its database.               |
| Session identity           | A generated ID                          | Supply a stable `session_id` or save `session.session_id`. |
| Running processes          | Until the next snapshot or context exit | Choose a snapshot policy; see {doc}`reference/session`.    |
| Server images              | Managed by the server                   | Keep required images available on that server.             |

Reopening SQLite restores references to server images. It does not restore images
that were deleted, nor restart processes from an earlier operation.

## Advanced: resource ownership

Use `with` for sync clients and stores; use `async with` for async versions.
The sandbox closes its own client and session. It does not close supplied
storage or other application-owned components. See {doc}`manual-sandbox` for
explicit construction and cleanup.
Sharing a store is supported: each `session_id` has separate history.

A command with a nonzero exit code can still produce a saved image. Inspect the
result before deciding whether to continue or roll back. See {doc}`troubleshooting`
and {doc}`branching`.

## Resume a selected node

Save the entry ID returned by `snapshot()` or `commit_result()`. Pass it as
`node_id=` to `create_sandbox_session`, `ContreeSession`, or `ContreeAsyncSession`.
The Store does not remember a shared current position. Two clients can resume the
same node and create independent continuations. Local branch names do not survive
reopening; retain node IDs when your application needs named checkpoints.
