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
assert len(doc_api.sync.calls_for("follow_operation_events")) == 1
assert not doc_api.sync.calls_for("wait_operation")
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
assert len(doc_api.async_client.calls_for("follow_operation_events")) == 1
assert not doc_api.async_client.calls_for("wait_operation")
```
-->

::::

## One reader per operation handle

`events()`, `wait()`, and subprocess handles share one unfiltered SSE reader.
It starts when the context is entered or when the first event iterator or wait is
consumed. A sync operation uses one reader thread; an async operation uses one task.
Transport reconnection remains the responsibility of `contree-client`.

Each `events()` iterator has an independent cursor. Events are retained in memory
for the lifetime of the handle, so a late subscriber can replay them without another
network stream. `since=N` selects event IDs greater than `N`; `spid=N` selects that
process. A process filter excludes the operation-wide `completion` event, but the
iterator still ends when the shared reader ends. Large event logs consume memory;
release completed handles when replay is no longer needed.

`wait()` uses the same reader and then fetches the final status once. Repeated waits
reuse that response. Closing or cancelling an event iterator only removes that
subscriber. A failed or cancelled operation `wait()` attempts remote cancellation
and therefore affects all consumers of the operation. Call `shutdown()` if you
stop consuming before completion and no longer need the operation.

Sharing applies to one `Operation` or `AsyncOperation` object. Constructing another
handle for the same UUID creates a separate owner and can open another stream.
Reuse the existing handle when consumers run in the same application.

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

## Stream input with bounded memory

Start the process with `stdin_open=True`. This keeps remote stdin open until you
send EOF. `pipe_stdin()` waits for that process's `spawn` event, sends chunks in
order, and sends an empty EOF request when the source ends. Its default maximum
input chunk size is 64 KiB after UTF-8 encoding. Base64 transport adds overhead.

Supply an iterable of `str` or `bytes` in sync code, or an async iterable in async
code. The SDK holds one source chunk at a time and splits large chunks before
sending them. To bound total input memory, keep the source's chunks bounded too.
`stdin=...` remains an eager initial payload; use `pipe_stdin()` for large files.

::::{tab} Sync

<!--
name: test_operation_input; fixtures: stdin_api
-->

```python
import os
from functools import partial

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = session.spawn("cat", stdin_open=True)
    with open("input.bin", "rb") as source:
        delivery = operation.pipe_stdin(iter(partial(source.read, 65536), b""))
    result = operation.wait()
```

<!--
name: test_operation_input
```python
from pathlib import Path

assert delivery.eof_sent
assert delivery.bytes_sent == Path("input.bin").stat().st_size
assert bytes(stdin_api.sync.received) == Path("input.bin").read_bytes()
assert len(stdin_api.sync.calls_for("follow_operation_events")) == 1
assert stdin_api.sync.calls_for("spawn_instance")[0].kwargs["stdin"].close is False
```
-->

::::

::::{tab} Async

<!--
name: async test_operation_input_async; fixtures: stdin_api
-->

```python
import asyncio
import os

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession


async def input_chunks():
    source = await asyncio.to_thread(open, "input.bin", "rb")
    try:
        while chunk := await asyncio.to_thread(source.read, 65536):
            yield chunk
    finally:
        await asyncio.to_thread(source.close)


async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    operation = await session.spawn("cat", stdin_open=True)
    source = input_chunks()
    try:
        delivery = await operation.pipe_stdin(source)
    finally:
        await source.aclose()
    result = await operation.wait()
```

<!--
name: test_operation_input_async
```python
from pathlib import Path

assert delivery.eof_sent
assert delivery.bytes_sent == Path("input.bin").stat().st_size
assert bytes(stdin_api.async_client.received) == Path("input.bin").read_bytes()
assert len(stdin_api.async_client.calls_for("follow_operation_events")) == 1
assert stdin_api.async_client.calls_for("spawn_instance")[0].kwargs["stdin"].close is False
```
-->

::::

`StdinResult.bytes_sent` counts bytes acknowledged by the server. It does not
prove that the process consumed them. `eof_sent` records successful EOF delivery.
If the shared reader observes an exit or operation completion before delivery
finishes, `process_exited` is true and the SDK stops sending input.

The caller owns the input source. A sync iterator can block inside `next()`;
the SDK checks for exit before and after that read but cannot interrupt arbitrary
blocking Python code. Use an interruptible source for live TTY input. Async
forwarding cancels a pending source read when the process exits. Sources must
cooperate with cancellation; cancelling `asyncio.to_thread()` does not stop its
underlying thread. The file example uses finite reads from a regular file.

Input-source errors, transport errors, and cancellation cancel the operation and
preserve the original exception. The SDK never retries stdin writes: a timeout
can mean that some bytes were delivered. An exit can race with a write and cause
a transport error instead of a `process_exited` result.

Use one writer per process. Set `close=False` on `pipe_stdin()` to deliver several
input batches before EOF. For a child process, use
`operation.run(..., stdin_open=True)` and pass its `spid` to `pipe_stdin()`.
`send_stdin()` remains a low-level single-write method; it does not wait for spawn
or manage input-source errors. Its default `close=True` sends EOF after that write.

`pipe_stdin()` returns after input delivery, without waiting for the operation.
Save `operation.uuid` if another owner will wait for completion. Do not enter an
operation context for this handoff: context exit stops the main process. The
shared reader remains active until completion or client closure. Input forwarding,
`events()`, and `wait()` on one handle use one transport subscription. The client
resumes that subscription after a connection loss; input is not replayed.

`signal()` sends a signal without waiting. `cancel()` requests operation
cancellation. `wait()` returns the typed `InstanceResult`, including nonzero
process exit codes. A cancelled operation raises `InterruptedError`; an operation
failure raises `FailedOperationError`.

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
