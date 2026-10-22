---
icon: terminal
---

# Work with a Session

The `session` returned by `create_sandbox_session` runs commands, saves
checkpoints, and switches between branches. Use the connection from
{doc}`getting-started`.

## Run commands and save a checkpoint

These two commands share one VM. `snapshot()` is a lightweight operation that
saves their files and stops the running VM. The next command starts from the
saved image. You can snapshot as often as needed, including after every command.

If the filesystem has not changed, a snapshot can return the same `image_uuid`.
This is normal: a new checkpoint does not require a new image UUID.

::::{tab} Sync

<!-- name: test_session_checkpoint; fixtures: sandbox_api, capsys -->

```python
"""Save filesystem changes as a session checkpoint."""

from contree_sdk import create_sandbox_session


def main() -> None:
    with create_sandbox_session(image="tag:alpine:latest") as session:
        # Start a VM and prepare files shared by both commands.
        session.run("mkdir", args=["-p", "/work"])
        session.run(shell="echo ready > /work/status.txt")

        # Save both commands as one checkpoint and stop the VM.
        checkpoint = session.snapshot()
        assert checkpoint is not None
        print(checkpoint.image_uuid)

        # Start a new VM from the checkpoint. The file is still there.
        session.run(shell="cat /work/status.txt")


main()
```

<!--
name: test_session_checkpoint
```python
assert capsys.readouterr().out == "image-op-1\n"
assert len(sandbox_api.sync.calls_for("operation_subprocess_create")) == 3
spawns = sandbox_api.sync.calls_for("spawn_instance")
assert len(spawns) == 2
assert spawns[1].args[1] == "image-op-1"
```
-->

::::

::::{tab} Async

<!-- name: test_session_checkpoint_async; fixtures: sandbox_api, capsys -->

```python
import asyncio

from contree_sdk import create_sandbox_session


async def main() -> None:
    async with create_sandbox_session(image="tag:alpine:latest") as session:
        # Start a VM and prepare files shared by both commands.
        await session.run("mkdir", args=["-p", "/work"])
        await session.run(shell="echo ready > /work/status.txt")

        # Save both commands as one checkpoint and stop the VM.
        checkpoint = await session.snapshot()
        assert checkpoint is not None
        print(checkpoint.image_uuid)

        # Start a new VM from the checkpoint. The file is still there.
        await session.run(shell="cat /work/status.txt")


asyncio.run(main())
```

<!--
name: test_session_checkpoint_async
```python
assert capsys.readouterr().out == "image-op-1\n"
assert len(sandbox_api.async_client.calls_for("operation_subprocess_create")) == 3
spawns = sandbox_api.async_client.calls_for("spawn_instance")
assert len(spawns) == 2
assert spawns[1].args[1] == "image-op-1"
```
-->

::::

The program prints the saved image UUID. Files survive a snapshot; processes and
memory do not. Normal context exit saves pending work. An exception aborts unsaved
work; completed snapshots remain available.

The default policy also saves after 10 idle seconds. Each snapshot is one
checkpoint, even when it contains several commands.

## Save after every command

Pass `session_type=ContreeSession` or `ContreeAsyncSession` to save each command
automatically. Each command runs in a separate VM, which stops when it finishes.
The next command starts from the saved image. No explicit `snapshot()` is needed.

::::{tab} Sync

<!--
name: test_save_every_command; fixtures: doc_api, capsys
```python
doc_api.complete()
doc_api.complete(stdout="ready\n")
```
-->

```python
from contree_sdk import ContreeSession, create_sandbox_session


with create_sandbox_session(image="tag:alpine:latest", session_type=ContreeSession) as session:
    # Write a file. The command finishes and saves its image automatically.
    session.run(shell="echo ready > /status.txt")

    # Start another VM from that image and read the saved file.
    result = session.run("cat", args=["/status.txt"])
    print(result.stdout.as_text(), end="")
```

<!--
name: test_save_every_command
```python
spawns = doc_api.sync.calls_for("spawn_instance")
assert [call.args[1] for call in spawns] == ["base-image", "image-1"]
assert all(call.kwargs["disposable"] is False for call in spawns)
assert session.image_uuid == "image-2"
assert capsys.readouterr().out == "ready\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_save_every_command_async; fixtures: doc_api, capsys
```python
doc_api.complete()
doc_api.complete(stdout="ready\n")
```
-->

```python
from contree_sdk import ContreeAsyncSession, create_sandbox_session


async with create_sandbox_session(image="tag:alpine:latest", session_type=ContreeAsyncSession) as session:
    # Write a file. The command finishes and saves its image automatically.
    await session.run(shell="echo ready > /status.txt")

    # Start another VM from that image and read the saved file.
    result = await session.run("cat", args=["/status.txt"])
    print(result.stdout.as_text(), end="")
```

<!--
name: test_save_every_command_async
```python
spawns = doc_api.async_client.calls_for("spawn_instance")
assert [call.args[1] for call in spawns] == ["base-image", "image-1"]
assert all(call.kwargs["disposable"] is False for call in spawns)
assert session.image_uuid == "image-2"
assert capsys.readouterr().out == "ready\n"
```
-->

::::

Set `disposable=True` on a command to leave the session image unchanged. The
default commit policy saves completed operations even when the command exits
with a nonzero code. Failed or cancelled operations do not advance history.

Use the default `LazySession` when commands need the same running processes.
It keeps the VM until a snapshot. Choose snapshot frequency to match the required
checkpoints and process lifetime. An unchanged filesystem can produce
the same image UUID in either mode.

## Start a new session from a snapshot

Each session builds an independent chain of saved images. Only the Store records
the links between history nodes and the positions of branches. An `image_uuid`
identifies saved files; it does not carry SDK session history.

You can start any number of new sessions from any history node's `image_uuid`,
or from any other image UUID you can access. Each session has its own history.
Changes in one session do not change the source image or other sessions.

::::{tab} Sync

<!--
name: test_session_from_snapshot; fixtures: sandbox_api, capsys
```python
sandbox_api.sync.mocks["resolve_image"].clear()
sandbox_api.sync.mock("resolve_image", "base")
sandbox_api.sync.mock("resolve_image", "image-op-1")
sandbox_api.command("baseline\n")
```
-->

```python
"""Use a saved image as the starting point of an independent session."""

from contree_sdk import create_sandbox_session


def main() -> None:
    # Prepare files in the original session and save their image UUID.
    with create_sandbox_session(image="tag:alpine:latest") as source:
        source.run(shell="echo baseline > /choice.txt")
        checkpoint = source.snapshot()
        assert checkpoint is not None
        image_uuid = checkpoint.image_uuid

    # Create a new session with those files and its own history.
    with create_sandbox_session(image=image_uuid) as fork:
        assert fork.session_id != source.session_id
        result = fork.run("cat", args=["/choice.txt"])
        print(result.stdout.as_text(), end="")

        # Change only the new session. The source image stays unchanged.
        fork.run(shell="echo experiment > /choice.txt")


main()
```

<!--
name: test_session_from_snapshot
```python
assert capsys.readouterr().out == "baseline\n"
spawns = sandbox_api.sync.calls_for("spawn_instance")
assert [call.args[1] for call in spawns] == ["base", "image-op-1"]
resolved = sandbox_api.sync.calls_for("resolve_image")
assert [call.args[0] for call in resolved] == ["tag:alpine:latest", "image-op-1"]
```
-->

::::

::::{tab} Async

<!--
name: test_session_from_snapshot_async; fixtures: sandbox_api, capsys
```python
sandbox_api.async_client.mocks["resolve_image"].clear()
sandbox_api.async_client.mock("resolve_image", "base")
sandbox_api.async_client.mock("resolve_image", "image-op-1")
sandbox_api.command("baseline\n")
```
-->

```python
import asyncio

from contree_sdk import create_sandbox_session


async def main() -> None:
    # Prepare files in the original session and save their image UUID.
    async with create_sandbox_session(image="tag:alpine:latest") as source:
        await source.run(shell="echo baseline > /choice.txt")
        checkpoint = await source.snapshot()
        assert checkpoint is not None
        image_uuid = checkpoint.image_uuid

    # Create a new session with those files and its own history.
    async with create_sandbox_session(image=image_uuid) as fork:
        assert fork.session_id != source.session_id
        result = await fork.run("cat", args=["/choice.txt"])
        print(result.stdout.as_text(), end="")

        # Change only the new session. The source image stays unchanged.
        await fork.run(shell="echo experiment > /choice.txt")


asyncio.run(main())
```

<!--
name: test_session_from_snapshot_async
```python
assert capsys.readouterr().out == "baseline\n"
spawns = sandbox_api.async_client.calls_for("spawn_instance")
assert [call.args[1] for call in spawns] == ["base", "image-op-1"]
resolved = sandbox_api.async_client.calls_for("resolve_image")
assert [call.args[0] for call in resolved] == ["tag:alpine:latest", "image-op-1"]
```
-->

::::

Reuse `image_uuid` in further `create_sandbox_session(image=image_uuid)` calls to
start more independent sessions. The source session can already be closed.
The new sessions do not inherit its history, branch names, or Store metadata.

If you share a Store, omit `session_id` to generate a new ID, or supply an unused
ID. An existing ID resumes that session instead; see {doc}`sessions`.

## Continue with a task

- {doc}`branching`: create a branch, compare results, and roll back a checkpoint.
- {doc}`sessions`: keep history in SQLite and resume after Python exits.
- {doc}`files`: upload inputs and read saved files.

History uses an in-memory Store by default. To resume later, supply a SQLite
Store and a stable `session_id`. Filesystem images remain on the ConTree server.
