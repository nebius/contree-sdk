---
icon: diagram-project
---

# Control a running sandbox

Use `run()` when you only need a completed result. Use `spawn()` to obtain an
operation handle immediately, stream output, send input, or cancel work.
Enter an operation context to start additional processes in the same running sandbox.

:::{note}
Async snippets with top-level `await` run inside an async function or a notebook
that supports it. For a standalone script, use the `asyncio.run(main())` structure
from {doc}`getting-started`.
:::

## Run an additional process

This program keeps a sandbox alive with `sleep`, runs `echo` inside it, and streams
the output locally. Use the connection variables from {doc}`getting-started`.

::::{tab} Sync

<!--
name: test_processes; fixtures: doc_api, capsys
```python
doc_api.subprocess()
```
-->

```python
import os
import sys

from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession


def main() -> None:
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
        operation = session.spawn(shell="sleep 300", timeout=60)
        with operation:
            process = operation.run("echo", args=["Hello from a subprocess!"])
            process.pipe_to(stdout=sys.stdout, stderr=sys.stderr)


main()
```

<!--
name: test_processes
```python
assert doc_api.sync.calls_for("operation_subprocess_create")[0].args == ("operation-1", "echo")
assert doc_api.sync.calls_for("operation_subprocess_create")[0].kwargs["args"] == ["Hello from a subprocess!"]
assert capsys.readouterr().out == "Hello from a subprocess!\n"
```
-->

::::

::::{tab} Async

<!--
name: test_processes_async; fixtures: doc_api, capsys
```python
doc_api.subprocess()
```
-->

```python
import asyncio
import os
import sys

from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession


async def main() -> None:
    async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
        operation = await session.spawn(shell="sleep 300", timeout=60)
        async with operation:
            process = await operation.run("echo", args=["Hello from a subprocess!"])
            await process.pipe_to(stdout=sys.stdout, stderr=sys.stderr)


asyncio.run(main())
```

<!--
name: test_processes_async
```python
assert doc_api.async_client.calls_for("operation_subprocess_create")[0].args == ("operation-1", "echo")
assert doc_api.async_client.calls_for("operation_subprocess_create")[0].kwargs["args"] == ["Hello from a subprocess!"]
assert capsys.readouterr().out == "Hello from a subprocess!\n"
```
-->

::::

On context exit, the SDK signals the main process, waits for shutdown, and attempts
cancellation if it does not stop. This happens even when the block raises an exception.
The subprocess shares the operation's live filesystem. It has its own `spid` and
result, but no separate session-history entry.

## Choose the right handle

| Call                                           | What you receive                                  |
| ---------------------------------------------- | ------------------------------------------------- |
| `session.run(...)`                             | A completed `InstanceResult`.                     |
| `session.spawn(...)`                           | An `OperationContract` for the main process.      |
| `operation.run(...)` inside a context          | A `SubprocessContract` for an additional process. |
| `await session.run(...)`                       | A completed `InstanceResult` in async code.       |
| `await session.spawn(...)`                     | An `AsyncOperationContract`.                      |
| `await operation.run(...)` inside `async with` | An `AsyncSubprocessContract`.                     |

Async `session.run()` also supports `async with`. Its pending call can be consumed
once. A sync `run()` returns a result and cannot be used as an operation context.

## Stream the main process

Iterate `operation.events()` when you need live output without additional processes.
Decode stream payloads before displaying them.

::::{tab} Sync

<!--
name: test_stream_events; fixtures: doc_api, capsys
```python
doc_api.subprocess(stdout="hello\n")
```
-->

```python
import os
from contree_client.models import EventDataStream

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = session.spawn(shell="echo hello")
    for event in operation.events():
        if event.type in {"stdout", "stderr"} and isinstance(event.data, EventDataStream):
            print(event.data.as_text(), end="")
    operation.wait()
```

<!--
name: test_stream_events
```python
assert capsys.readouterr().out == "hello\n"
assert doc_api.sync.calls_for("follow_operation_events")[0].args == ("operation-1",)
```
-->

::::

::::{tab} Async

<!--
name: async test_stream_events_async; fixtures: doc_api, capsys
```python
doc_api.subprocess(stdout="hello\n")
```
-->

```python
import os
from contree_client.models import EventDataStream

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = await session.spawn(shell="echo hello")
    async for event in operation.events():
        if event.type in {"stdout", "stderr"} and isinstance(event.data, EventDataStream):
            print(event.data.as_text(), end="")
    await operation.wait()
```

<!--
name: test_stream_events_async
```python
assert capsys.readouterr().out == "hello\n"
assert doc_api.async_client.calls_for("follow_operation_events")[0].args == ("operation-1",)
```
-->

::::

## Keep the result image

`spawn()` defaults to disposable execution, like `run()`. To retain an image, spawn
with `disposable=False`, wait for completion, then call `commit_result(operation)`.
::::{tab} Sync

<!--
name: test_manual_commit; fixtures: doc_api, capsys
```python
doc_api.complete()
```
-->

```python
import os

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = session.spawn(shell="echo saved > /saved.txt", disposable=False)
    result = operation.wait()
    entry = session.commit_result(operation, title="Save output")
    print(entry.image_uuid)
```

<!--
name: test_manual_commit
```python
assert session.image_uuid == "image-1"
assert entry.operation_uuid == "operation-1"
assert entry.title == "Save output"
assert capsys.readouterr().out == "image-1\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_manual_commit_async; fixtures: doc_api, capsys
```python
doc_api.complete()
```
-->

```python
import os

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = await session.spawn(shell="echo saved > /saved.txt", disposable=False)
    result = await operation.wait()
    entry = await session.commit_result(operation, title="Save output")
    print(entry.image_uuid)
```

<!--
name: test_manual_commit_async
```python
assert session.image_uuid == "image-1"
assert entry.operation_uuid == "operation-1"
assert entry.title == "Save output"
assert capsys.readouterr().out == "image-1\n"
```
-->

::::

A subprocess's writes can be part of that operation's final filesystem image; only
the whole operation creates a history entry.

A UUID-only handle can inspect, wait for, or cancel an existing operation. It has no
session history context, so `commit_result()` cannot use it. Keep the original
session-created handle when you intend to commit.

A subprocess remembers its exit event. `wait()` after iteration does not wait for
another exit. Stream failures propagate to consumers. Operation `wait()` attempts
remote cancellation if waiting fails or is cancelled, while preserving the original error.

## Send input, then stop the main process

`send_stdin()` targets the main process unless you supply a subprocess `spid`.
Set `close=False` while sending more chunks; the final call closes remote stdin.
`signal()` sends a signal without waiting. `cancel()` requests operation cancellation.

::::{tab} Sync

<!--
name: test_operation_input; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="first chunk\nlast chunk\n")
```
-->

```python
import os

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = session.spawn("cat")
    operation.send_stdin("first chunk\n", close=False)
    operation.send_stdin("last chunk\n")
    result = operation.wait()
```

<!--
name: test_operation_input
```python
calls = doc_api.sync.calls_for("operation_subprocess_stdin")
assert [call.kwargs["close"] for call in calls] == [False, True]
assert all(call.args[:2] == ("operation-1", 1) for call in calls)
```
-->

::::

::::{tab} Async

<!--
name: async test_operation_input_async; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="first chunk\nlast chunk\n")
```
-->

```python
import os

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = await session.spawn("cat")
    await operation.send_stdin("first chunk\n", close=False)
    await operation.send_stdin("last chunk\n")
    result = await operation.wait()
```

<!--
name: test_operation_input_async
```python
calls = doc_api.async_client.calls_for("operation_subprocess_stdin")
assert [call.kwargs["close"] for call in calls] == [False, True]
assert all(call.args[:2] == ("operation-1", 1) for call in calls)
```
-->

::::

## Reattach to an operation by UUID

Save `operation.uuid` when another process must inspect or cancel work.
Construct a handle with the same UUID and a client for the same server. This does
not start a new operation or restore session history context.

<!--
name: test_reattach; fixtures: doc_api, capsys
```python
doc_api.complete()
```
-->

```python
import os
from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession
from contree_sdk.session import Operation

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = session.spawn("echo", args=["hello"])
    saved_uuid = operation.uuid
    reattached = Operation(client, saved_uuid)
    result = reattached.wait()
    print(reattached.uuid)
```

<!--
name: test_reattach
```python
assert len(doc_api.sync.calls_for("spawn_instance")) == 1
assert reattached.context is None
assert capsys.readouterr().out == "operation-1\n"
```
-->

Use `AsyncOperation` and await its methods for an async client.
