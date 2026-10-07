---
icon: clock
---

# Reuse a sandbox between commands

`LazySession` and `AsyncLazySession` keep one VM available for several commands.
They start that VM only when a command is requested. Construction, context entry,
and a snapshot of an unused wrapper do not start a VM. A snapshot policy decides when to save its filesystem as one session-history entry.
Saving drains active commands and stops the current VM.

Each command is a subprocess in the shared VM. A successful `run()` means that
subprocess finished. Its filesystem changes become a saved image only after a
snapshot completes. This differs from `ContreeSession.run(disposable=False)`,
which starts a VM and saves an image for each command.

## Run commands and save their shared state

Use the connection variables from {doc}`getting-started`. The base image must
provide `sleep` for the default keepalive process. Override `keepalive_request()`
when an image needs a different long-running main process.

::::{tab} Sync

<!--
name: test_lazy_session; fixtures: lazy_api
-->

```python
import os

from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession, LazySession
from contree_sdk.session import IdleSnapshotPolicy

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    with LazySession(session, snapshot_policy=IdleSnapshotPolicy(30)) as lazy:
        first = lazy.run(shell="echo first > /work.txt")
        second = lazy.run(shell="echo second >> /work.txt")
        saved = lazy.snapshot()
        assert saved is not None
        assert session.image_uuid == saved.image_uuid
        lazy.run(shell="cat /work.txt")
```

<!--
name: test_lazy_session
```python
assert len(lazy_api.sync.calls_for("spawn_instance")) == 2
assert len(lazy_api.sync.calls_for("operation_subprocess_create")) == 3
assert len(lazy_api.sync.calls_for("follow_operation_events")) == 2
assert not lazy_api.sync.calls_for("wait_operation")
assert lazy_api.sync.calls_for("spawn_instance")[1].args[1] == saved.image_uuid
assert lazy.phase == "closed"
assert [entry.kind for entry in session.history()[0]] == ["init", "run", "run"]
```
-->

::::

::::{tab} Async

Top-level `await` requires an async function or a compatible notebook.

<!--
name: async test_lazy_session_async; fixtures: lazy_api
-->

```python
import os

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import AsyncLazySession, ContreeAsyncSession
from contree_sdk.session import IdleSnapshotPolicy

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
    async with AsyncLazySession(session, snapshot_policy=IdleSnapshotPolicy(30)) as lazy:
        first = await lazy.run(shell="echo first > /work.txt")
        second = await lazy.run(shell="echo second >> /work.txt")
        saved = await lazy.snapshot()
        assert saved is not None
        assert session.image_uuid == saved.image_uuid
        await lazy.run(shell="cat /work.txt")
```

<!--
name: test_lazy_session_async
```python
assert len(lazy_api.async_client.calls_for("spawn_instance")) == 2
assert len(lazy_api.async_client.calls_for("operation_subprocess_create")) == 3
assert len(lazy_api.async_client.calls_for("follow_operation_events")) == 2
assert not lazy_api.async_client.calls_for("wait_operation")
assert lazy_api.async_client.calls_for("spawn_instance")[1].args[1] == saved.image_uuid
assert lazy.phase == "closed"
assert [entry.kind for entry in (await session.history())[0]] == ["init", "run", "run"]
```
-->

::::

`snapshot()` closes admission, waits for accepted subprocesses to exit, and signals
the main process with `SIGTERM`. It then waits for the final operation response.
Only a successful response with a result image can advance session history.
A concurrent history change causes a conflict instead of overwriting that change.

After a snapshot, the next command starts a new VM from the saved image. Normal
context exit calls `close()`, which saves pending work and closes the wrapper.
An exception inside the context calls `abort()` and cancels unsaved work.
An already running snapshot finishes before `abort()` returns.
The supplied session, client, and store remain caller-owned.

## Choose a snapshot policy

The same policy classes work with both wrappers. Each instance owns its state and
timers: create a separate instance for each lazy session. The default is
`IdleSnapshotPolicy(60)`.

| Policy                               | When it requests a snapshot                                                  |
| ------------------------------------ | ---------------------------------------------------------------------------- |
| `IdleSnapshotPolicy(seconds)`        | No command is active and the idle interval has elapsed since the last exit.  |
| `CommandCountSnapshotPolicy(limit)`  | The VM has accepted `limit` commands. Further commands wait for the next VM. |
| `CompositeSnapshotPolicy(*policies)` | Any child policy requests a snapshot.                                        |

This composition closes admission after ten commands or thirty idle seconds.
Active commands finish before the VM stops.

<!--
name: test_lazy_policies
-->

```python
from contree_sdk.session import (
    CommandCountSnapshotPolicy,
    CompositeSnapshotPolicy,
    IdleSnapshotPolicy,
    SnapshotEvent,
)

idle = IdleSnapshotPolicy(30)
count = CommandCountSnapshotPolicy(10)
policy = CompositeSnapshotPolicy(idle, count)

policy.notify(SnapshotEvent.RESET)
ready = policy.should_snapshot()
for _ in range(10):
    policy.notify(SnapshotEvent.COMMAND_STARTED)

assert ready.result(timeout=1) is None
assert count.should_snapshot().done()
assert not idle.should_snapshot().done()
policy.notify(SnapshotEvent.CLOSE)
```

The counter includes reservations made before subprocess creation. Parallel callers
cannot admit an extra command beyond the limit. Nonzero exits count as commands.
A creation error fails the current VM lifecycle; the SDK does not retry that
command automatically. All counters reset when the next VM starts.

## Define a policy

`notify(event)` receives lifecycle and execution notifications. `should_snapshot()`
returns one `concurrent.futures.Future[None]` for the current VM cycle. Resolving it
requests a snapshot. A failed or unexpectedly cancelled future fails the wrapper.
The session closes admission and waits for accepted commands before stopping.

| Event              | Meaning                                                           |
| ------------------ | ----------------------------------------------------------------- |
| `RESET`            | Clear the previous cycle's state and create a new pending future. |
| `COMMAND_STARTED`  | A command has been accepted, before subprocess creation.          |
| `COMMAND_FINISHED` | Its exit event arrived, including a nonzero exit.                 |
| `CLOSE`            | Cancel timers and release policy resources.                       |

The base class implements future creation and cancellation. Call its constructor
and `notify()` implementation from overrides. Keep notifications nonblocking.
Policies own counters, timers, and scheduling. `LazySession` receives no deadlines
and does not poll policies.

This custom policy requests a snapshot after two observed exits. It does not depend
on the application calling each subprocess handle's `wait()`.

<!--
name: test_custom_snapshot_policy; fixtures: lazy_api
-->

```python
import os
from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession, LazySession
from contree_sdk.session import AbstractSnapshotPolicy, SnapshotEvent


class AfterTwoExits(AbstractSnapshotPolicy):
    def __init__(self) -> None:
        super().__init__()
        self.finished = 0

    def notify(self, event: SnapshotEvent) -> None:
        super().notify(event)
        if event is SnapshotEvent.RESET:
            self.finished = 0
        elif event is SnapshotEvent.COMMAND_FINISHED:
            self.finished += 1
            if self.finished == 2 and not self.future.done():
                self.future.set_result(None)


with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image="tag:ubuntu:24.04")
    with LazySession(session, snapshot_policy=AfterTwoExits()) as lazy:
        lazy.run("echo", args=["first"])
        lazy.run("echo", args=["second"])
        saved = lazy.snapshot()
        assert saved is not None
```

<!--
name: test_custom_snapshot_policy
```python
assert len(lazy_api.sync.calls_for("spawn_instance")) == 1
assert len(lazy_api.sync.calls_for("operation_subprocess_create")) == 2
assert len(session.history()[0]) == 2
assert lazy.phase == "closed"
```
-->

`RESET` can occur after saving and before another VM starts. It must not create a VM
or start an idle timer. `CLOSE` must be safe to repeat, including after failure.
A command-creation failure closes the policy and cancels pending timers.

## Await a policy decision

Sync code can wait on the policy future with `result()`. Async code can use
`asyncio.wrap_future()` without a thread pool. Shield the wrapper so cancelling an
individual waiter does not cancel the shared policy decision.

This standalone example uses the same idle policy as an async lazy session. The
policy creates an event-loop timer internally when the command finishes.

<!--
name: async test_async_policy_future
-->

```python
import asyncio

from contree_sdk.session import IdleSnapshotPolicy, SnapshotEvent

policy = IdleSnapshotPolicy(0.01)
policy.notify(SnapshotEvent.COMMAND_STARTED)
policy.notify(SnapshotEvent.COMMAND_FINISHED)
ready = policy.should_snapshot()
try:
    await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(ready)), timeout=1)
finally:
    policy.notify(SnapshotEvent.CLOSE)
```

`IdleSnapshotPolicy` uses `loop.call_later()` in async code and `threading.Timer`
in sync code. It cancels stale timers on admission, reset, and close. Supply
`timer_factory=` when the policy needs a different scheduler. The factory receives
an interval and a callback and returns a handle with `cancel()`.

## Run concurrent commands

Sync callers can share a wrapper between threads. Async callers can use
`asyncio.gather()`. Admission and VM shutdown are serialized; subprocesses can run
concurrently. Commands submitted while a snapshot is in progress wait for the
next VM. File writes and application locks remain the application's responsibility.

<!--
name: async test_lazy_parallel; fixtures: lazy_api
-->

```python
import os
import asyncio

from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import AsyncLazySession, ContreeAsyncSession
from contree_sdk.session import CommandCountSnapshotPolicy

async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeAsyncSession(client, image="tag:ubuntu:24.04")
    async with AsyncLazySession(session, snapshot_policy=CommandCountSnapshotPolicy(2)) as lazy:
        results = await asyncio.gather(
            lazy.run("echo", args=["first"]),
            lazy.run("echo", args=["second"]),
            lazy.run("echo", args=["third"]),
        )
        await lazy.snapshot()
```

<!--
name: test_lazy_parallel
```python
assert len(results) == 3
assert len(lazy_api.async_client.calls_for("spawn_instance")) == 2
assert len(lazy_api.async_client.calls_for("follow_operation_events")) == 2
assert lazy.phase == "closed"
```
-->

`spawn()` returns a subprocess handle immediately. Exit events update the policy
counters even if the application never calls the handle's `wait()` method.
One operation reader supplies those events, public event subscriptions, and waits.
See {doc}`operation` for stream ownership and cancellation behavior.

## Handle errors and history boundaries

- A nonzero subprocess exit remains an `InstanceResult`; it does not discard filesystem changes.
- A command timeout or cancelled async command wait attempts to kill that subprocess with `SIGKILL`.
  The VM remains active until an exit event confirms completion.
- A failed subprocess creation, lost event stream, or unexpected main-process exit fails the wrapper.
  Inspect `lazy.error`; subsequent calls raise an error instead of starting another VM silently.
- A failed snapshot leaves the saved history unchanged. After a history conflict,
  `lazy.operation.response` retains the remote response for explicit recovery.
- `snapshot(timeout=...)` limits the caller's wait. The snapshot continues after
  that timeout or cancellation. `snapshot_timeout` limits the operation wait during saving.
- `close(timeout=...)` stops admission and waits for saving. `abort()` cancels unsaved
  work. Always close or abort a wrapper to release its controller.

Call `snapshot()` before `read_file()`, `create_branch()`, `switch_branch()`, or
`rollback()`. These methods require a saved boundary. They do not inspect or modify
a live VM. Do not mutate the wrapped session directly while its VM is active.

Commands default to `disposable=False`. Explicit disposable requests are rejected:
use a separate `ContreeSession` for isolated work. `files`, `preserve_env`, and
`hostname` are also rejected on live commands. Prepare input files in a saved image first. Configure VM-wide options through
`keepalive_request()`. Per-command `env`, `cwd`, and stdin are supported.
When using `execute(RunRequest(...))`, set `disposable=False` on the request.
