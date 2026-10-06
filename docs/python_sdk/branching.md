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
