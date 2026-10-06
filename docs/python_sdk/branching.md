---
icon: code-branch
---

# Branch, switch, and roll back

With the default lazy session, call `snapshot()` before changing branches.
Snapshots are lightweight, so you can create a checkpoint after every command.
Each snapshot stops the VM; an unchanged filesystem can return the same
`image_uuid`. Rollback follows history entries, not distinct image UUIDs.

For automatic saving after each command, see
[Save after every command](session-model.md#save-after-every-command).
Configure your connection as shown in {doc}`getting-started`.

Branches share one session's history in its Store. To create an independent
session from any saved image, see
[Start a new session from a snapshot](session-model.md#start-a-new-session-from-a-snapshot).

## Create a branch and switch back

Save a baseline on `main`, change a file on `experiment`, then read the original
file from `main`. Creating a branch does not select it: call `switch_branch()`.

::::{tab} Sync

<!--
name: test_branches; fixtures: sandbox_api, capsys
```python
sandbox_api.download(b"candidate\n")
sandbox_api.download(b"baseline\n")
```
-->

```python
"""Compare a change with the saved baseline."""

from contree_sdk import create_sandbox_session


def main() -> None:
    with create_sandbox_session(image="tag:alpine:latest") as session:
        # Save the baseline on main.
        session.run(shell="echo baseline > /choice.txt")
        session.snapshot()

        # Create a branch at that checkpoint, then select it.
        session.create_branch("experiment", from_branch="main")
        session.switch_branch("experiment")

        # Change the file and save the result on experiment only.
        session.run(shell="echo candidate > /choice.txt")
        session.snapshot()
        print("experiment:", session.read_file("/choice.txt").decode().strip())

        # Select main's saved image. Its file still contains baseline.
        session.switch_branch("main")
        print("main:", session.read_file("/choice.txt").decode().strip())


main()
```

<!--
name: test_branches
```python
assert [call.args[0] for call in sandbox_api.sync.calls_for("inspect_image_download")] == [
    "image-op-2",
    "image-op-1",
]
assert sandbox_api.sync.calls_for("spawn_instance")[1].args[1] == "image-op-1"
assert capsys.readouterr().out == "experiment: candidate\nmain: baseline\n"
```
-->

::::

::::{tab} Async

<!--
name: test_branches_async; fixtures: sandbox_api, capsys
```python
sandbox_api.download(b"candidate\n")
sandbox_api.download(b"baseline\n")
```
-->

```python
import asyncio

from contree_sdk import create_sandbox_session


async def main() -> None:
    async with create_sandbox_session(image="tag:alpine:latest") as session:
        # Save the baseline on main.
        await session.run(shell="echo baseline > /choice.txt")
        await session.snapshot()

        # Create a branch at that checkpoint, then select it.
        await session.create_branch("experiment", from_branch="main")
        await session.switch_branch("experiment")

        # Change the file and save the result on experiment only.
        await session.run(shell="echo candidate > /choice.txt")
        await session.snapshot()
        print("experiment:", (await session.read_file("/choice.txt")).decode().strip())

        # Select main's saved image. Its file still contains baseline.
        await session.switch_branch("main")
        print("main:", (await session.read_file("/choice.txt")).decode().strip())


asyncio.run(main())
```

<!--
name: test_branches_async
```python
assert [call.args[0] for call in sandbox_api.async_client.calls_for("inspect_image_download")] == [
    "image-op-2",
    "image-op-1",
]
assert sandbox_api.async_client.calls_for("spawn_instance")[1].args[1] == "image-op-1"
assert capsys.readouterr().out == "experiment: candidate\nmain: baseline\n"
```
-->

::::

Output:

```text
experiment: candidate
main: baseline
```

Omit `from_branch` to branch from the current checkpoint. Switching branches
selects saved files; it does not rerun commands or restore processes.

## Roll back and keep a way back to the result

`rollback()` moves the active branch back one saved entry. Keep the current
result under another name before rolling back if you want to return to it later.

::::{tab} Sync

<!--
name: test_rollback; fixtures: sandbox_api, capsys
```python
sandbox_api.download(b"baseline\n")
sandbox_api.download(b"candidate\n")
```
-->

```python
"""Roll back one checkpoint and revisit the saved candidate."""

from contree_sdk import create_sandbox_session


def main() -> None:
    with create_sandbox_session(image="tag:alpine:latest") as session:
        # Save the first checkpoint on main.
        session.run(shell="echo baseline > /choice.txt")
        session.snapshot()

        # Save a second checkpoint with the changed file.
        session.run(shell="echo candidate > /choice.txt")
        session.snapshot()

        # Keep a name for the second checkpoint without switching branches.
        session.create_branch("saved-candidate")

        # Move main back one checkpoint and read the original file.
        session.rollback()
        print("after rollback:", session.read_file("/choice.txt").decode().strip())

        # Return to the second checkpoint through its saved branch name.
        session.switch_branch("saved-candidate")
        print("saved candidate:", session.read_file("/choice.txt").decode().strip())


main()
```

<!--
name: test_rollback
```python
assert [call.args[0] for call in sandbox_api.sync.calls_for("inspect_image_download")] == [
    "image-op-1",
    "image-op-2",
]
assert len(sandbox_api.sync.calls_for("spawn_instance")) == 2
assert capsys.readouterr().out == "after rollback: baseline\nsaved candidate: candidate\n"
```
-->

::::

::::{tab} Async

<!--
name: test_rollback_async; fixtures: sandbox_api, capsys
```python
sandbox_api.download(b"baseline\n")
sandbox_api.download(b"candidate\n")
```
-->

```python
import asyncio

from contree_sdk import create_sandbox_session


async def main() -> None:
    async with create_sandbox_session(image="tag:alpine:latest") as session:
        # Save the first checkpoint on main.
        await session.run(shell="echo baseline > /choice.txt")
        await session.snapshot()

        # Save a second checkpoint with the changed file.
        await session.run(shell="echo candidate > /choice.txt")
        await session.snapshot()

        # Keep a name for the second checkpoint without switching branches.
        await session.create_branch("saved-candidate")

        # Move main back one checkpoint and read the original file.
        await session.rollback()
        print("after rollback:", (await session.read_file("/choice.txt")).decode().strip())

        # Return to the second checkpoint through its saved branch name.
        await session.switch_branch("saved-candidate")
        print("saved candidate:", (await session.read_file("/choice.txt")).decode().strip())


asyncio.run(main())
```

<!--
name: test_rollback_async
```python
assert [call.args[0] for call in sandbox_api.async_client.calls_for("inspect_image_download")] == [
    "image-op-1",
    "image-op-2",
]
assert len(sandbox_api.async_client.calls_for("spawn_instance")) == 2
assert capsys.readouterr().out == "after rollback: baseline\nsaved candidate: candidate\n"
```
-->

::::

Output:

```text
after rollback: baseline
saved candidate: candidate
```

Use `rollback(steps=2)` to move back two entries. A snapshot can contain several
commands. Rollback keeps later history and other branches; new work starts from
the selected image. It does not undo external side effects or session-wide
`cwd` and `env` overrides.

Branch changes while a VM is active raise `RuntimeError`: snapshot first.
Duplicate branch names, unknown branches, and rollback beyond the initial entry
raise `ValueError`.

## Concurrent callers

Each Session owns its position and branch names. Objects using the same Store
and `session_id` can select different nodes without affecting each other.
Concurrent operations from one parent create separate children. No result moves
another client's position or overwrites its history.

Within one Session, a result advances the selected position only if that position
still matches its captured source and navigation has not changed. Late results
remain available by their entry IDs. Explicit `branch=` selects a local branch
for a normal commit. The SDK does not merge filesystem changes.

After restarting, select a saved `node_id`; a tree with multiple continuations
requires an explicit choice. `navigate_forward()` also requires a unique child.
See {doc}`sessions` for persistence and {doc}`reference/store` for the contract.
