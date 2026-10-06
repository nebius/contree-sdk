---
icon: database
---

# Save and resume a session

Use a SQLite store when a workflow must continue after Python exits.
The database keeps session identifiers, history, branch names, and session defaults.
The filesystem images stay on the ConTree server.

## Save work, close the store, and reopen it

This program writes `/saved.txt`, closes the database, then resumes the same session.
It prints `saved`. Use the connection variables from {doc}`getting-started`.

::::{tab} Sync

<!--
name: test_resume; fixtures: doc_api, capsys
```python
doc_api.complete()
doc_api.download(b"saved\n")
```
-->

```python
import os

from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession
from contree_sdk.store import SyncSQLiteStore


def main() -> None:
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        with SyncSQLiteStore("sessions.db") as store:
            session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"], store=store, session_id="demo")
            session.run(shell="printf 'saved\\n' > /saved.txt", disposable=False)

        # Reopen the same database. No base image is needed to resume.
        with SyncSQLiteStore("sessions.db") as store:
            resumed = ContreeSession(client, store=store, session_id="demo")
            print(resumed.read_file("/saved.txt").decode(), end="")


main()
```

<!--
name: test_resume
```python
assert len(doc_api.sync.calls_for("resolve_image")) == 1
assert doc_api.sync.calls_for("inspect_image_download")[0].args == ("image-1", "/saved.txt")
assert capsys.readouterr().out == "saved\n"
```
-->

::::

::::{tab} Async

<!--
name: test_resume_async; fixtures: doc_api, capsys
```python
doc_api.complete()
doc_api.download(b"saved\n")
```
-->

```python
import asyncio
import os

from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession
from contree_sdk.store import AsyncSQLiteStore


async def main() -> None:
    async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        async with AsyncSQLiteStore("sessions.db") as store:
            session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"], store=store, session_id="demo")
            await session.run(shell="printf 'saved\\n' > /saved.txt", disposable=False)

        # Reopen the same database. No base image is needed to resume.
        async with AsyncSQLiteStore("sessions.db") as store:
            resumed = ContreeAsyncSession(client, store=store, session_id="demo")
            print((await resumed.read_file("/saved.txt")).decode(), end="")


asyncio.run(main())
```

<!--
name: test_resume_async
```python
assert len(doc_api.async_client.calls_for("resolve_image")) == 1
assert doc_api.async_client.calls_for("inspect_image_download")[0].args == ("image-1", "/saved.txt")
assert capsys.readouterr().out == "saved\n"
```
-->

::::

The second store block can run in a different Python process. It needs the same
database, `session_id="demo"`, and access to the same ConTree server. It does not
need the original `image=` argument. An unknown session ID without an image raises
`ValueError`.

If a store already contains that session ID, its current image takes precedence
over `image=`. Use a new session ID to start from a different base image.

## Choose what to retain

| Resource                   | Default lifetime                       | How to retain it                                           |
| -------------------------- | -------------------------------------- | ---------------------------------------------------------- |
| Command filesystem changes | Discarded after a disposable operation | Pass `disposable=False`.                                   |
| Session history            | A memory-store instance                | Supply a SQLite store and keep its database.               |
| Session identity           | A generated ID                         | Supply a stable `session_id` or save `session.session_id`. |
| Running processes          | One operation                          | Keep the operation open; see {doc}`operation`.             |
| Server images              | Managed by the server                  | Keep required images available on that server.             |

Reopening SQLite restores references to server images. It does not restore images
that were deleted, nor restart processes from an earlier operation.

## Close resources at the application boundary

Use `with` for sync clients, stores, and caches; use `async with` for async versions.
Sessions, builders, and adapters do not close components supplied by the application.
Sharing a store is supported: each `session_id` has separate history.

A command with a nonzero exit code can still produce a saved image. Inspect the
result before deciding whether to continue or roll back. See {doc}`running-commands`
and {doc}`branching`.
