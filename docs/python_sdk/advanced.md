---
icon: sliders
---

# Advanced usage

The sandbox and image helpers manage clients, stores, and cleanup.
Use the options below when you need to select components or control their behavior.
For basic workflows, start with {doc}`getting-started`, {doc}`images`, and
{doc}`building-images`. Connection settings remain in {ref}`sandbox-connection`;
{ref}`shared-image-client` shows one client shared across all three workflows.

For the workflow itself, continue with {doc}`Work with a Session <session-model>`:
save checkpoints, compare branches, roll back experiments, and resume saved work.

## What each component does

| Component                            | Purpose                                                                                                                              | Read more                                                         |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| **Store** (`store=` in helpers)      | Keeps history, uploaded-file references, and imported images in typed trees. Supports resume and result reuse.                       | {doc}`sessions` and {doc}`reference/store`                        |
| **Client** (`client=`)               | Sends requests to ConTree using your endpoint, credentials, and project. One client can serve import, build, and sandbox operations. | {ref}`shared-image-client`                                        |
| **Session**                          | Tracks the current image and history. `ContreeSession` runs each command as a separate operation and can save its result.            | {doc}`session-model`                                              |
| **LazySession**                      | Keeps commands in one running VM until a snapshot. This is the default session behind `create_sandbox_session`.                      | {doc}`session-model`                                              |
| **Operation**                        | Gives access to one remote operation: wait for completion, run subprocesses, read output, or stop it.                                | {doc}`operation`                                                  |
| **FileTransfer** (`file_transfer=`)  | Prepares uploads and reads files from saved images. It does not access unsaved files inside a running VM.                            | {doc}`files` and {doc}`reference/files`                           |
| **Snapshot policy**                  | Decides when a lazy session saves filesystem changes and stops its VM.                                                               | {doc}`reference/session`                                          |
| **Commit policy** (`commit_policy=`) | Decides whether a completed operation's result becomes part of session history.                                                      | [Select a commit policy](customization.md#select-a-commit-policy) |
| **Docker builder**                   | Executes Dockerfile instructions and returns an image UUID. It uses Store trees for layer history and uploaded results.              | {doc}`building-images` and {doc}`reference/docker`                |

A memory Store keeps history only for that store instance. A SQLite Store keeps
it across Python restarts. The filesystem images themselves remain on the ConTree
server. Deleting an upload-cache tree removes its reuse records without changing session history.

Sandbox history and upload reuse share a memory Store by default. The
import and build helpers use a persistent SQLite Store by default. See
{doc}`manual-sandbox` for component construction and ownership.

### Bring your own storage

`SyncStore` and `AsyncStore` are the public storage interfaces. The SDK includes
Memory and SQLite implementations. Subclass the matching interface to implement
Redis or PostgreSQL storage. One Store holds both history and reusable results.
Tree kinds separate their purposes.

Store contains typed trees of immutable nodes. Session owns the selected position
and local branch names. See [Implement history storage](customization.md#implement-history-storage)
for atomic insertion, pagination, and retention requirements.

Pass your Store through `store=` to helpers, sessions, and builders. Use sync implementations with sync APIs and async implementations
with async APIs. The SDK uses these interfaces, so changing the storage backend
does not require changing its execution code. Your application owns and closes
the supplied components.

(shared-image-client)=

## Share one client

For a workflow with several operations, initialize a client once. Pass it through
`client=` as a dependency to the import helper, build helper, and sandbox factory.
This reuses the connection and gives your application one place to configure it.
Each operation leaves this client open; the outer context closes it.

Use the `build-context` directory from
[Create a small build context](building-images.md#create-a-small-build-context).
These programs import the base under the `alpine:latest` ConTree tag, build that
context, and read its result. The Dockerfile's `FROM alpine:latest` resolves the
imported image.

::::{tab} Sync

<!--
name: test_shared_client_sync; fixtures: doc_api, doc_build_context, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a built image!\n")
for client in (doc_api.sync, doc_api.async_client):
    client.mock("import_image", "operation-1")
    client.mock("resolve_image", "image-1")
```
-->

```python
"""Reuse one client for import, build, and sandbox operations."""

from contree_client import profiles
from contree_client.sync import ContreeClient

from contree_sdk import create_sandbox_session, sync_build_image, sync_import_image


def main() -> None:
    # Create one client for the full workflow.
    profile = profiles.from_env() or profiles.resolve_profile()
    with ContreeClient.from_profile(profile) as client:
        # Import the base and give it the tag used by FROM.
        sync_import_image(
            "docker://mirror.gcr.io/library/alpine:latest",
            tag="alpine:latest",
            client=client,
        )

        # Build with the same client, then read the resulting filesystem.
        image = sync_build_image("build-context", client=client)
        with create_sandbox_session(image=image, client=client) as sandbox:
            content = sandbox.read_file("/built.txt")
            print(content.decode(), end="")


main()
```

<!--
name: test_shared_client_sync
```python
assert len(doc_api.sync.calls_for("import_image")) == 1
assert len(doc_api.sync.calls_for("spawn_instance")) == 1
assert doc_api.sync.calls_for("inspect_image_download")[0].args == ("image-1", "/built.txt")
assert capsys.readouterr().out == "Hello from a built image!\n"
```
-->

::::

::::{tab} Async

<!--
name: test_shared_client_async; fixtures: doc_api, doc_build_context, capsys
```python
doc_api.complete()
doc_api.download(b"Hello from a built image!\n")
for client in (doc_api.sync, doc_api.async_client):
    client.mock("import_image", "operation-1")
    client.mock("resolve_image", "image-1")
```
-->

```python
import asyncio

from contree_client import profiles
from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import create_sandbox_session, async_build_image, async_import_image


async def main() -> None:
    # Create one client for the full workflow.
    profile = profiles.from_env() or profiles.resolve_profile()
    async with ContreeAsyncClient.from_profile(profile) as client:
        # Import the base and give it the tag used by FROM.
        await async_import_image(
            "docker://mirror.gcr.io/library/alpine:latest",
            tag="alpine:latest",
            client=client,
        )

        # Build with the same client, then read the resulting filesystem.
        image = await async_build_image("build-context", client=client)
        async with create_sandbox_session(image=image, client=client) as sandbox:
            content = await sandbox.read_file("/built.txt")
            print(content.decode(), end="")


asyncio.run(main())
```

<!--
name: test_shared_client_async
```python
assert len(doc_api.async_client.calls_for("import_image")) == 1
assert len(doc_api.async_client.calls_for("spawn_instance")) == 1
assert doc_api.async_client.calls_for("inspect_image_download")[0].args == ("image-1", "/built.txt")
assert capsys.readouterr().out == "Hello from a built image!\n"
```
-->

::::

## Select the session class and components

Some async snippets use top-level `await`. Run them inside an async function or
a compatible notebook. Complete programs use `asyncio.run(main())`.

`session_type` accepts a class. Without it, the context selects `LazySession` or
`AsyncLazySession`. An explicitly selected class must match the context mode:
`session_type=AsyncLazySession` with a synchronous `with` raises `TypeError`
before creating a client. The same rule applies to `client_type` and supplied
store, file transfer, and client objects.

::::{tab} Sync

<!-- name: test_factory_components; fixtures: sandbox_api -->

```python
from contree_sdk import LazySession, create_sync_sandbox_session
from contree_sdk.session import IdleSnapshotPolicy
from contree_sdk.store import SyncSQLiteStore


with SyncSQLiteStore("sandbox.db") as store:
    with create_sync_sandbox_session(
        image="tag:alpine:latest",
        session_type=LazySession,
        session_id="work",
        store=store,
        cache_ttl=60,
        cwd="/",
        env={"LANG": "C.UTF-8"},
        session_kwargs={"snapshot_policy": IdleSnapshotPolicy(120), "snapshot_timeout": 30},
    ) as session:
        session.run("echo", args=["Saved on exit"])
```

::::

::::{tab} Async

<!-- name: async test_factory_components_async; fixtures: sandbox_api -->

```python
from contree_sdk import AsyncLazySession, create_async_sandbox_session
from contree_sdk.session import IdleSnapshotPolicy
from contree_sdk.store import AsyncSQLiteStore


async with AsyncSQLiteStore("sandbox.db") as store:
    async with create_async_sandbox_session(
        image="tag:alpine:latest",
        session_type=AsyncLazySession,
        session_id="work",
        store=store,
        cache_ttl=60,
        cwd="/",
        env={"LANG": "C.UTF-8"},
        session_kwargs={"snapshot_policy": IdleSnapshotPolicy(120), "snapshot_timeout": 30},
    ) as session:
        await session.run("echo", args=["Saved on exit"])
```

::::

Custom classes implement `SyncExecutor` or `AsyncExecutor`. Lazy subclasses
receive an underlying `ContreeSession` or `ContreeAsyncSession`, plus
`session_kwargs`. Other classes receive the client and the standard Session
constructor arguments, plus `session_kwargs`. Subclass an existing session to
retain its execution and lifecycle rules. The factory never substitutes a
different class for an explicitly selected class.

Selecting `ContreeSession` or `ContreeAsyncSession` saves each command by default
and starts the next command in a separate VM. Use `disposable=True` to leave
the session image unchanged. See [Save after every command](session-model.md#save-after-every-command).

Snapshots are lightweight; saving after every command is supported. A snapshot
stops the VM and can return the same image UUID if files have not changed.

| Argument                      | Purpose                                                                                                                                                                                                                     |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `image`, `session_id`         | Initial image or stored session to resume. At least one is required.                                                                                                                                                        |
| `node_id`                     | Select a saved node explicitly when resuming, including a tree with multiple continuations.                                                                                                                                 |
| `store`                       | Session history store; defaults to a new memory store of the selected mode.                                                                                                                                                 |
| `cache_ttl`                   | Upload reuse through the shared Store expires after 60 seconds by default. Choose a TTL no longer than your server's upload retention.                                                                                      |
| `cwd`, `env`, `commit_policy` | Configuration of the underlying session.                                                                                                                                                                                    |
| `file_transfer`               | Replace file I/O; a cached transfer wraps it using the same Store.                                                                                                                                                          |
| `session_kwargs`              | Additional constructor arguments for the selected session class, including lazy snapshot options. Factory-managed arguments take priority over duplicates in this mapping.                                                  |
| `client`                      | Borrow an already configured client. Cannot be combined with connection settings or `client_type`.                                                                                                                          |
| `client_type`                 | Select a contree-client class. Defaults are HTTPX for sync and aiohttp for async.                                                                                                                                           |
| Other keyword arguments       | Forwarded unchanged to the client constructor through `from_profile`, including `timeout`, `retry`, `identity`, TLS and backend-specific settings. Credentials follow {ref}`sandbox-connection`; use `url`, not `base_url`. |

Uploaded-file cache entries are separated by endpoint, project, and token. The
cache does not replace history storage or enable uploads to an already running
LazySession VM.

## Ownership and extension

Each context object permits one entry, including a failed entry. Re-entry,
nesting, and mixing sync/async entry on that object raise `RuntimeError`; call the
factory again to get a new context.

The factory closes resources it creates. Supplied clients, storage, and
file transfers remain caller-owned and must be ready for use. A session's context
exit runs before the owned client closes. Async cleanup is joined even when the
caller cancels again; a body exception takes priority over cleanup errors.

All three factories call `session_maker(context_type, ...)` with their respective
context class. `SandboxSessionContext` composes `SyncSandboxSessionContext` and
`AsyncSandboxSessionContext`. For a custom context, supply a class accepting
`SandboxConfig` to `session_maker`. See {doc}`reference/sandbox` for the shared
parameter signature and context contracts.

For complete sync and async examples of the component assembly behind this
factory, see {doc}`manual-sandbox`.

## Tag a saved result

Run a setup command, save its result, and give that image a reusable name. This
example selects `ContreeSession` or `ContreeAsyncSession`, which saves each command
by default as an independent operation. The default lazy sandbox instead
saves at a snapshot boundary; see {doc}`session-model`.

::::{tab} Sync

<!--
name: test_tag_image; fixtures: doc_api, capsys
```python
doc_api.complete()
for client in (doc_api.sync, doc_api.async_client):
    client.mock("update_image_tag", None)
```
-->

```python
"""Save a setup command as a reusable image."""

from contree_client import profiles
from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession, create_sandbox_session


def main() -> None:
    profile = profiles.from_env() or profiles.resolve_profile()
    with ContreeClient.from_profile(profile) as client:
        with create_sandbox_session(image="tag:alpine:latest", session_type=ContreeSession, client=client) as sandbox:
            sandbox.run(shell="echo ready > /ready.txt")
            client.update_image_tag(sandbox.image_uuid, "prepared-base")
            print(sandbox.image_uuid)


main()
```

<!--
name: test_tag_image
```python
assert doc_api.sync.calls_for("update_image_tag")[0].args == ("image-1", "prepared-base")
assert capsys.readouterr().out == "image-1\n"
```
-->

::::

::::{tab} Async

<!--
name: test_tag_image_async; fixtures: doc_api, capsys
```python
doc_api.complete()
for client in (doc_api.sync, doc_api.async_client):
    client.mock("update_image_tag", None)
```
-->

```python
import asyncio

from contree_client import profiles
from contree_client.asyncio import ContreeAsyncClient

from contree_sdk import ContreeAsyncSession, create_sandbox_session


async def main() -> None:
    profile = profiles.from_env() or profiles.resolve_profile()
    async with ContreeAsyncClient.from_profile(profile) as client:
        async with create_sandbox_session(
            image="tag:alpine:latest", session_type=ContreeAsyncSession, client=client
        ) as sandbox:
            await sandbox.run(shell="echo ready > /ready.txt")
            await client.update_image_tag(sandbox.image_uuid, "prepared-base")
            print(sandbox.image_uuid)


asyncio.run(main())
```

<!--
name: test_tag_image_async
```python
assert doc_api.async_client.calls_for("update_image_tag")[0].args == ("image-1", "prepared-base")
assert capsys.readouterr().out == "image-1\n"
```
-->

::::

Use `image="tag:prepared-base"` in another sandbox. The tag refers to the saved
filesystem; it does not copy session history, environment overrides, or defaults.
Assigning an existing tag moves it to the new image.

Image listing and tag removal are available through `list_images()` and
`delete_image_tag()` on the client. Closing a client or local store does not
delete server images. Deleting a server image can invalidate saved session history.

## Assemble the builder yourself

The helpers create a client and one SQLite Store for layer history and reusable uploads. They scope the build session to the context path and connection,
call the Docker builder, and close the resources they created.

Use the builder directly to manage these dependencies and their lifetime yourself.
The following example keeps a builder inside the client context and uses its
default memory Store. For persistence, pass `store=SyncSQLiteStore(...)` or its
async equivalent and close it yourself. Helpers accept the same dependency as `store=`.
Use `builder_type=` and `builder_kwargs=` to extend a builder through a helper.

### Rebuild a multi-stage image after changing inputs

This standalone example creates `multi-context` in the current directory. Its
first stage builds an output file. The second stage copies only that output with
`COPY --from`. Use a base image with `cat` and a POSIX shell.
The builder downloads regular files as bytes and attaches them at their final
paths to the next operation. The file specification carries permissions and
ownership, including explicit `--chown`/`--chmod` overrides.

For directory sources, the builder exports tar and asks the live API to unpack
it directly into the destination with merge enabled. This preserves existing
entries that are absent from the archive. The VM runs `sleep infinity` during
transfer. Explicit directory overrides run as subprocesses after unpacking and
before the builder signals the main process to save the layer. These commands
change only entries supplied by the archive. Directory copies require
`sleep infinity` and, for overrides, `chown` or `chmod`; they do not require `tar`.

Keep the same builder, store, and build session to observe layer reuse. Changing
an ignored file leaves the build inputs unchanged. Changing `message.txt`
invalidates the source RUN and the stage copy that depends on its output.

::::{tab} Sync

<!--
name: test_multistage_rebuild; fixtures: doc_api, doc_stage_file
```python
for _ in range(4):
    doc_api.complete()
```
-->

```python
from pathlib import Path

from contree_client import profiles
from contree_client.sync import ContreeClient

from contree_sdk.docker import ContreeDockerBuilder


context = Path("multi-context")
context.mkdir(exist_ok=True)
(context / "Dockerfile").write_text(
    "ARG BASE_IMAGE\n"
    "FROM ${BASE_IMAGE} AS source\n"
    "COPY . /src/\n"
    "RUN cat /src/message.txt > /built.txt\n"
    "FROM ${BASE_IMAGE}\n"
    "COPY --from=source /built.txt /result.txt\n"
)
(context / ".dockerignore").write_text("ignored.txt\n")
(context / "message.txt").write_text("one\n")
(context / "ignored.txt").write_text("local notes\n")

with ContreeClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client:
    builder = ContreeDockerBuilder(client)

    def rebuild():
        events = []
        image = builder.build(
            context,
            build_args={"BASE_IMAGE": "tag:alpine:latest"},
            session_id="multi-stage-demo",
            on_event=events.append,
        )
        started = [event for event in events if event.type == "operation_started"]
        return image, started

    first_image, first_runs = rebuild()
    repeated_image, repeated_runs = rebuild()
    (context / "ignored.txt").write_text("changed local notes\n")
    ignored_image, ignored_runs = rebuild()
    (context / "message.txt").write_text("two\n")
    changed_image, changed_runs = rebuild()

assert len(first_runs) == 2  # Source RUN and snapshot of the attached stage file.
assert repeated_runs == ignored_runs == []
assert first_image == repeated_image == ignored_image
assert len(changed_runs) == 2
```

::::

::::{tab} Async

<!--
name: async test_multistage_rebuild_async; fixtures: doc_api, doc_stage_file
```python
for _ in range(4):
    doc_api.complete()
```
-->

```python
from pathlib import Path

from contree_client import profiles
from contree_client.asyncio import ContreeAsyncClient

from contree_sdk.docker import ContreeAsyncDockerBuilder


context = Path("multi-context")
context.mkdir(exist_ok=True)
(context / "Dockerfile").write_text(
    "ARG BASE_IMAGE\n"
    "FROM ${BASE_IMAGE} AS source\n"
    "COPY . /src/\n"
    "RUN cat /src/message.txt > /built.txt\n"
    "FROM ${BASE_IMAGE}\n"
    "COPY --from=source /built.txt /result.txt\n"
)
(context / ".dockerignore").write_text("ignored.txt\n")
(context / "message.txt").write_text("one\n")
(context / "ignored.txt").write_text("local notes\n")

async with ContreeAsyncClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client:
    builder = ContreeAsyncDockerBuilder(client)

    async def rebuild():
        events = []
        image = await builder.build(
            context,
            build_args={"BASE_IMAGE": "tag:alpine:latest"},
            session_id="multi-stage-demo",
            on_event=events.append,
        )
        started = [event for event in events if event.type == "operation_started"]
        return image, started

    first_image, first_runs = await rebuild()
    repeated_image, repeated_runs = await rebuild()
    (context / "ignored.txt").write_text("changed local notes\n")
    ignored_image, ignored_runs = await rebuild()
    (context / "message.txt").write_text("two\n")
    changed_image, changed_runs = await rebuild()

assert len(first_runs) == 2  # Source RUN and snapshot of the attached stage file.
assert repeated_runs == ignored_runs == []
assert first_image == repeated_image == ignored_image
assert len(changed_runs) == 2
```

::::

The cache comparison uses file content and execution inputs. It does not require
the server to return a different image UUID for every submission. To retain this
cache across Python restarts, supply a SQLite Store as above.

Source files and directory archives are keyed by immutable image UUID and source path, without a
client expiry. Before reuse, the builder checks the uploaded file with HEAD;
a missing upload is downloaded from the image and uploaded again. Cached layers also receive a
HEAD check, and missing images are rebuilt. Store retention still applies.

The live API restores regular-file permission bits from tar. Its current
implementation creates archive directories with mode `0755` and does not restore
ownership or timestamps. Explicit directory overrides apply after unpacking. File attachments retain
the source file mode and ownership unless COPY overrides them.

## Observe a live build

Use the `build-context` files from {doc}`building-images` for these examples.

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
doc_api.sync.mock(
    "follow_operation_events",
    [
        replace(event("stdout"), data=EventDataStream.from_text("building\n")),
        event("completion"),
    ],
)
```
-->

```python
import sys

from contree_client import profiles
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


with ContreeClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client:
    builder = ContreeDockerBuilder(client)
    image_uuid = builder.build(
        "build-context",
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
doc_api.async_client.mock(
    "follow_operation_events",
    [
        replace(event("stdout"), data=EventDataStream.from_text("building\n")),
        event("completion"),
    ],
)
```
-->

```python
import asyncio
import sys

from contree_client import profiles
from contree_client.asyncio import ContreeAsyncClient

from contree_sdk.docker import BuildEvent, ContreeAsyncDockerBuilder


async def report(event: BuildEvent) -> None:
    if event.type in {"stdout", "stderr"}:
        stream = sys.stdout.buffer if event.type == "stdout" else sys.stderr.buffer
        await asyncio.to_thread(stream.write, event.data)
        await asyncio.to_thread(stream.flush)
    elif event.type == "step_started":
        await asyncio.to_thread(print, f"Step {event.step.id}: {event.step.keyword}", flush=True)


async with ContreeAsyncClient.from_profile(profiles.from_env() or profiles.resolve_profile()) as client:
    builder = ContreeAsyncDockerBuilder(client)
    image_uuid = await builder.build(
        "build-context",
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

COPY and ADD keep reusable upload records in the same Store as layer history.
Tree kinds separate these records. Namespaces and layer hashes include the
endpoint, project, and credential scope, so shared storage does not reuse another
server’s UUIDs.
Local paths and source URLs are retained through the public file-source registry.
See {doc}`caching` for enumeration and invalidation.

The default upload lifetime is 90 days. Cache hits and URL responses with status
304 do not extend it. Override `create_context()` and set
`context.upload_cache_ttl` to choose a shorter lifetime for your server. Expiry
causes a new upload when the directive runs; it does not invalidate an existing
image layer. A 304 response without a live cached upload raises `DockerBuildError`.

Local COPY uses a temporary snapshot for its content hash and upload. Async COPY
limits concurrent snapshots and uploads through `context.upload_concurrency`
(default four). URL ADD streams into a temporary file before upload and closes the
response body, including conditional responses. These paths bound memory usage;
temporary disk space must hold the files currently being prepared.

## Assemble the sandbox yourself

The factory resolves a connection, creates a client and memory store, connects
file transfer to a base session, and wraps it in a lazy session.
See {doc}`manual-sandbox` for complete Sync/Async programs that assemble these
components and close them in the correct order.

```{toctree}
:maxdepth: 1

manual-sandbox
```
