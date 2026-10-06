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
