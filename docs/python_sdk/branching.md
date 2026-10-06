---
icon: code-branch
---

# Try a change and return to a checkpoint

A branch names a position in a session's image history. Use one branch for a known
baseline and another for an experiment. Switching branches selects a saved image;
it does not rerun earlier commands.

## Compare an experiment with its baseline

This program writes a baseline, changes it on `experiment`, then returns to `main`.
Finally, it rolls the experiment back by one entry. Use the connection variables
from {doc}`getting-started`.

::::{tab} Sync

<!--
name: test_branches; fixtures: doc_api, capsys
```python
doc_api.complete()
doc_api.complete()
doc_api.download(b"candidate\n")
doc_api.download(b"baseline\n")
doc_api.download(b"baseline\n")
```
-->

```python
import os

from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession


def main() -> None:
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
        session.run(shell="echo baseline > /choice.txt", disposable=False)
        session.create_branch("experiment")
        session.switch_branch("experiment")
        session.run(shell="echo candidate > /choice.txt", disposable=False)
        print("experiment:", session.read_file("/choice.txt").decode().strip())

        session.switch_branch("main")
        print("main:", session.read_file("/choice.txt").decode().strip())
        session.switch_branch("experiment")
        session.rollback()
        print("after rollback:", session.read_file("/choice.txt").decode().strip())


main()
```

<!--
name: test_branches
```python
assert [call.args[0] for call in doc_api.sync.calls_for("inspect_image_download")] == ["image-2", "image-1", "image-1"]
assert doc_api.sync.calls_for("spawn_instance")[1].args[1] == "image-1"
assert capsys.readouterr().out == "experiment: candidate\nmain: baseline\nafter rollback: baseline\n"
```
-->

::::

::::{tab} Async

<!--
name: test_branches_async; fixtures: doc_api, capsys
```python
doc_api.complete()
doc_api.complete()
doc_api.download(b"candidate\n")
doc_api.download(b"baseline\n")
doc_api.download(b"baseline\n")
```
-->

```python
import asyncio
import os

from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession


async def main() -> None:
    async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
        await session.run(shell="echo baseline > /choice.txt", disposable=False)
        await session.create_branch("experiment")
        await session.switch_branch("experiment")
        await session.run(shell="echo candidate > /choice.txt", disposable=False)
        print("experiment:", (await session.read_file("/choice.txt")).decode().strip())

        await session.switch_branch("main")
        print("main:", (await session.read_file("/choice.txt")).decode().strip())
        await session.switch_branch("experiment")
        await session.rollback()
        print("after rollback:", (await session.read_file("/choice.txt")).decode().strip())


asyncio.run(main())
```

<!--
name: test_branches_async
```python
assert [call.args[0] for call in doc_api.async_client.calls_for("inspect_image_download")] == [
    "image-2",
    "image-1",
    "image-1",
]
assert doc_api.async_client.calls_for("spawn_instance")[1].args[1] == "image-1"
assert capsys.readouterr().out == "experiment: candidate\nmain: baseline\nafter rollback: baseline\n"
```
-->

::::

Expected output:

```text
experiment: candidate
main: baseline
after rollback: baseline
```

`create_branch()` creates a pointer without selecting it. `switch_branch()` selects
that pointer and refreshes the session's current image. `rollback()` moves the
active pointer back; it does not delete the later history entry.

## Navigate recorded history

`history()` returns `(entries, branch_pointers)`. Each entry records its parent,
image UUID, command title, and exit code. `branch_pointers` maps entry IDs to branch names.

| Method               | Effect                                   |
| -------------------- | ---------------------------------------- |
| `rollback(steps=1)`  | Move back through parents.               |
| `navigate(entry_id)` | Select an entry by its positive ID.      |
| `navigate(-2)`       | Move back two entries.                   |
| `navigate_forward()` | Choose the most recently recorded child. |
| `list_branches()`    | Return `(name, is_active)` pairs.        |

After a fork, `navigate_forward()` does not choose by branch name. Use
`switch_branch(name)` when the destination branch matters.

## Read history without moving a branch

Use the store's `resolve_history(session_id, ...)` to inspect a recorded position.
It does not change the active branch, tip, working directory, or environment.
`read_session()` captures one `HistorySnapshot` when several queries must use
exactly the same local state. Snapshots remain usable after the store closes.

| Position                   | Query arguments                 |
| -------------------------- | ------------------------------- |
| Active branch head         | No selector                     |
| Named branch head          | `branch="checkpoint"`           |
| Absolute entry             | `history_id=entry_id`           |
| Two ancestors              | `offset=-2`                     |
| One descendant of an entry | `history_id=entry_id, offset=1` |

Offsets can start at the active head, a named branch, or an absolute entry. Forward
queries choose the child with the greatest entry ID, as `navigate_forward()` does.
They can follow history beyond a rolled-back branch pointer. Use `branch=` when
selecting a named head matters. Combining `branch` and `history_id`, crossing a
history boundary, or selecting another session's entry raises `ValueError`.
The SDK does not parse CLI strings such as `HEAD~2` or `@+1`.

::::{tab} Sync

<!--
name: test_history_queries; fixtures: doc_api
```python
doc_api.complete()
doc_api.complete()
```
-->

```python
import os
from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession
from contree_sdk.store import SyncSQLiteStore

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    with SyncSQLiteStore("history-queries.db") as store:
        session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"], session_id="demo", store=store)
        session.run("touch", args=["/one"], disposable=False)
        session.create_branch("checkpoint")
        session.run("touch", args=["/two"], disposable=False)
        snapshot = store.read_session("demo")
        head = snapshot.resolve()
        previous = snapshot.resolve(offset=-1)
        saved = snapshot.resolve(branch="checkpoint")
        operation_uuid = snapshot.resolve_operation()
        summary = store.get_session_summary("demo")
        sessions = store.list_session_summaries(prefix="de")
```

<!--
name: test_history_queries
```python
assert previous == saved
assert snapshot.resolve(history_id=previous.id, offset=1) == head
assert operation_uuid == "operation-2"
assert summary.entry_count == 3
assert summary.active_branch == "main"
assert [item.session_id for item in sessions] == ["demo"]
assert session.image_uuid == head.image_uuid == "image-2"
with SyncSQLiteStore("history-queries.db") as reopened:
    assert reopened.read_session("demo") == snapshot
```
-->

::::

::::{tab} Async

<!--
name: async test_history_queries_async; fixtures: doc_api
```python
doc_api.complete()
doc_api.complete()
```
-->

```python
import os
from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession
from contree_sdk.store import AsyncSQLiteStore

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    async with AsyncSQLiteStore("history-queries_async.db") as store:
        session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"], session_id="demo", store=store)
        await session.run("touch", args=["/one"], disposable=False)
        await session.create_branch("checkpoint")
        await session.run("touch", args=["/two"], disposable=False)
        snapshot = await store.read_session("demo")
        head = snapshot.resolve()
        previous = snapshot.resolve(offset=-1)
        saved = snapshot.resolve(branch="checkpoint")
        operation_uuid = snapshot.resolve_operation()
        summary = await store.get_session_summary("demo")
        sessions = await store.list_session_summaries(prefix="de")
```

<!--
name: test_history_queries_async
```python
assert previous == saved
assert snapshot.resolve(history_id=previous.id, offset=1) == head
assert operation_uuid == "operation-2"
assert summary.entry_count == 3
assert summary.active_branch == "main"
assert [item.session_id for item in sessions] == ["demo"]
assert session.image_uuid == head.image_uuid == "image-2"
async with AsyncSQLiteStore("history-queries_async.db") as reopened:
    assert await reopened.read_session("demo") == snapshot
```
-->

::::

`resolve_operation()` returns the UUID of exactly the selected entry. It raises
`ValueError` when that entry has no operation, including an initial image entry;
it does not substitute an ancestor's operation. Pass the UUID to an `Operation`
or `AsyncOperation` handle to inspect, wait for, or cancel it.

Session IDs in these queries are exact. Use `find_session(name)` explicitly to
resolve a short name first. Exact matches take precedence; an ambiguous suffix
raises `ValueError`. Prefix filters on `list_session_summaries()` are literal.

A `SessionSummary` includes the active head, all `BranchInfo` records, entry count,
metadata, and append timestamps. `last_entry_at` records the latest history append,
not a later checkout or metadata edit. Each summary is consistent; the complete
list is not a cross-session transaction.

## Remove service branch pointers

Choose a nonempty literal prefix owned by your application. `prune_branches()`
always keeps the active branch and the names in `keep`. It removes only branch
pointers; history entries, images, files, and metadata remain available. `dry_run`
returns the selected names without applying the deletion. A later deletion checks
the current state again, so its returned names can differ from the preview.

::::{tab} Sync

<!--
name: test_prune_branches; fixtures: doc_api
```python
from contree_sdk.store import SyncSQLiteStore

with SyncSQLiteStore("prune.db") as initial:
    root = initial.append("demo", image_uuid="base", parent_id=None)
    initial.create_branch("demo", "temporary:old")
    initial.create_branch("demo", "temporary:keep")
```
-->

```python
from contree_sdk.store import SyncSQLiteStore

with SyncSQLiteStore("prune.db") as store:
    candidates = store.prune_branches("demo", prefix="temporary:", keep=("temporary:keep",), dry_run=True)
    removed = store.prune_branches("demo", prefix="temporary:", keep=("temporary:keep",))
    head = store.resolve_history("demo")
```

<!--
name: test_prune_branches
```python
assert candidates == removed == ("temporary:old",)
assert head == root
with SyncSQLiteStore("prune.db") as reopened:
    assert reopened.list_branches("demo") == [("main", True), ("temporary:keep", False)]
```
-->

::::

::::{tab} Async

<!--
name: async test_prune_branches_async; fixtures: doc_api
```python
from contree_sdk.store import AsyncSQLiteStore

async with AsyncSQLiteStore("prune_async.db") as initial:
    root = await initial.append("demo", image_uuid="base", parent_id=None)
    await initial.create_branch("demo", "temporary:old")
    await initial.create_branch("demo", "temporary:keep")
```
-->

```python
from contree_sdk.store import AsyncSQLiteStore

async with AsyncSQLiteStore("prune_async.db") as store:
    candidates = await store.prune_branches("demo", prefix="temporary:", keep=("temporary:keep",), dry_run=True)
    removed = await store.prune_branches("demo", prefix="temporary:", keep=("temporary:keep",))
    head = await store.resolve_history("demo")
```

<!--
name: test_prune_branches_async
```python
assert candidates == removed == ("temporary:old",)
assert head == root
async with AsyncSQLiteStore("prune_async.db") as reopened:
    assert await reopened.list_branches("demo") == [("main", True), ("temporary:keep", False)]
```
-->

::::

## Coordinate concurrent work

A saved run commits against the branch position captured when it starts.
If another run advances that position first, `SessionConflictError` prevents a
silent overwrite. Filesystem changes are not automatically merged.

Serialize dependent commands. For independent work, create separate branches and
coordinate access to the store's active branch. Two session objects sharing a
`session_id` also share that active branch; they are not isolated workspaces.

Use `switch_branch()` before running on an existing branch. The `branch=` option
on a saved `run()` can create and select a new branch for its result. It cannot
replace an existing different branch. See {doc}`troubleshooting` for conflict recovery.

To keep branches across Python restarts, use {doc}`sessions`.
