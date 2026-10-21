# Customize the SDK

Subclass a session to change command defaults, image resolution, or operation
handling. To replace storage or file transfer, implement the matching sync or
async interface and pass it to the sandbox factory. See {doc}`manual-sandbox`
if you also need to manage component construction and cleanup.

## Customize command policy and operations

`RunRequest` is a frozen configuration value. Its argument tuple and environment
mapping are copied at construction. Files and stdin remain caller-owned resources.
Use `dataclasses.replace()` to apply policy without mutating the caller's request.

This example rejects shell commands, applies a default timeout, and counts waits.
Configure a connection as described in {ref}`sandbox-connection`.

::::{tab} Sync

<!--
name: test_custom_policy; fixtures: doc_api, capsys
```python
doc_api.complete()
```
-->

```python
from dataclasses import replace

from contree_client.models import InstanceResult, InstanceSpawnResponse

from contree_sdk import ContreeSession, OperationContext, RunRequest, create_sandbox_session
from contree_sdk.session import Operation, OperationContract


class AuditedOperation(Operation):
    waits = 0

    def wait(self, *, timeout: float | None = None) -> InstanceResult:
        self.waits += 1
        return super().wait(timeout=timeout)


class PolicySession(ContreeSession):
    def prepare_request(self, request: RunRequest) -> RunRequest:
        request = super().prepare_request(request)
        if request.shell is not None:
            raise ValueError("this session only accepts commands with explicit arguments")
        return replace(request, timeout=request.timeout or 30, env={**(request.env or {}), "APP_MODE": "test"})

    def create_operation(self, response: InstanceSpawnResponse, context: OperationContext) -> OperationContract:
        if not isinstance(response.uuid, str):
            raise TypeError("missing operation UUID")
        return AuditedOperation(self.client, response.uuid, timeout=context.request.timeout_seconds, context=context)


with create_sandbox_session(session_type=PolicySession, image="tag:alpine:latest") as session:
    with session.spawn("echo", args=["hello"]) as operation:
        result = operation.wait()
        session.commit_result(operation)
        assert isinstance(operation, AuditedOperation)
        print(operation.waits)
```

<!--
name: test_custom_policy
```python
import pytest

with pytest.raises(ValueError, match="explicit arguments"):
    session.run(shell="echo blocked")
assert len(doc_api.sync.calls_for("spawn_instance")) == 1
assert operation.waits == 1
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["env"] == {"APP_MODE": "test"}
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["timeout"] == 30
assert capsys.readouterr().out == "1\n"
```
-->

::::

::::{tab} Async

<!--
name: async test_custom_policy_async; fixtures: doc_api, capsys
```python
doc_api.complete()
```
-->

```python
from dataclasses import replace

from contree_client.models import InstanceResult, InstanceSpawnResponse

from contree_sdk import ContreeAsyncSession, OperationContext, RunRequest, create_sandbox_session
from contree_sdk.session import AsyncOperation, AsyncOperationContract


class AuditedAsyncOperation(AsyncOperation):
    waits = 0

    async def wait(self, *, timeout: float | None = None) -> InstanceResult:
        self.waits += 1
        return await super().wait(timeout=timeout)


class PolicySession(ContreeAsyncSession):
    def prepare_request(self, request: RunRequest) -> RunRequest:
        request = super().prepare_request(request)
        if request.shell is not None:
            raise ValueError("this session only accepts commands with explicit arguments")
        return replace(request, timeout=request.timeout or 30, env={**(request.env or {}), "APP_MODE": "test"})

    def create_operation(self, response: InstanceSpawnResponse, context: OperationContext) -> AsyncOperationContract:
        if not isinstance(response.uuid, str):
            raise TypeError("missing operation UUID")
        return AuditedAsyncOperation(
            self.client, response.uuid, timeout=context.request.timeout_seconds, context=context
        )


async with create_sandbox_session(session_type=PolicySession, image="tag:alpine:latest") as session:
    async with await session.spawn("echo", args=["hello"]) as operation:
        result = await operation.wait()
        await session.commit_result(operation)
        assert isinstance(operation, AuditedAsyncOperation)
        print(operation.waits)
```

<!--
name: test_custom_policy_async
```python
import pytest

with pytest.raises(ValueError, match="explicit arguments"):
    await session.run(shell="echo blocked")
assert len(doc_api.async_client.calls_for("spawn_instance")) == 1
assert operation.waits == 1
assert doc_api.async_client.calls_for("spawn_instance")[0].kwargs["env"] == {"APP_MODE": "test"}
assert doc_api.async_client.calls_for("spawn_instance")[0].kwargs["timeout"] == 30
assert capsys.readouterr().out == "1\n"
```
-->

::::

The session calls `prepare_request()` before uploading files or submitting work.
It passes the prepared inputs to `submit_request()`, then constructs the handle
through `create_operation()`. The `OperationContext` holds the effective request
and the source image, history entry, and branch used for the eventual commit.
If operation construction fails after submission, the session attempts remote
cancellation and preserves the factory error.

`create_store()` and `create_file_transfer()` supply defaults only when no component
was passed explicitly. Constructor-time factories must not depend on attributes
that a subclass initializes after `super().__init__()`.

## Choose what to override

| Requirement                                | Extension boundary                                             |
| ------------------------------------------ | -------------------------------------------------------------- |
| Add command defaults or reject commands    | Override `prepare_request(RunRequest)`                         |
| Resolve images from another naming scheme  | Override `resolve_image(image)`                                |
| Modify transport submission                | Override `submit_request(...)`                                 |
| Instrument or replace operation lifecycle  | Override `create_operation(response, context)`                 |
| Replace subprocess handles                 | Override `Operation.create_subprocess(spid, queue)`            |
| Replace the event source                   | Override `Operation.open_event_stream()`                       |
| Observe operation events                   | Register `add_observer()` before starting the reader           |
| Upload from another storage service        | Implement `SyncFileTransfer` or `AsyncFileTransfer`            |
| Store history remotely                     | Implement `SyncStore` or `AsyncStore`                          |
| Replace build caching                      | Implement `SyncStore` or `AsyncStore`                          |
| Add or replace Dockerfile instructions     | Register a `DockerKeyword` with `DockerfileParser`             |
| Use a session subclass inside builds       | Pass `session_factory=`                                        |
| Add per-build state                        | Set `context_class` or override `create_context(BuildRequest)` |
| Audit or restrict build instructions       | Override `execute_directive(directive, context)`               |
| Use another execution engine in deepagents | Implement `SyncExecutor` or `AsyncExecutor`                    |

Use native async I/O in async overrides; offload blocking work explicitly.

## Implement file transfer

Inherit `SyncFileTransfer` or `AsyncFileTransfer` and implement:

- `upload(UploadFileSpec) -> FileSpec`: return a file identifier valid on the session's server.
- `read_file(image_uuid, path) -> bytes`: return exact bytes from the specified image.

The default `prepare_files()` expands directories, rejects destination conflicts,
and calls `upload()` with a bounded worker count. Set `max_concurrency` on a custom
transfer to select that limit. Override `iter_file()` to yield chunks and release
its reader when the generator closes. Its default implementation buffers through
`read_file()`. The inherited `download_file()` writes those chunks atomically.
See {doc}`files` for tree preparation, callbacks, cancellation, and ownership.
The async implementation cancels and joins sibling uploads if one fails. Override
this method for batching or bounded concurrency. Override `read_stdin()` to support
additional input handling. Never close a caller-owned input stream.

Inject a component with `file_transfer=`. `ClientFileTransfer` and
`AsyncClientFileTransfer` provide the standard implementations and can also be
subclassed. Import `UploadFileSpec`, `UploadedFile`, `InputSource`, and the readable
protocols from `contree_sdk.files`.

## Implement history storage

Implement `SyncStore` or `AsyncStore` from `contree_sdk.store`. The same interface
supports session history and reusable results. The core operation is
`append(session_id, node)`: save an immutable node with an explicit parent.

Preserve these guarantees across all clients of your backend:

- A parent belongs to the same live tree; a tree has one root.
- Repeating an identical node succeeds without a duplicate. Reusing its identity
  with different contents raises `NodeConflictError` without overwriting data.
- Reads and writes detach JSON values from caller-owned objects.
- Tree and node kind filters apply before cursor pagination.
- `get_nodes()` reads up to 1000 known identities atomically, preserving input
  order and `None` slots for missing nodes. Implement it as a batch read when
  network round trips are expensive.
- TTL and deletion cover the tree. Reads and append do not renew expiry.

See {doc}`reference/store` for the complete contract. Store does not implement
branch switching, command execution, or Docker hashing. Session handles local
navigation and serializes its payloads into nodes. Staging records contain
attachments and applied paths. Detached completion saves its response and result
in one node, using the identity recorded before collection.

## Store reusable results

The same Store holds history and reusable results. Implement its contract with
Redis or PostgreSQL and supply it through `store=` in helpers and
direct constructors. Tree `kind` distinguishes purposes; the backend does not
interpret user JSON.

Stores expose `close()` and a matching context manager. Sessions and builders
leave caller-supplied stores open. See {doc}`caching` for upload reuse and
{doc}`detached-operations` for operation recovery.

## Replace an integration backend

The framework adapters depend only on `SyncExecutor` or `AsyncExecutor`:

- `session_id` identifies the execution context.
- `execute(RunRequest)` returns `contree_client.models.InstanceResult`.
- `write_file(path, content)` writes bytes and returns `None` after application.
- `read_file(path)` returns bytes; use client `NotFoundError` or
  `UnprocessableEntityError` for missing or invalid paths.

A nonzero process exit code belongs in the result. Operation-level failure is an
exception. Preserve cancellation and timeout errors. An executor used by the
sandbox must retain filesystem changes when `disposable=False`; the adapter uses
this for commands and uploads. It serializes its own mutating calls, but callers
sharing the same executor must coordinate any additional concurrent mutations.

The adapters never access a concrete session's client, store, or history internals.
They do not close the executor. The async adapter requires native async methods;
its sync entry points raise `NotImplementedError`.

`write_file()` has a default implementation using shell execution and binary
`RunRequest.stdin`. Existing executors inherit it. Override this method to replace
the transfer mechanism; adapters do not construct upload commands themselves.
A failed write raises `FileWriteError(path, message)`. Transport errors, timeouts,
and cancellation must propagate unchanged.

A write must apply the content before returning. Uploading a blob or staging files
for a later command is not sufficient. A native transfer implementation must also
coordinate with VM startup, active commands, and snapshots. Keep the VM selected
for the transfer until the backend confirms application.

Blob upload and application to a VM are separate operations. A future backend
implementation can reuse uploaded blobs here without changing framework calls.
Archive extraction needs explicit extraction semantics; `write_file` always means
writing the supplied bytes, even when those bytes contain an archive.
See [File transfers and executor contracts](../integrations/langchain.md#advanced-file-transfers-and-executor-contracts).

## Extend Dockerfile builds

The same directive class supports both builders through `execute()` and
`execute_async()`. Create a parser per dialect, then register your directive:

<!--
name: async test_custom_directive; fixtures: doc_api, tmp_path, capsys
-->

```python
"""Register a Dockerfile directive without changing the SDK's global registry."""

from dataclasses import dataclass
from typing import ClassVar

from contree_sdk.docker import AsyncBuildContext, BuildContext, DockerfileParser, DockerKeyword


@dataclass(frozen=True, repr=False)
class BuildMode(DockerKeyword):
    NAME: ClassVar[str] = "BUILDMODE"
    value: str = ""

    @classmethod
    def parse(cls, args_text: str) -> "BuildMode":
        if args_text not in {"test", "release"}:
            raise ValueError("BUILDMODE requires test or release")
        return cls(value=args_text)

    def serialize(self) -> str:
        return f"BUILDMODE {self.value}"

    def execute(self, ctx: BuildContext) -> None:
        ctx.env["BUILD_MODE"] = self.value

    async def execute_async(self, ctx: AsyncBuildContext) -> None:
        ctx.env["BUILD_MODE"] = self.value


def make_parser() -> DockerfileParser:
    parser = DockerfileParser()
    parser.register(BuildMode)
    return parser


parser = make_parser()
print(parser.parse("BUILDMODE test"))
```

<!--
name: test_custom_directive
```python
assert parser.parse("BUILDMODE test") == [BuildMode(value="test")]
assert "BUILDMODE" in capsys.readouterr().out
import pytest

from contree_sdk.docker import ContreeAsyncDockerBuilder, ContreeDockerBuilder
from contree_sdk.store import AsyncMemoryStore, SyncMemoryStore

assert parser.parse("BUILDMODE\ttest") == [BuildMode(value="test")]
with pytest.raises(ValueError, match="unknown"):
    DockerfileParser().parse("BUILDMODE test")
with pytest.raises(ValueError, match="requires"):
    parser.parse("BUILDMODE invalid")
assert BuildMode(value="release").serialize() == "BUILDMODE release"
(tmp_path / "Dockerfile").write_text("FROM base\nBUILDMODE release\nRUN echo hi\n")
doc_api.complete()
with SyncMemoryStore() as store:
    for _ in range(2):
        assert (
            ContreeDockerBuilder(doc_api.sync, parser=make_parser(), store=store).build(tmp_path, session_id="dialect")
            == "image-1"
        )

async with AsyncMemoryStore() as store:
    for _ in range(2):
        assert (
            await ContreeAsyncDockerBuilder(doc_api.async_client, parser=make_parser(), store=store).build(
                tmp_path, session_id="dialect"
            )
            == "image-1"
        )

for client in (doc_api.sync, doc_api.async_client):
    assert len(client.calls_for("spawn_instance")) == 1
    assert client.calls_for("spawn_instance")[0].kwargs["env"] == {"BUILD_MODE": "release"}
```
-->

Pass the parser with `parser=make_parser()` to either builder. Registration copies
no state into the module registry and cannot change another builder's dialect.
`execute()` and `execute_async()` define the instruction's sync and async behavior.
Implement both if the dialect supports both builders.

The `session_factory` receives `client` as its first positional argument, then
`session_id`, `store`, `image`, `node_id`, and `tree_kind` as keyword arguments. It returns a `ContreeSession` or `ContreeAsyncSession` implementation.
Both fresh layers and cache hits use this factory. Set `context_class` to a
`BuildContext` or `AsyncBuildContext` subclass when only additional methods or state
are needed. Override `create_context(BuildRequest)` for a different construction
policy. `execute_directive()` intercepts normal steps, stage sealing, and final file materialization.
Custom directives that execute nested directives must call `context.execute_directive()`.
A custom `create_context()` must pass `directive_executor=self.run_step`
to preserve event reporting and policy dispatch for nested steps.
`run_step()` wraps `execute_directive()` with step notifications.
Override `BuildContext.run_operation(request, branch=...)` or its async equivalent
to customize RUN orchestration. The default uses session `spawn_request()`,
operation `events()`/`wait()`, and session `commit_result()`. It applies
`prepare_request()` and the session operation factory through these public hooks.

A custom directive must include every input that affects a layer in the context's
cache state or its hash contribution. Changing the implementation of an instruction
can invalidate previous cached layers; use a new session/cache namespace or disable
cache reuse. A parser extension alone does not automatically version existing caches.

## Operation contract obligations

`OperationContract` and `AsyncOperationContract` expose status, events, waiting,
stdin, signals, cancellation, context management, and subprocess creation. A
session-created operation has an `OperationContext`. A reattached UUID-only handle
may have no context and cannot be committed to session history.

`wait()` must store the final `OperationResponse` before returning its
`InstanceResult`. Cancellation and cleanup must preserve the primary exception.
Use `SubprocessContract` or `AsyncSubprocessContract` when replacing subprocess
handles. Iteration followed by `wait()` must not wait for a second exit event.
A stream failure must reach its consumer instead of appearing as successful EOF.

The built-in operations own one unfiltered reader per handle. Override
`open_event_stream()` to replace its source. Calling `events()` creates a local
subscription; overriding it does not replace the source used by `wait()` or
subprocesses. Register observers before entering the context or first consuming
`events()` or `wait()`. Sync observers return directly; async observers are awaited.
They receive `(event, None)` for events and `(None, error)` at EOF. Keep them short;
do not wait for the operation from its own observer. Observer errors fail the reader.

`LazySession` requires `add_observer()` support from a custom operation contract.
It delegates request policy and operation creation to the wrapped session. Pass
`vm_request=RunRequest(...)` to configure the main process, VM lifetime, and other
startup options without subclassing. With the sandbox factories, put `vm_request`
in `session_kwargs`. `ManualSnapshotPolicy` keeps the VM alive until explicit
snapshot, close, or abort; the default remains a ten-second idle snapshot.
Override `keepalive_request()` when the startup request needs custom logic. See
{doc}`reference/session` for the public snapshot-policy interface.

## Resolve application-specific image names

A sync override runs during session construction. An async override runs during
`ensure_ready()` or the first operation. Return a valid UUID for the selected server;
the example uses a mapping that your application supplies.

::::{tab} Sync

<!--
name: test_resolve_policy; fixtures: doc_api
-->

```python
from contree_sdk import ContreeSession, create_sandbox_session


class NamedImageSession(ContreeSession):
    def resolve_image(self, image: str) -> str:
        return {"test-base": "8a0269a2-7720-4daa-aa96-dca93b20bb33"}[image]


with create_sandbox_session(session_type=NamedImageSession, image="test-base") as session:
    print(session.image_uuid)
```

<!--
name: test_resolve_policy
```python
assert session.image_uuid == "8a0269a2-7720-4daa-aa96-dca93b20bb33"
assert session.client.calls_for("resolve_image") == []
```
-->

::::

::::{tab} Async

<!--
name: async test_resolve_policy_async; fixtures: doc_api
-->

```python
from contree_sdk import ContreeAsyncSession, create_sandbox_session


class NamedAsyncImageSession(ContreeAsyncSession):
    async def resolve_image(self, image: str) -> str:
        return {"test-base": "8a0269a2-7720-4daa-aa96-dca93b20bb33"}[image]


async with create_sandbox_session(session_type=NamedAsyncImageSession, image="test-base") as session:
    print(session.image_uuid)
```

<!--
name: test_resolve_policy_async
```python
assert session.image_uuid == "8a0269a2-7720-4daa-aa96-dca93b20bb33"
assert session.client.calls_for("resolve_image") == []
```
-->

::::

## Select a commit policy

`ApiSuccessCommitPolicy` is the default for both session implementations. It
retains successful API results from non-disposable commands, including nonzero
and unknown process exit codes. API failure and cancellation raise errors and
never change history.

Pass `commit_policy=ZeroExitCommitPolicy()` to retain only results with an explicit
zero exit code. A rejected result is still returned to the caller. Rejection does
not change the session image, branches, or pending files. `commit_result()` uses
the same policy after an explicit `spawn()` and `wait()`; it returns `None` when
it skips the commit. Disposable requests cannot create history entries through
`commit_result()`, even if the server returns an image.

::::{tab} Sync

<!--
name: test_sync_commit_policy; fixtures: doc_api
```python
doc_api.complete(exit_code=7)
doc_api.complete(exit_code=7)
```
-->

```python
from contree_sdk import ContreeSession, create_sandbox_session
from contree_sdk.session import ZeroExitCommitPolicy


with create_sandbox_session(
    session_type=ContreeSession, image="tag:alpine:latest", commit_policy=ZeroExitCommitPolicy()
) as session:
    original_image = session.image_uuid
    result = session.run(shell="exit 7")
    assert result.state.exit_code == 7
    assert session.image_uuid == original_image
    operation = session.spawn(shell="exit 7")
    result = operation.wait()
    entry = session.commit_result(operation)
    assert result.state.exit_code == 7
    assert entry is None
```

::::

::::{tab} Async

<!--
name: async test_async_commit_policy; fixtures: doc_api
```python
doc_api.complete(exit_code=7)
doc_api.complete(exit_code=7)
```
-->

```python
from contree_sdk import ContreeAsyncSession, create_sandbox_session
from contree_sdk.session import ZeroExitCommitPolicy


async with create_sandbox_session(
    session_type=ContreeAsyncSession, image="tag:alpine:latest", commit_policy=ZeroExitCommitPolicy()
) as session:
    original_image = session.image_uuid
    result = await session.run(shell="exit 7")
    assert result.state.exit_code == 7
    assert session.image_uuid == original_image
    operation = await session.spawn(shell="exit 7")
    result = await operation.wait()
    entry = await session.commit_result(operation)
    assert result.state.exit_code == 7
    assert entry is None
```

::::

For an application-specific rule, inherit `AbstractCommitPolicy` and implement
`should_commit(context: OperationContext, result: InstanceResult) -> bool`. The
session passes the effective request and its original history position. The
method must not perform blocking I/O. The session validates API success before
calling it and requires a result image before committing an accepted result.
Policies are session components; pass the same policy when resuming a session.

Session commands save by default; `disposable=True` opts out. Snapshots are
lightweight and can run after every command, but stop the VM. An unchanged
filesystem can return the same image UUID; policies must not require a new UUID.

A `LazySession` snapshot also uses the underlying session's commit policy. If the
policy rejects that snapshot, the lazy session fails and leaves history unchanged.
It cannot restart from the previous image while claiming that changes were saved.
The policy sees the keepalive process result, not individual subprocess results.
Use the default policy to preserve snapshots after terminating the keepalive.
