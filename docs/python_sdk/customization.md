# Adapt the SDK to your application

Start with the smallest change your application needs. For example, add a default
timeout in `prepare_request()` before replacing operation handling.
Use a public contract when replacing a component. Subclass a built-in implementation
when changing one policy or lifecycle step. All imports in the examples below are
public SDK imports. HTTP transports remain a separate `contree-client` concern.

## Customize command policy and operations

`RunRequest` is a frozen configuration value. Its argument tuple and environment
mapping are copied at construction. Files and stdin remain caller-owned resources.
Use `dataclasses.replace()` to apply policy without mutating the caller's request.

This example rejects shell commands, applies a default timeout, and counts waits.
It uses a saved profile as described in {doc}`getting-started`. The complete code
includes both the session policy and its operation implementation.

<!--
name: test_custom_policy; fixtures: doc_api, capsys
```python
doc_api.complete()
```
-->

```python
from dataclasses import replace

from contree_client.models import InstanceResult, InstanceSpawnResponse
from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession, OperationContext, RunRequest
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


with ContreeClient.from_profile() as client:
    session = PolicySession(client, image="tag:tutorial-base")
    operation = session.spawn("echo", args=["hello"])
    result = operation.wait()
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

The execution order is:

1. Construct a `RunRequest` from `run()` or `spawn()` arguments, or pass it to `execute()` directly.
2. Load session state. The synchronous session initializes in its constructor; the async session initializes on first use.
3. Call `prepare_request()` before uploads or command submission.
4. Capture the source image, history entry, and branch. Prepare files and stdin through the file-transfer component.
5. Call `submit_request()` with the effective request and prepared inputs.
6. Call `create_operation()`. Bind its `OperationContext` to the effective request and source history position.
7. For `execute()` or an awaited `run()`, wait for completion and commit the effective request when `disposable=False`.

A policy can change persistence, timeout, environment, or other request fields.
History uses the effective request, not the original arguments. A custom operation
factory must return the matching lifecycle contract. If that factory fails after
submission, the session attempts remote cancellation and preserves the factory error.

`create_store()` and `create_file_transfer()` supply defaults only when no component
was passed explicitly. Constructor-time factories must not depend on attributes
that a subclass initializes after `super().__init__()`.

## Choose an extension boundary

| Requirement                                | Extension boundary                                             | Consumer                                                      |
| ------------------------------------------ | -------------------------------------------------------------- | ------------------------------------------------------------- |
| Add command defaults or reject commands    | Override `prepare_request(RunRequest)`                         | Session `run`, `execute`, and `spawn`                         |
| Resolve images from another naming scheme  | Override `resolve_image(image)`                                | Session initialization                                        |
| Modify transport submission                | Override `submit_request(...)`                                 | Session `spawn_request`                                       |
| Instrument or replace operation lifecycle  | Override `create_operation(response, context)`                 | Session `spawn_request`                                       |
| Replace subprocess handles                 | Override `Operation.create_subprocess(spid, queue)`            | Operation `run`                                               |
| Transform or observe live events           | Override `Operation.events(...)`                               | Direct iteration and rich-mode event consumer                 |
| Upload from another storage service        | Implement `SyncFileTransfer` or `AsyncFileTransfer`            | Session `file_transfer=`                                      |
| Store history remotely                     | Implement `SyncStore` or `AsyncStore`                          | Session and builder `store=`                                  |
| Replace build caching                      | Implement `SyncCache` or `AsyncCache`                          | Builder `cache=`                                              |
| Add or replace Dockerfile instructions     | Register a `DockerKeyword` with `DockerfileParser`             | Builder `parser=`                                             |
| Use a session subclass inside builds       | Pass `session_factory=`                                        | Fresh builds and cache hits                                   |
| Add per-build state                        | Set `context_class` or override `create_context(BuildRequest)` | Builder `build`                                               |
| Audit or restrict build instructions       | Override `execute_directive(directive, context)`               | Parsed directives, stage sealing, and final pending-file step |
| Use another execution engine in deepagents | Implement `SyncExecutor` or `AsyncExecutor`                    | Sandbox adapters                                              |

Sync methods stay synchronous. Async methods perform native asynchronous I/O.
There is no hidden event loop bridging between the contracts. Keep async overrides
nonblocking, or explicitly offload local blocking work when necessary.

## Implement file transfer

Inherit `SyncFileTransfer` or `AsyncFileTransfer` and implement:

- `upload(UploadFileSpec) -> FileSpec`: return a file identifier valid on the session's server.
- `read_file(image_uuid, path) -> bytes`: return exact bytes from the specified image.

The default `prepare_files()` normalizes inputs and calls `upload()` for each file.
The async implementation cancels and joins sibling uploads if one fails. Override
this method for batching or bounded concurrency. Override `read_stdin()` to support
additional input handling. Never close a caller-owned input stream.

Inject a component with `file_transfer=`. `ClientFileTransfer` and
`AsyncClientFileTransfer` provide the standard implementations and can also be
subclassed. Import `UploadFileSpec`, `UploadedFile`, `InputSource`, and the readable
protocols from `contree_sdk.files`.

## Implement history and cache storage

History implementations inherit `SyncStore` or `AsyncStore`. Their contract includes
session metadata, history lookup, branch navigation, and atomic append. A custom
store must preserve these invariants:

- An entry's parent belongs to the same session.
- `append(expected_tip=...)` compares and updates the branch in one atomic operation.
- `expected_tip=None` requires a new branch; omitted `expected_tip` disables the comparison.
- A conflict raises `SessionConflictError` and leaves history and branch pointers unchanged.
- Metadata and history returned to callers must not expose mutable internal state.
- Navigation failures leave the previous branch position intact.

Cache implementations inherit `SyncCache` or `AsyncCache`. `get()` returns `None`
for a miss. `set()` replaces a value within its namespace. Namespace isolation is
part of the contract. SQLite caches require JSON-serializable values.

Stores and caches have a `close()` method and matching context-manager methods.
The default close is a no-op for implementations without resources. Override it
for connections or files. Sessions and builders do not close supplied components;
the application decides their lifetime. Explicit components are retained even when
they evaluate as false.

## Replace an integration backend

The framework adapters depend only on `SyncExecutor` or `AsyncExecutor`:

- `session_id` identifies the execution context.
- `execute(RunRequest)` returns `contree_client.models.InstanceResult`.
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

## Extend Dockerfile builds

Create a parser per dialect, then register your directive:

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
from contree_sdk.docker import ContreeDockerBuilder, ContreeAsyncDockerBuilder
from contree_sdk.store import SyncMemoryStore, AsyncMemoryStore

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
`session_id`, `store`, and `image` as keyword arguments. It returns a `ContreeSession` or `ContreeAsyncSession` implementation.
Both fresh layers and cache hits use this factory. Set `context_class` to a
`BuildContext` or `AsyncBuildContext` subclass when only additional methods or state
are needed. Override `create_context(BuildRequest)` for a different construction
policy. `execute_directive()` intercepts normal steps, stage sealing, and final file materialization.
Custom directives that execute nested directives must call `context.execute_directive()`.
A custom `create_context()` must pass `directive_executor=self.execute_directive`
to preserve this dispatch for nested steps.

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

The public factory hooks support independent contract implementations. The supplied subprocess event queue is part of that factory signature. Other
internal queue management, worker threads, SQLite schemas, and helper module layouts
are implementation details; override the documented methods instead of changing those details.

## Resolve application-specific image names

A sync override runs during session construction. An async override runs during
`ensure_ready()` or the first operation. Return a valid UUID for the selected server;
the example uses a mapping that your application supplies.

<!--
name: test_resolve_policy; fixtures: doc_api
-->

```python
from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession


class NamedImageSession(ContreeSession):
    def resolve_image(self, image: str) -> str:
        return {"test-base": "8a0269a2-7720-4daa-aa96-dca93b20bb33"}[image]


with ContreeClient.from_profile() as client:
    session = NamedImageSession(client, image="test-base")
    print(session.image_uuid)
```

<!--
name: test_resolve_policy
```python
assert session.image_uuid == "8a0269a2-7720-4daa-aa96-dca93b20bb33"
assert session.client.calls_for("resolve_image") == []
```
-->
