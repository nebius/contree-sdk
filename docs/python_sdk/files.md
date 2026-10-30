---
icon: file-arrow-up
---

# Upload inputs and download results

Use `write_file(path, content)` to write bytes into the sandbox. It creates parent
directories and returns after the write completes. `read_file()` reads the active
VM without taking a snapshot. The next command reuses that VM, including its
running processes. A cold session reads its saved image; pending staged files
start a VM so reads include those inputs.

This example uploads bytes as `/input.txt`, copies them to `/output.txt` remotely,
and saves the result as `output.txt` in your local working directory.
Configure a connection as described in {ref}`sandbox-connection`.

::::{tab} Sync

<!--
name: test_files; fixtures: sandbox_api, capsys
```python
sandbox_api.command()
sandbox_api.download(b"Hello from a file!\n")
```
-->

```python
"""Write a file and download the result from the same VM."""

from pathlib import Path

from contree_sdk import create_sandbox_session


def main() -> None:
    with create_sandbox_session(image="tag:alpine:latest") as session:
        session.write_file("/input.txt", b"Hello from a file!\n")
        session.run(shell="cat /input.txt > /output.txt")
        content = session.read_file("/output.txt")
        Path("output.txt").write_bytes(content)
        print(content.decode(), end="")


main()
```

<!--
name: test_files
```python
assert Path("output.txt").read_bytes() == b"Hello from a file!\n"
assert sandbox_api.sync.calls_for("inspect_instance_download")[0].args == ("op-1", "/output.txt")
assert sandbox_api.sync.calls_for("spawn_instance")[0].kwargs["disposable"] is False
assert len(sandbox_api.sync.calls_for("operation_subprocess_create")) == 2
assert capsys.readouterr().out == "Hello from a file!\n"
```
-->

::::

::::{tab} Async

<!--
name: test_files_async; fixtures: sandbox_api, capsys
```python
sandbox_api.command()
sandbox_api.download(b"Hello from a file!\n")
```
-->

```python
import asyncio
from pathlib import Path

from contree_sdk import create_sandbox_session


async def main() -> None:
    async with create_sandbox_session(image="tag:alpine:latest") as session:
        await session.write_file("/input.txt", b"Hello from a file!\n")
        await session.run(shell="cat /input.txt > /output.txt")
        content = await session.read_file("/output.txt")
        await asyncio.to_thread(Path("output.txt").write_bytes, content)
        print(content.decode(), end="")


asyncio.run(main())
```

<!--
name: test_files_async
```python
assert Path("output.txt").read_bytes() == b"Hello from a file!\n"
assert sandbox_api.async_client.calls_for("inspect_instance_download")[0].args == ("op-1", "/output.txt")
assert sandbox_api.async_client.calls_for("spawn_instance")[0].kwargs["disposable"] is False
assert len(sandbox_api.async_client.calls_for("operation_subprocess_create")) == 2
assert capsys.readouterr().out == "Hello from a file!\n"
```
-->

::::

Both stdout and the local `output.txt` contain `Hello from a file!` followed by a newline.
`read_file()` sees both writes without stopping the VM. Normal context exit saves them.
With `ContreeSession`, each command saves by default; `disposable=True` leaves
the previous image selected.

:::{note}
Async snippets with top-level `await` run inside an async function or a notebook
that supports it. For a standalone script, use the `asyncio.run(main())` structure
from {doc}`getting-started`.
:::

Use `run(files={"/input.txt": Path("local.txt")}, command="cat", args=["/input.txt"])`
to make a local file available before the command starts. A `LazySession` applies
the file to its running VM, including on the first call; a `ContreeSession`
attaches it at operation startup. Directory sources expand into individual files
on both paths, so empty directories are omitted. Live placement uses mode `0644`
and the VM runtime user; explicit non-default `UploadFileSpec` ownership or mode
is rejected for `LazySession`.

## Advanced: choose a file source

| Input                                     | Meaning                                                    |
| ----------------------------------------- | ---------------------------------------------------------- |
| `files={"/input.txt": b"content"}`        | Upload bytes directly.                                     |
| `files={"/input.txt": "local.txt"}`       | Read a local file; the string is a path, not file content. |
| `files={"/input.txt": Path("local.txt")}` | Read a local file using a path object.                     |
| `files=["local.txt"]`                     | Upload the file to `/local.txt`.                           |
| `files={"/tool.sh": UploadFileSpec(...)}` | Set ownership and mode for startup attachments.            |

Destination paths refer to the remote filesystem. Source paths refer to your local
machine. A duplicate destination in a list raises `ValueError` before execution.
The standard transfer component uses the client's `ensure_file()` to reuse uploads
by content. A saved upload does not by itself change a session image.

See {doc}`customization` to replace file transfer.

## Advanced: upload an executable script

Use `UploadFileSpec` to set a mode. This example runs the uploaded script directly.
Its output is `script output`. It is disposable because the script is not needed
by a later command.

::::{tab} Sync

<!--
name: test_executable_upload; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="script output\n")
```
-->

```python
from contree_client.models import StreamRepr

from contree_sdk import ContreeSession, create_sandbox_session
from contree_sdk.files import UploadFileSpec


with create_sandbox_session(session_type=ContreeSession, image="tag:alpine:latest") as session:
    script = UploadFileSpec(source=b"#!/bin/sh\necho 'script output'\n", mode=0o755)
    result = session.run("/tool.sh", files={"/tool.sh": script}, disposable=True)
    if isinstance(result.stdout, StreamRepr):
        print(result.stdout.as_text(), end="")
```

<!--
name: test_executable_upload
```python
call = doc_api.sync.calls_for("spawn_instance")[0]
assert call.args[0] == "/tool.sh"
assert call.kwargs["files"]["/tool.sh"].mode == "0755"
assert doc_api.sync.calls_for("ensure_file")[0].args == (b"#!/bin/sh\necho 'script output'\n",)
assert capsys.readouterr().out == "script output\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_executable_upload_async; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="script output\n")
```
-->

```python
from contree_client.models import StreamRepr

from contree_sdk import ContreeAsyncSession, create_sandbox_session
from contree_sdk.files import UploadFileSpec


async with create_sandbox_session(session_type=ContreeAsyncSession, image="tag:alpine:latest") as session:
    script = UploadFileSpec(source=b"#!/bin/sh\necho 'script output'\n", mode=0o755)
    result = await session.run("/tool.sh", files={"/tool.sh": script}, disposable=True)
    if isinstance(result.stdout, StreamRepr):
        print(result.stdout.as_text(), end="")
```

<!--
name: test_executable_upload_async
```python
call = doc_api.async_client.calls_for("spawn_instance")[0]
assert call.args[0] == "/tool.sh"
assert call.kwargs["files"]["/tool.sh"].mode == "0755"
assert doc_api.async_client.calls_for("ensure_file")[0].args == (b"#!/bin/sh\necho 'script output'\n",)
assert capsys.readouterr().out == "script output\n"
```
-->

::::

## Advanced: stage files for a later command

`stage_files()` uploads content and appends a `stage` history entry. It does not
start a VM or change the image. `pending_files()` returns the uploaded UUID,
destination path, and permissions for each pending attachment.

Use a SQLite store to keep staging between processes. The next `run()` or `spawn()`
attaches pending files from its source history entry. Local sources are no longer
needed after staging succeeds.

This example stages a configuration file, closes the store, and resumes the session.
A committed run consumes the attachment. Rolling back that run restores the pending
attachment with its original permissions.

::::{tab} Sync

<!--
name: test_durable_staging; fixtures: doc_api
```python
doc_api.complete()
```
-->

```python
from contree_client import profiles
from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession
from contree_sdk.files import UploadFileSpec
from contree_sdk.store import SyncSQLiteStore


with ContreeClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client:
    with SyncSQLiteStore("staging.db") as store:
        session = ContreeSession(client, image="tag:alpine:latest", session_id="edit-demo", store=store)
        config_file = UploadFileSpec(source=b"mode=test\n", uid=1000, gid=1000, mode=0o640)
        staged = session.stage_files({"/work/config.ini": config_file})
        pending = session.pending_files()
        assert pending[0].mode == 0o640

    with SyncSQLiteStore("staging.db") as store:
        session = ContreeSession(client, session_id="edit-demo", store=store)
        assert session.pending_files() == pending
        session.run(shell="cat /work/config.ini")
        assert session.pending_files() == ()
        session.rollback()
        assert session.tip_id == staged.id
        assert session.pending_files() == pending
```

<!--
name: test_durable_staging
```python
assert len(doc_api.sync.calls_for("ensure_file")) == 1
assert len(doc_api.sync.calls_for("spawn_instance")) == 1
attached = doc_api.sync.calls_for("spawn_instance")[0].kwargs["files"]["/work/config.ini"]
assert (attached.uuid, attached.uid, attached.gid, attached.mode) == ("uploaded-file", 1000, 1000, "0640")
with SyncSQLiteStore("staging.db") as reopened:
    restored = ContreeSession(doc_api.sync, session_id="edit-demo", store=reopened, node_id=staged.id)
    assert restored.pending_files() == pending
```
-->

::::

::::{tab} Async

<!--
name: async test_durable_staging_async; fixtures: doc_api
```python
doc_api.complete()
```
-->

```python
from contree_client import profiles
from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession
from contree_sdk.files import UploadFileSpec
from contree_sdk.store import AsyncSQLiteStore


async with ContreeAsyncClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client:
    async with AsyncSQLiteStore("staging-async.db") as store:
        session = ContreeAsyncSession(client, image="tag:alpine:latest", session_id="edit-demo", store=store)
        config_file = UploadFileSpec(source=b"mode=test\n", uid=1000, gid=1000, mode=0o640)
        staged = await session.stage_files({"/work/config.ini": config_file})
        pending = await session.pending_files()
        assert pending[0].mode == 0o640

    async with AsyncSQLiteStore("staging-async.db") as store:
        session = ContreeAsyncSession(client, session_id="edit-demo", store=store)
        assert await session.pending_files() == pending
        await session.run(shell="cat /work/config.ini")
        assert await session.pending_files() == ()
        await session.rollback()
        assert session.tip_id == staged.id
        assert await session.pending_files() == pending
```

<!--
name: test_durable_staging_async
```python
assert len(doc_api.async_client.calls_for("ensure_file")) == 1
assert len(doc_api.async_client.calls_for("spawn_instance")) == 1
attached = doc_api.async_client.calls_for("spawn_instance")[0].kwargs["files"]["/work/config.ini"]
assert (attached.uuid, attached.uid, attached.gid, attached.mode) == ("uploaded-file", 1000, 1000, "0640")
async with AsyncSQLiteStore("staging-async.db") as reopened:
    restored = ContreeAsyncSession(doc_api.async_client, session_id="edit-demo", store=reopened, node_id=staged.id)
    assert await restored.pending_files() == pending
```
-->

::::

Staging follows history ancestry. A new branch inherits the pending files at its
starting entry. Staging another version of the same path changes only that branch.
Rolling back a staging entry restores the previous version, if one exists.

Explicit `run(files=...)` attachments take precedence over pending files with the
same destination. A committed result records all attached paths as applied, including
those explicit replacements. A disposable run, failed operation, cancelled operation,
or failed commit leaves the source staging available. Nonzero command exit codes
follow the session's normal commit behavior.

Concurrent operations retain their original parent. Their results become siblings;
a late result does not replace a newer local selection. Use
`commit_result(operation, branch="result")` to select its result explicitly.

`read_file()` reads the current image; staged attachments appear there only after a
committed run. For `LazySession`, pending attachments enter the VM at startup and
are consumed when its snapshot commits. Stage inputs before starting that VM.

Staging and pending-file resolution belong to Session. Store persists their nodes
without interpreting file attachments. Rollback changes only the local selection;
pass `node_id=staged.id` to resume that position in another process. Stored file
references do not guarantee that the uploaded UUID still exists on the server.

## Advanced: prepare directory trees and stream large files

Directory sources expand into regular-file attachments. For example,
`files={"/app": Path("project")}` uploads the contents of `project` under `/app`.
Use `prepare_file_tree()` for exclusions and ownership. It returns ordinary
`UploadFileSpec` objects that can be passed to a session or a transfer component.

Patterns match relative POSIX paths. Patterns without `/` also match basenames
at any depth; matching directories are excluded with their contents. Permission
bits are preserved unless `mode=` is supplied. Ownership defaults to uid=gid=0.
Symlinks and special files raise `ValueError`; empty directories are omitted because
spawn attachments represent files. Normalized destination conflicts are rejected
before uploads start, including a file that would be another file's parent.

Client-backed transfers send local files as binary streams. Keep source files
unchanged until the upload completes, or use {doc}`caching` for a stable temporary
snapshot. Bytes inputs are already in memory. `read_file()` still returns the
whole file; use `iter_file()` or `download_file()` for large results.

The examples upload a directory with an exclusion, then stream a result into a
local file. Configure a connection as described in {ref}`sandbox-connection`.

::::{tab} Sync

<!--
name: test_tree_and_stream; fixtures: doc_api
```python
doc_api.complete()
doc_api.sync.mock("inspect_image_download_stream", [b"hello", b"\n"])
```
-->

```python
from pathlib import Path

from contree_client import profiles
from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession
from contree_sdk.files import ClientFileTransfer, prepare_file_tree


Path("project").mkdir()
Path("project/input.txt").write_text("hello\n")
Path("project/ignored.tmp").write_text("excluded")
files = prepare_file_tree("project", "/app", exclude=("*.tmp",), mode=0o640)
progress = []
with ContreeClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client:
    transfer = ClientFileTransfer(client, max_concurrency=2, on_progress=progress.append)
    session = ContreeSession(client, image="tag:alpine:latest", file_transfer=transfer)
    session.run(shell="cat /app/input.txt > /result.txt", files=files)
    count = transfer.download_file(session.image_uuid, "/result.txt", "result.txt")
assert count == 6
assert Path("result.txt").read_bytes() == b"hello\n"
assert progress[-1].direction == "download"
assert progress[-1].bytes_transferred == 6
```

<!--
name: test_tree_and_stream
```python
assert len(doc_api.sync.calls_for("ensure_file")) == 1
attachments = doc_api.sync.calls_for("spawn_instance")[0].kwargs["files"]
assert set(attachments) == {"/app/input.txt"}
assert attachments["/app/input.txt"].mode == "0640"
assert doc_api.sync.calls_for("inspect_image_download_stream")[0].args == ("image-1", "/result.txt")
assert not doc_api.sync.calls_for("inspect_image_download")
```
-->

::::

::::{tab} Async

<!--
name: async test_tree_and_stream_async; fixtures: doc_api
```python
doc_api.complete()
doc_api.async_client.mock("inspect_image_download_stream", [b"hello", b"\n"])
```
-->

```python
import asyncio
from functools import partial
from pathlib import Path

from contree_client import profiles
from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession
from contree_sdk.files import AsyncClientFileTransfer, prepare_file_tree


await asyncio.to_thread(Path("project").mkdir)
await asyncio.to_thread(Path("project/input.txt").write_text, "hello\n")
await asyncio.to_thread(Path("project/ignored.tmp").write_text, "excluded")
files = await asyncio.to_thread(partial(prepare_file_tree, "project", "/app", exclude=("*.tmp",), mode=0o640))
progress = []
async with ContreeAsyncClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client:
    transfer = AsyncClientFileTransfer(client, max_concurrency=2, on_progress=progress.append)
    session = ContreeAsyncSession(client, image="tag:alpine:latest", file_transfer=transfer)
    await session.run(shell="cat /app/input.txt > /result.txt", files=files)
    count = await transfer.download_file(session.image_uuid, "/result.txt", "result.txt")
assert count == 6
assert await asyncio.to_thread(Path("result.txt").read_bytes) == b"hello\n"
assert progress[-1].bytes_transferred == 6
```

<!--
name: test_tree_and_stream_async
```python
assert len(doc_api.async_client.calls_for("ensure_file")) == 1
assert set(doc_api.async_client.calls_for("spawn_instance")[0].kwargs["files"]) == {"/app/input.txt"}
assert doc_api.async_client.calls_for("inspect_image_download_stream")[0].args == ("image-1", "/result.txt")
assert not doc_api.async_client.calls_for("inspect_image_download")
```
-->

::::

`max_concurrency` limits uploads within each `prepare_files()` call. Sync defaults
to one worker; async defaults to four. Sync callbacks run in upload worker threads
when concurrency exceeds one, so callbacks and custom clients must support that
usage. Async callbacks run on the event loop and must not block it. Upload events
report a completed file's size, including server deduplication. Download events
report cumulative bytes received for one file. Callbacks are synchronous and their
exceptions propagate.

An upload failure cancels queued work and joins active workers. Async cancellation
also joins local file I/O before closing files. Uploads already accepted by the
server are not undone. Concurrent calls have separate worker limits.

`download_file()` writes a temporary sibling, flushes it, and replaces the destination
only after the stream completes. Failure, cancellation, or a progress callback error
preserves the previous destination and removes the temporary file. The parent
directory must exist. The replacement uses private temporary-file permissions;
it does not retain the destination's previous mode. If you iterate `iter_file()`
directly, close it on early exit with `contextlib.closing()` or `aclosing()`.

`write_download()` and `write_download_async()` provide the same atomic local writer
for other byte iterables. These helpers do not own their input streams; the caller
must close them. Custom transfer backends can override `iter_file()`; its default
implementation buffers through `read_file()`.

## Inspect the active VM without stopping it

`LazySession.inspect()` returns a view of the current session. Each file request
selects the active VM or, when the session is cold, its saved image. Retaining the
view does not keep a VM running. Pending staged files start a VM before reading.

The view provides `list`, `grep`, `file_exists`, `archive_exists`, `read_file`,
`iter_file`, `download_file`, and `archive`. Paths use the filesystem root rather
than the command's working directory. File contents bypass the operation event log.
`download_file` replaces the local destination only after the complete transfer.

::::{tab} Sync

<!--
name: test_live_inspect; fixtures: sandbox_api
```python
sandbox_api.sync.mock("inspect_instance_download_stream", [b"result", b"\n"])
```
-->

```python
from contextlib import closing

from contree_sdk import create_sandbox_session


with create_sandbox_session(image="tag:alpine:latest") as session:
    session.write_file("/result.txt", b"result\n")
    view = session.inspect()
    with closing(view.iter_file("/result.txt")) as chunks:
        content = b"".join(chunks)
    assert content == b"result\n"
    assert session.phase == "running"
    saved = session.inspect_snapshot()
    assert session.phase == "cold"
    image_uuid = saved.image_uuid
```

<!--
name: test_live_inspect
```python
assert sandbox_api.sync.calls_for("inspect_instance_download_stream")[0].args == ("op-1", "/result.txt")
assert image_uuid == "image-op-1"
```
-->

::::

::::{tab} Async

<!--
name: async test_live_inspect_async; fixtures: sandbox_api
```python
sandbox_api.async_client.mock("inspect_instance_download_stream", [b"result", b"\n"])
```
-->

```python
from contextlib import aclosing

from contree_sdk import create_sandbox_session


async with create_sandbox_session(image="tag:alpine:latest") as session:
    await session.write_file("/result.txt", b"result\n")
    view = await session.inspect()
    async with aclosing(view.iter_file("/result.txt")) as chunks:
        content = b"".join([chunk async for chunk in chunks])
    assert content == b"result\n"
    assert session.phase == "running"
    saved = await session.inspect_snapshot()
    assert session.phase == "cold"
    image_uuid = saved.image_uuid
```

<!--
name: test_live_inspect_async
```python
assert sandbox_api.async_client.calls_for("inspect_instance_download_stream")[0].args == ("op-1", "/result.txt")
assert image_uuid == "image-op-1"
```
-->

::::

Close streams when iteration stops early. Snapshot and normal session close wait
for accepted live requests, including their streams. File requests count as idle
activity; they do not increase `CommandCountSnapshotPolicy`'s command count.
Requests arriving during a snapshot wait for it to finish. `inspect(timeout=...)`
limits that admission and startup wait; client settings control HTTP timeouts.
Live errors propagate without reading an older image as a fallback.

Live reads can observe concurrent writes. They are not filesystem snapshots.
Live grep also differs from image grep in regex support, encoding, ignore rules,
and highlight spans. Unsupported patterns raise an error; check `truncated` on
successful results. The live API limits transfers to 300 seconds and directory
listings to 10,000 entries. Use `inspect_snapshot()` for a stable image view;
its `image_uuid` remains fixed across later commands. Image metadata through
`view.info()` requires this same snapshot and stops the VM.
