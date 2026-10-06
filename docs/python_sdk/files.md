---
icon: file-arrow-up
---

# Upload inputs and download results

Use `run(files=...)` to attach local content before a command starts.
Use `read_file()` to download a file from the session's current image.

This example uploads bytes as `/input.txt`, copies them to `/output.txt` remotely,
and saves the result as `output.txt` in your local working directory.
Use the connection variables from {doc}`getting-started`.

::::{tab} Sync

<!--
name: test_files; fixtures: doc_api, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a file!\n")
```
-->

```python
import os
from pathlib import Path

from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession


def main() -> None:
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
        session.run(
            shell="cat /input.txt > /output.txt",
            files={"/input.txt": b"Hello from a file!\n"},
            disposable=False,
        )
        content = session.read_file("/output.txt")
        Path("output.txt").write_bytes(content)
        print(content.decode(), end="")


main()
```

<!--
name: test_files
```python
assert Path("output.txt").read_bytes() == b"Hello from a file!\n"
assert doc_api.sync.calls_for("inspect_image_download")[0].args == ("image-1", "/output.txt")
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["disposable"] is False
assert doc_api.sync.calls_for("ensure_file")[0].args == (b"Hello from a file!\n",)
assert capsys.readouterr().out == "Hello from a file!\n"
```
-->

::::

::::{tab} Async

<!--
name: test_files_async; fixtures: doc_api, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a file!\n")
```
-->

```python
import asyncio
import os
from pathlib import Path

from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession


async def main() -> None:
    async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
        await session.run(
            shell="cat /input.txt > /output.txt",
            files={"/input.txt": b"Hello from a file!\n"},
            disposable=False,
        )
        content = await session.read_file("/output.txt")
        await asyncio.to_thread(Path("output.txt").write_bytes, content)
        print(content.decode(), end="")


asyncio.run(main())
```

<!--
name: test_files_async
```python
assert Path("output.txt").read_bytes() == b"Hello from a file!\n"
assert doc_api.async_client.calls_for("inspect_image_download")[0].args == ("image-1", "/output.txt")
assert doc_api.async_client.calls_for("spawn_instance")[0].kwargs["disposable"] is False
assert doc_api.async_client.calls_for("ensure_file")[0].args == (b"Hello from a file!\n",)
assert capsys.readouterr().out == "Hello from a file!\n"
```
-->

::::

Both stdout and the local `output.txt` contain `Hello from a file!` followed by a newline.
The command uses `disposable=False`, so `read_file()` sees the image produced by that command.
With a disposable run, it would still read the previous image.

:::{note}
Async snippets with top-level `await` run inside an async function or a notebook
that supports it. For a standalone script, use the `asyncio.run(main())` structure
from {doc}`getting-started`.
:::

## Choose a file source

| Input                                     | Meaning                                                    |
| ----------------------------------------- | ---------------------------------------------------------- |
| `files={"/input.txt": b"content"}`        | Upload bytes directly.                                     |
| `files={"/input.txt": "local.txt"}`       | Read a local file; the string is a path, not file content. |
| `files={"/input.txt": Path("local.txt")}` | Read a local file using a path object.                     |
| `files=["local.txt"]`                     | Upload the file to `/local.txt`.                           |
| `files={"/tool.sh": UploadFileSpec(...)}` | Set file ownership and mode.                               |

Destination paths refer to the remote filesystem. Source paths refer to your local
machine. A duplicate destination in a list raises `ValueError` before execution.
The standard transfer component uses the client's `ensure_file()` to reuse uploads
by content. A saved upload does not by itself change a session image.

See {doc}`running-commands` for stdin, and {doc}`customization` to replace file transfer.

## Upload an executable script

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
import os
from contree_client.models import StreamRepr
from contree_sdk.files import UploadFileSpec

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    script = UploadFileSpec(source=b"#!/bin/sh\necho 'script output'\n", mode=0o755)
    result = session.run("/tool.sh", files={"/tool.sh": script})
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
import os
from contree_client.models import StreamRepr
from contree_sdk.files import UploadFileSpec

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    script = UploadFileSpec(source=b"#!/bin/sh\necho 'script output'\n", mode=0o755)
    result = await session.run("/tool.sh", files={"/tool.sh": script})
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

## Stage files for a later command

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
from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession
from contree_sdk.files import UploadFileSpec
from contree_sdk.store import SyncSQLiteStore

with ContreeClient.from_profile() as client:
    with SyncSQLiteStore("staging.db") as store:
        session = ContreeSession(client, image="tag:tutorial-base", session_id="edit-demo", store=store)
        staged = session.stage_files(
            {
                "/work/config.ini": UploadFileSpec(source=b"mode=test\n", uid=1000, gid=1000, mode=0o640),
            }
        )
        pending = session.pending_files()
        assert pending[0].mode == 0o640

    with SyncSQLiteStore("staging.db") as store:
        session = ContreeSession(client, session_id="edit-demo", store=store)
        assert session.pending_files() == pending
        session.run(shell="cat /work/config.ini", disposable=False)
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
    assert reopened.pending_files("edit-demo") == pending
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
from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession
from contree_sdk.files import UploadFileSpec
from contree_sdk.store import AsyncSQLiteStore

async with ContreeAsyncClient.from_profile() as client:
    async with AsyncSQLiteStore("staging-async.db") as store:
        session = ContreeAsyncSession(client, image="tag:tutorial-base", session_id="edit-demo", store=store)
        staged = await session.stage_files(
            {
                "/work/config.ini": UploadFileSpec(source=b"mode=test\n", uid=1000, gid=1000, mode=0o640),
            }
        )
        pending = await session.pending_files()
        assert pending[0].mode == 0o640

    async with AsyncSQLiteStore("staging-async.db") as store:
        session = ContreeAsyncSession(client, session_id="edit-demo", store=store)
        assert await session.pending_files() == pending
        await session.run(shell="cat /work/config.ini", disposable=False)
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
    assert await reopened.pending_files("edit-demo") == pending
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

Concurrent changes to the target branch raise `SessionConflictError`. The operation
still has its result and context, so it can be committed to a new branch with
`commit_result(operation, branch="result")`. Do not retry a stale commit against
the changed branch without choosing which history to retain.

`read_file()` reads the current image; staged attachments appear there only after a
committed run. For `LazySession`, pending attachments enter the VM at startup and
are consumed when its snapshot commits. Stage inputs before starting that VM.

Custom integrations can use `store.stage_files(session_id, attachments, branch=...)`
with public `StagedFile` values for already uploaded content. Store-level
`pending_files()` accepts a history ID or exact branch name. Both native sync and
async stores provide these methods. The store does not verify whether an uploaded
UUID still exists on the server.

## Prepare directory trees and stream large files

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
local file. Use a saved profile as described in {doc}`getting-started`.

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

from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession
from contree_sdk.files import ClientFileTransfer, prepare_file_tree

Path("project").mkdir()
Path("project/input.txt").write_text("hello\n")
Path("project/ignored.tmp").write_text("excluded")
files = prepare_file_tree("project", "/app", exclude=("*.tmp",), mode=0o640)
progress = []
with ContreeClient.from_profile() as client:
    transfer = ClientFileTransfer(client, max_concurrency=2, on_progress=progress.append)
    session = ContreeSession(client, image="tag:tutorial-base", file_transfer=transfer)
    session.run(shell="cat /app/input.txt > /result.txt", files=files, disposable=False)
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

from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession
from contree_sdk.files import AsyncClientFileTransfer, prepare_file_tree

await asyncio.to_thread(Path("project").mkdir)
await asyncio.to_thread(Path("project/input.txt").write_text, "hello\n")
await asyncio.to_thread(Path("project/ignored.tmp").write_text, "excluded")
files = await asyncio.to_thread(partial(prepare_file_tree, "project", "/app", exclude=("*.tmp",), mode=0o640))
progress = []
async with ContreeAsyncClient.from_profile() as client:
    transfer = AsyncClientFileTransfer(client, max_concurrency=2, on_progress=progress.append)
    session = ContreeAsyncSession(client, image="tag:tutorial-base", file_transfer=transfer)
    await session.run(shell="cat /app/input.txt > /result.txt", files=files, disposable=False)
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
