# Harbor on ConTree SDK V2

The Harbor environment runs task commands and file transfers as subprocesses in
one `AsyncLazySession` VM created by `create_async_sandbox_session`. The integration
uses the standard SDK session and operation classes. Files and background processes remain available between
commands. A trial's final stop completes the active operation and saves its result
image. An idle snapshot stops the current VM and starts the next command from its saved image.
Background processes do not survive that boundary.

The backend targets Harbor 0.22.x and requires Python 3.12 or newer. Install with
`pip install 'contree-sdk[harbor]'` in the environment that runs Harbor.

```bash
harbor run -t hello-world/hello-world -a oracle \
  --env contree_sdk.harbor:ConTreeEnvironment --ek profile=stage
```

The `stage` profile is an example; use a profile pointing at the intended ConTree
backend. Authentication remains in the host's ConTree profile. Python callers may
pass `client=ContreeAsyncClient(...)`; injected clients remain caller-owned.

Tasks need a prebuilt OCI registry image in `[environment].docker_image`, such as
`docker.io/library/ubuntu:24.04`. Startup imports the image through the SDK's
cached import helper. Native ConTree UUID and `tag:` references are not supported
by this adapter. The image must provide Bash and `sleep`. Commands use the image's
default user unless Harbor supplies a numeric UID or `root`; other user names are
not supported. Dockerfile builds, Compose, GPUs, custom mounts,
and restricted networking are not supported. Harbor's standard log mount paths are
replaced by file transfers. Commands inherit the image's `WORKDIR` and `HOME`
unless Harbor supplies overrides. Task/trial/command environment precedence is
resolved by Harbor and forwarded to each subprocess. The adapter does not parse
Dockerfiles or add shell fallbacks.

File transfers use the shared lazy session's native live upload/download APIs.
Directory uploads merge tar archives through the backend file API; downloads
stream files or archives directly. File contents never enter command stdin/stdout
or operation events, and transfers do not require a snapshot. The adapter serializes
Harbor calls on one environment. Command output capture remains capped at 10 MiB
per stream. This requires the backend live-file feature and its corresponding
client build; the current development client is supplied as a wheel.

`--ek operation_timeout=1800` changes the default command timeout (1000 seconds).
Harbor's task command timeout overrides it. `snapshot_timeout` defaults to 120
seconds and `terminate_timeout` to 5 seconds. The keepalive VM's `vm_timeout`
defaults to 3,600 seconds (`--ek vm_timeout=SECONDS`); without this setting,
the stage backend ends a VM after 60 seconds. The optional
`--ek snapshot_idle_sec=300` requests snapshots after 300 seconds without a
running command; later commands restart the VM. The default has no idle snapshot,
so long-running background processes can remain alive through the trial. A trial that must keep services alive beyond the backend's maximum VM lifetime
still requires backend support or a task-specific cleanup and snapshot boundary. A command timeout kills that subprocess and waits for its
exit; an unconfirmed kill fails the VM.

`stop()` closes the session, saving the final operation's result image and releasing
owned resources. Harbor's `delete` argument (`--delete` / `--no-delete`) is accepted
for compatibility and has no effect. Stopping does not delete images or create
tags; image retention is managed separately by ConTree. If saving fails, cleanup
aborts the remaining operation and propagates the error.
Snapshotting an image with unsupported socket inodes can still fail. Use the
single-VM default for tasks that require those sockets until cleanup or backend
snapshot support is available.

The image import timeout and environment setup are bounded by Harbor's
`build_timeout_sec`. File uploads and downloads use 600-second per-command limits.
ConTree's backend command/VM maximum still applies; for example, a prior TB2.1
stage run rejected requested operation timeouts above 3,600 seconds.

The same VM behavior is available through the public sandbox factory:

<!--
name: async test_harbor_sandbox; fixtures: sandbox_api, monkeypatch
```python
from contree_client.profiles import Profile

monkeypatch.setattr(
    "contree_sdk.connection.ConnectionConfig.resolve_profile",
    lambda self: Profile(name="stage", url="https://contree.invalid", token="documentation-token", auth_type="iam"),
)
```
-->

```python
from contree_sdk import RunRequest, create_async_sandbox_session
from contree_sdk.session import ManualSnapshotPolicy

async with create_async_sandbox_session(
    image="tag:task-image",
    profile="stage",
    session_kwargs={
        "snapshot_policy": ManualSnapshotPolicy(),
        "vm_request": RunRequest(command="sleep", args=("2147483647",), timeout=3600),
        "snapshot_timeout": 120,
    },
) as sandbox:
    await sandbox.run(shell="start-my-service &")
    await sandbox.run(shell="check-my-service")
```

<!--
name: async test_harbor_sandbox
```python
assert len(sandbox_api.async_client.calls_for("spawn_instance")) == 1
assert len(sandbox_api.async_client.calls_for("operation_subprocess_create")) == 2
```
-->

`vm_request` configures the parent VM; each command has its own timeout. Ordinary
context exit saves a snapshot, while exceptional exit discards unsaved work.
Harbor enters and exits this context across its `start()` and `stop()` calls.
Normal shutdown saves the final image; abort is reserved for failure cleanup.
