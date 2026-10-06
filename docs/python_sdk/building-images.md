---
icon: file-code
---

# Build an image from a Dockerfile

Use a Docker builder when your setup already lives in a Dockerfile.
It runs build steps on ConTree and returns an image UUID for new sessions.
You do not need a local Docker daemon.

:::{note}
Async snippets with top-level `await` run inside an async function or a notebook
that supports it. For a standalone script, use the `asyncio.run(main())` structure
from {doc}`getting-started`.
:::

## Create a small build context

Use the connection variables from {doc}`getting-started`. `CONTREE_IMAGE` must
refer to an imported image with a POSIX shell and `cat`.
Create `build-context/Dockerfile`:

```dockerfile
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY message.txt /message.txt
RUN cat /message.txt > /built.txt
```

Create `build-context/message.txt` with this content and a final newline:

```text
Hello from a built image!
```

## Build and read the result

Run this code from the directory containing `build-context`. The SQLite databases
retain build history and upload-cache entries for later invocations.

::::{tab} Sync

<!--
name: test_build; fixtures: doc_api, doc_build_context, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a built image!\n")
for client in (doc_api.sync, doc_api.async_client):
    client.mock("resolve_image", "image-1")
```
-->

```python
import os
from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession
from contree_sdk.cache import SyncSQLiteCache
from contree_sdk.docker import ContreeDockerBuilder
from contree_sdk.store import SyncSQLiteStore

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    with SyncSQLiteStore("build-history.db") as store, SyncSQLiteCache("build-cache.db") as cache:
        builder = ContreeDockerBuilder(client, store=store, cache=cache)
        image_uuid = builder.build(
            "build-context",
            build_args={"BASE_IMAGE": os.environ["CONTREE_IMAGE"]},
            session_id="tutorial-build",
        )
        session = ContreeSession(client, image=image_uuid)
        print(session.read_file("/built.txt").decode(), end="")
```

<!--
name: test_build
```python
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["disposable"] is False
from pathlib import Path

source_file = doc_api.sync.calls_for("ensure_file")[0].args[0]
assert Path(source_file.name).read_bytes() == b"Hello from a built image!\n"
assert doc_api.sync.calls_for("inspect_image_download")[0].args == ("image-1", "/built.txt")
assert capsys.readouterr().out == "Hello from a built image!\n"
```
-->

::::
::::{tab} Async

<!--
name: async test_build_async; fixtures: doc_api, doc_build_context, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a built image!\n")
for client in (doc_api.sync, doc_api.async_client):
    client.mock("resolve_image", "image-1")
```
-->

```python
import os
from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession
from contree_sdk.cache import AsyncSQLiteCache
from contree_sdk.docker import ContreeAsyncDockerBuilder
from contree_sdk.store import AsyncSQLiteStore

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    async with AsyncSQLiteStore("build-history.db") as store, AsyncSQLiteCache("build-cache.db") as cache:
        builder = ContreeAsyncDockerBuilder(client, store=store, cache=cache)
        image_uuid = await builder.build(
            "build-context",
            build_args={"BASE_IMAGE": os.environ["CONTREE_IMAGE"]},
            session_id="tutorial-build",
        )
        session = ContreeAsyncSession(client, image=image_uuid)
        print((await session.read_file("/built.txt")).decode(), end="")
```

<!--
name: test_build_async
```python
assert doc_api.async_client.calls_for("spawn_instance")[0].kwargs["disposable"] is False
assert doc_api.async_client.calls_for("ensure_file")[0].args == (b"Hello from a built image!\n",)
assert doc_api.async_client.calls_for("inspect_image_download")[0].args == ("image-1", "/built.txt")
assert capsys.readouterr().out == "Hello from a built image!\n"
```
-->

::::

The output is `Hello from a built image!`. Changing `message.txt` changes the input
hash and invalidates the dependent layer. Reusing the same store and build session
allows an unchanged layer to be reused.

## Understand the two caches

| Component | What it records                                           |
| --------- | --------------------------------------------------------- |
| `store=`  | History and branch pointers used to reuse built layers.   |
| `cache=`  | Uploaded-file and URL-download metadata used by COPY/ADD. |

Memory implementations are the default. Use both SQLite components to retain
these records between Python processes. Keep referenced images and uploaded files
available on the server. `no_cache=True` disables layer reuse; it does not force
identical file content to be uploaded again.

The default build session ID derives from the context path. Supply `session_id=`
when you need a stable identity after moving a context. Avoid concurrent builds
that mutate the same build session.

## Supported Dockerfile behavior

`FROM`, `RUN`, `COPY`, `ADD`, `WORKDIR`, `ENV`, `ARG`, and `USER` are implemented.
The builder supports multiple stages, `COPY --from`, `.dockerignore`, and build
arguments. It interprets a subset of Dockerfile syntax, not the complete Docker build specification.

`CMD`, `ENTRYPOINT`, `LABEL`, `EXPOSE`, `VOLUME`, `STOPSIGNAL`, `MAINTAINER`,
`HEALTHCHECK`, `ONBUILD`, and `SHELL` are accepted but have no effect.
Unknown instructions raise `ValueError`. A nonzero `RUN` exit raises `DockerBuildError`.

The output is a filesystem image. Startup instructions and Docker configuration
are not reproduced. `ENV`, `WORKDIR`, and `USER` guide build steps; pass the desired
runtime environment and working directory when executing the resulting image.
`WORKDIR` sets a command's directory; ensure the directory exists in the image.

## Observe a live build

Pass `on_event=` to receive `BuildEvent` notifications while a build runs.
Output events arrive before RUN completes and carry raw `bytes`. Decode or format
them in your application. Each operation uses the same reader for output and its
final result.

| `event.type`        | Meaning                                                           |
| ------------------- | ----------------------------------------------------------------- |
| `step_started`      | A parsed or synthetic directive is about to execute.              |
| `operation_started` | RUN submitted an operation; `operation_uuid` is available.        |
| `stdout`, `stderr`  | A chunk of live output is in `event.data`.                        |
| `cache_hit`         | The directive reused an existing image without starting RUN.      |
| `step_completed`    | The directive completed, including any required history commit.   |
| `step_failed`       | The directive raised; `event.error` holds the original exception. |

`event.step.id` is unique within one build. `event.step.index` is the zero-based
parsed directive index, including ARG and metadata instructions. Synthetic steps
have `index=None`. A nested step has `parent_id` set to its enclosing step's ID.
A final COPY/ADD flush appears as a synthetic `RUN :`; a stage flush appears as a
child of the next FROM. If a nested step fails, both it and its parent report the
same exception.

Events include elapsed step time, image IDs, and the operation UUID when available.
The terminal RUN event also contains its typed `InstanceResult`, including nonzero
exit codes. A cache hit emits no output and no new operation UUID.

::::{tab} Sync

<!--
name: test_build_events; fixtures: doc_api, doc_build_context, capsys
```python
from dataclasses import replace
from contree_client.models import EventDataStream
from tests.unit.session.lazy_clients import event

doc_api.complete(stream=False)
doc_api.sync.mock("follow_operation_events", [
    replace(event("stdout"), data=EventDataStream.from_text("building\n")),
    event("completion"),
])
```
-->

```python
import os
import sys
from contree_client.sync import ContreeClient
from contree_sdk.docker import BuildEvent, ContreeDockerBuilder


def report(event: BuildEvent) -> None:
    if event.type == "stdout":
        sys.stdout.buffer.write(event.data)
        sys.stdout.buffer.flush()
    elif event.type == "stderr":
        sys.stderr.buffer.write(event.data)
        sys.stderr.buffer.flush()
    elif event.type == "step_started":
        print(f"Step {event.step.id}: {event.step.keyword}", flush=True)


with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    builder = ContreeDockerBuilder(client)
    image_uuid = builder.build(
        "build-context",
        build_args={"BASE_IMAGE": os.environ["CONTREE_IMAGE"]},
        on_event=report,
    )
```

<!--
name: test_build_events
```python
assert image_uuid == "image-1"
assert "building\n" in capsys.readouterr().out
assert len(doc_api.sync.calls_for("follow_operation_events")) == 1
```
-->

::::
::::{tab} Async

<!--
name: async test_build_events_async; fixtures: doc_api, doc_build_context, capsys
```python
from dataclasses import replace
from contree_client.models import EventDataStream
from tests.unit.session.lazy_clients import event

doc_api.complete(stream=False)
doc_api.async_client.mock("follow_operation_events", [
    replace(event("stdout"), data=EventDataStream.from_text("building\n")),
    event("completion"),
])
```
-->

```python
import asyncio
import os
import sys
from contree_client.asyncio import ContreeAsyncClient
from contree_sdk.docker import BuildEvent, ContreeAsyncDockerBuilder


async def report(event: BuildEvent) -> None:
    if event.type in {"stdout", "stderr"}:
        stream = sys.stdout.buffer if event.type == "stdout" else sys.stderr.buffer
        await asyncio.to_thread(stream.write, event.data)
        await asyncio.to_thread(stream.flush)
    elif event.type == "step_started":
        await asyncio.to_thread(print, f"Step {event.step.id}: {event.step.keyword}", flush=True)


async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    builder = ContreeAsyncDockerBuilder(client)
    image_uuid = await builder.build(
        "build-context",
        build_args={"BASE_IMAGE": os.environ["CONTREE_IMAGE"]},
        on_event=report,
    )
```

<!--
name: test_build_events_async
```python
assert image_uuid == "image-1"
assert "building\n" in capsys.readouterr().out
assert len(doc_api.async_client.calls_for("follow_operation_events")) == 1
```
-->

::::

Callbacks run serially in the thread or task executing `build()`. The async builder
accepts both synchronous and awaitable callbacks. Keep callbacks short. The async
example offloads local output writes so they do not block the event loop. For a
live UI, a callback can also feed a bounded queue that another task consumes.

A callback error, including a closed output pipe, aborts the build and cancels its
active RUN operation. Async task cancellation and sync interruption follow the
same cleanup path. Error notifications cannot replace the original exception.
Callbacks do not roll back completed layers. File, parse, and final tag errors
raise directly; these do not create directive events outside a running step.

## Customize a build

Pass `on_step=` to receive a `BuildStepEvent` for each parsed directive. It includes
duration, cache-hit status, image IDs, and any error. Keep callbacks short; a callback
exception can stop the build. The async builder also accepts an awaitable callback.

Use `parser=`, `session_factory=`, or `execute_directive()` for custom behavior.
See {doc}`customization` and {doc}`reference/docker`.

## Upload cache lifetime and scope

COPY and ADD cache uploads separately from layer history. The cache namespaces
and layer hashes include the endpoint, project, and credential scope. Shared
cache files and build session IDs therefore do not reuse another server’s UUIDs.
Local paths and source URLs are retained through the public file-source registry.
See {doc}`caching` for enumeration and invalidation.

The default upload lifetime is 90 days. Cache hits and URL responses with status
304 do not extend it. Override `create_context()` and set
`context.upload_cache_ttl` to choose a shorter lifetime for your server. Expiry
causes a new upload when the directive runs; it does not invalidate an existing
image layer. A 304 response without a live cached upload raises `DockerBuildError`.
