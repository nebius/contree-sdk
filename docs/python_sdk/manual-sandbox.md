# Advanced: assemble a sandbox yourself

`create_sandbox_session` connects the SDK components into a familiar sandbox
interface. ConTree executes from filesystem images; a long-lived, mutable VM is
not its persistence model. The default `LazySession` provides continuity between
commands, then saves files at a snapshot boundary.

Use the factory for normal application code. Build the components directly when
you need to control their construction, share them, or replace their behavior.
These examples show the components behind the default sandbox and their cleanup
order. Configure a connection as described in {ref}`sandbox-connection` and use
an available image with `sleep`, a POSIX shell, and `cat`.

## What the factory supplies

| Component | Factory default | Your control |
| --- | --- | --- |
| Connection | Resolve a Profile from explicit arguments, ENV, or INI. | Supply a Profile or an already configured client. |
| Client | HTTPX for sync; aiohttp for async. | Select a client class or manage the connection yourself. |
| Store | A memory store for session history. | Supply SQLite or your own Store implementation. |
| File transfer | A client-backed transfer for uploads and saved-image reads. | Replace it or wrap it in a cached transfer. |
| Base session | `ContreeSession` or `ContreeAsyncSession`. | Extend request preparation, commits, or operation creation. |
| Lazy session | Reuse one VM; snapshot after 60 idle seconds. | Select a policy or subclass the lazy session. |
| Cleanup | Finish the session, then close owned storage and the client. | Manage component lifetimes explicitly; borrowed objects remain yours. |

The factory does not enable an upload cache by default. Pass `cache` and
`cache_ttl` to enable it, or construct the transfer shown in {doc}`caching`.

## Build the default components explicitly

Both programs write a file, read it in the same VM, and print
`Hello from ConTree!`. Normal exit saves pending filesystem changes. An exception
inside the lazy context discards changes since its last completed snapshot.

::::{tab} Sync

<!-- name: test_manual_sandbox; fixtures: sandbox_api, capsys -->

```python
from contree_client import profiles
from contree_client.httpx import ContreeClient

from contree_sdk import ContreeSession, LazySession
from contree_sdk.files import ClientFileTransfer
from contree_sdk.session import IdleSnapshotPolicy
from contree_sdk.store import SyncMemoryStore


def main() -> None:
    profile = profiles.from_env() or profiles.resolve_profile()
    with ContreeClient.from_profile(profile) as client:
        with SyncMemoryStore() as storage:
            transfer = ClientFileTransfer(client)
            base = ContreeSession(client, image="tag:alpine:latest", store=storage, file_transfer=transfer)
            policy = IdleSnapshotPolicy(60)
            with LazySession(base, snapshot_policy=policy) as sandbox:
                sandbox.run(shell="echo 'Hello from ConTree!' > /message.txt")
                result = sandbox.run("cat", args=["/message.txt"])
                print(result.stdout.as_text(), end="")


main()
```

<!--
name: test_manual_sandbox
```python
assert len(sandbox_api.sync.calls_for("spawn_instance")) == 1
assert len(sandbox_api.sync.calls_for("operation_subprocess_create")) == 2
assert sandbox_api.sync.calls_for("operation_subprocess_kill")[0].args[1] == 1
assert len(sandbox_api.sync.calls_for("get_operation_status")) == 1
assert capsys.readouterr().out == "Hello from ConTree!\n"
```
-->

::::

::::{tab} Async

<!-- name: test_manual_sandbox_async; fixtures: sandbox_api, capsys -->

```python
import asyncio

from contree_client import profiles
from contree_client.aiohttp import ContreeAsyncClient

from contree_sdk import AsyncLazySession, ContreeAsyncSession
from contree_sdk.files import AsyncClientFileTransfer
from contree_sdk.session import IdleSnapshotPolicy
from contree_sdk.store import AsyncMemoryStore


async def main() -> None:
    profile = profiles.from_env() or profiles.resolve_profile()
    async with ContreeAsyncClient.from_profile(profile) as client:
        async with AsyncMemoryStore() as storage:
            transfer = AsyncClientFileTransfer(client)
            base = ContreeAsyncSession(client, image="tag:alpine:latest", store=storage, file_transfer=transfer)
            await base.ensure_ready()
            policy = IdleSnapshotPolicy(60)
            async with AsyncLazySession(base, snapshot_policy=policy) as sandbox:
                await sandbox.run(shell="echo 'Hello from ConTree!' > /message.txt")
                result = await sandbox.run("cat", args=["/message.txt"])
                print(result.stdout.as_text(), end="")


asyncio.run(main())
```

<!--
name: test_manual_sandbox_async
```python
assert len(sandbox_api.async_client.calls_for("spawn_instance")) == 1
assert len(sandbox_api.async_client.calls_for("operation_subprocess_create")) == 2
assert sandbox_api.async_client.calls_for("operation_subprocess_kill")[0].args[1] == 1
assert len(sandbox_api.async_client.calls_for("get_operation_status")) == 1
assert capsys.readouterr().out == "Hello from ConTree!\n"
```
-->

::::

`ensure_ready()` resolves the initial image and history; it does not start a VM.
The first lazy command starts the VM. The lazy context exits before the store and
client contexts, so saving can still use both components.

These programs show ordinary component assembly. The factory also handles partial
entry failures, preserves a body exception if cleanup fails, and joins async
cleanup under repeated cancellation. Reuse its context implementation when those
guarantees are needed in a custom factory; see {doc}`reference/sandbox`.

## Change one component without rebuilding everything

The factory accepts the same extension points. This selects a custom base session
that adds a default command timeout. Each command uses an independent operation.

<!--
name: test_factory_custom_session; fixtures: doc_api
```python
doc_api.complete()
```
-->

```python
from dataclasses import replace

from contree_sdk import ContreeSession, RunRequest, create_sync_sandbox_session


class TimedSession(ContreeSession):
    def prepare_request(self, request: RunRequest) -> RunRequest:
        request = super().prepare_request(request)
        return replace(request, timeout=30 if request.timeout is None else request.timeout)


with create_sync_sandbox_session(image="tag:alpine:latest", session_type=TimedSession) as session:
    session.run("echo", args=["Custom request policy"])
```

<!--
name: test_factory_custom_session
```python
assert isinstance(session, TimedSession)
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["timeout"] == 30
```
-->

Selecting `ContreeSession` or a subclass changes execution semantics: commands
are disposable by default, and `disposable=False` saves each result. Selecting a
lazy subclass retains a shared VM and snapshot boundaries. `session_kwargs`
configures the selected class; `storage`, `file_transfer`, and `commit_policy`
configure its underlying base session. To supply a custom base session inside a
lazy wrapper, assemble them directly as above.

Continue with {doc}`customization` for public hooks, {doc}`architecture` for
component contracts, and {doc}`lazy-session` for snapshot policies. Snapshots
preserve files, not processes, memory, or sockets.
