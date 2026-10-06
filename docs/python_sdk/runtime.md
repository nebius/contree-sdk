# Keep one VM until explicit stop

Use `ContreeAsyncRuntime` for an environment that must retain one VM between
commands. Files and background processes remain in that VM until explicit stop,
a server lifetime limit, or a failure. This runtime supports the fixed lifetime
needed by agent environments such as Harbor.

`AsyncLazySession` can snapshot automatically between commands. A runtime uses a
manual snapshot policy and never schedules an idle or command-count shutdown.
After stop or failure, create a new runtime; the existing object does not restart.

## Execute several commands in one VM

Construction and context entry do not launch a VM. `start()` launches it explicitly;
`run()`, `execute()`, and `spawn_request()` start it when needed. Startup uses `sleep`
by default, so the base image must provide that command. Use `RuntimeOptions.vm_request`
to choose another keepalive command or provide startup files and VM options.

This example creates a file and reads it in the same VM. It then requests a snapshot
and advances the wrapped session only after the server confirms a result image.
Use a saved profile as described in {doc}`getting-started`.

<!--
name: async test_runtime_commands; fixtures: doc_runtime_client
-->

```python
from contree_client.asyncio import ContreeAsyncClient
from contree_client.models import InstanceNetworking, InstanceResourcesLimits

from contree_sdk import ContreeAsyncSession, RunRequest, RuntimeOptions, create_runtime

options = RuntimeOptions(
    vm_request=RunRequest(
        command="sleep",
        args=("2147483647",),
        disposable=False,
        networking=InstanceNetworking(enabled=False),
        resources_limits=InstanceResourcesLimits(max_layer_bytes=64 * 1024 * 1024),
    ),
    terminate_timeout=5,
    stop_timeout=30,
)
async with ContreeAsyncClient.from_profile() as client:
    session = ContreeAsyncSession(client, image="tag:tutorial-base")
    async with create_runtime(session, options=options) as runtime:
        await runtime.start()
        operation_uuid = runtime.operation_uuid
        await runtime.run(shell="mkdir -p /work; printf first > /work/result.txt", uid=0, gid=0)
        result = await runtime.run("cat", args=["result.txt"], cwd="/work", env={"LANG": "C"})
        assert result.state.exit_code == 0
        assert runtime.operation_uuid == operation_uuid
        entry = await runtime.stop(snapshot=True)
        assert entry is not None
        assert session.image_uuid == entry.image_uuid
```

<!--
name: test_runtime_commands
```python
assert len(doc_runtime_client.calls_for("spawn_instance")) == 1
assert len(doc_runtime_client.calls_for("follow_operation_events")) == 1
calls = doc_runtime_client.calls_for("operation_subprocess_create")
assert [call.args[0] for call in calls] == [operation_uuid, operation_uuid]
assert calls[0].kwargs["uid"] == 0
assert calls[1].kwargs["cwd"] == "/work"
assert not doc_runtime_client.calls_for("cancel_operation")
```
-->

A command returns `InstanceResult`, including separate stdout, stderr, and its
exit code. Nonzero process exits are results, not runtime failures. Use
`RunRequest(disposable=False, ...)` with `execute()`; `run()` selects that default.
Command `uid` and `gid` are numeric identities, passed through to the subprocess API.

VM options belong in `vm_request`. Commands cannot change networking, resource
limits, hostname, or startup attachments on an existing VM. The client currently
exposes `max_layer_bytes` and networking `enabled`; the runtime does not infer CPU,
RAM, or network-isolation guarantees from these fields. A timeout in `vm_request`
is the server's VM lifetime limit, separate from a command timeout.

## Stop a timed-out command without stopping its siblings

The command timeout covers subprocess creation, event waiting, and final-result
retrieval after the VM starts. Cancellation has the same cleanup behavior. The
runtime sends SIGKILL to that subprocess and waits for its exit event.

<!--
name: async test_runtime_timeout; fixtures: doc_runtime_client
```python
doc_runtime_client.auto_exit = False
```
-->

```python
from contree_client.asyncio import ContreeAsyncClient
from contree_sdk import ContreeAsyncSession, create_runtime

async with ContreeAsyncClient.from_profile() as client:
    session = ContreeAsyncSession(client, image="tag:tutorial-base")
    async with create_runtime(session) as runtime:
        try:
            await runtime.run("sleep", args=["60"], timeout=0.01)
        except TimeoutError:
            pass
```

<!--
name: test_runtime_timeout
```python
assert doc_runtime_client.calls_for("operation_subprocess_kill")[0].args == ("op-1", 2)
assert len(doc_runtime_client.calls_for("cancel_operation")) == 1  # Context exit discards the VM.
assert runtime.lifecycle.worker.done()
```
-->

If exit is not confirmed within `terminate_timeout`, the runtime fails and cancels
the entire VM. Sibling commands then fail too, because continued execution cannot
be established safely. Cancellation during subprocess creation can leave its ID
unknown; that uncertainty also fails the VM. A broken event stream or an unexpected
main-process exit is terminal. Inspect `runtime.error` for the cause.

`spawn_request()` returns a caller-managed subprocess handle. Use its event iterator
or `wait()`, and call `runtime.terminate(spid)` when abandoning it. A raw handle's
wait timeout does not provide the managed cleanup of `runtime.execute()`.
Use `send_stdin()` or `pipe_stdin()` with that handle's `spid`. Runtime stdin and
filtered `events()` subscriptions share the operation's single event reader.

## Stop, snapshot, and component ownership

`stop()` discards unsaved work. The runtime context manager uses this behavior.
`stop(snapshot=True)` stops admission, waits for accepted commands, and delegates
snapshot and commit to the existing session lifecycle. `stop_timeout` bounds the
graceful drain and snapshot waits. A failed or missing result image leaves session
history unchanged; stopping a VM alone is not proof of a snapshot.

Concurrent stop calls share one task. The first call selects whether to snapshot;
later calls return the same result or error. Cancellation of start or stop waits
for cleanup to finish before propagating. A cancelled startup waits for the
transport to return the operation ID, then cancels that operation. Configure the
client's network timeouts to bound its API requests.

The caller retains ownership of the session, client, store, and file transfer.
Do not mutate the wrapped session while the runtime is active. Live filesystem
transfer is separate from inspecting a saved image: `session.read_file()` cannot
observe unsaved VM changes.

Implement `AsyncRuntime` to provide an independent runtime. Pass a callable matching
`AsyncRuntimeFactory` through `create_runtime(..., factory=...)` to replace the
implementation. `ContreeAsyncRuntime.create_lifecycle()` is the narrower hook for
customizing its session lifecycle without replacing the shared event reader.
