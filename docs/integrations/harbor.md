# Harbor on ConTree SDK V2

The Harbor environment runs task commands as subprocesses in
one `AsyncLazySession` VM created by `create_async_sandbox_session`. The integration
uses the standard SDK session and operation classes. Files and background processes remain available between
commands. An idle snapshot stops the current VM and starts the next command from its saved image.
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

Downloads use the lazy session's `AsyncSessionInspector`, which reads the live VM
without a snapshot. Uploads use the SDK file transfer and apply uploaded files
to the live VM; directory uploads merge with existing contents. The adapter serializes Harbor
calls on one environment. Command output capture remains capped at 10 MiB per
stream. Live inspection requires a backend and client that support running-instance
file APIs.

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

`stop()` cancels the active VM and releases owned resources. Harbor's `delete`
argument (`--delete` / `--no-delete`) has no effect; neither value saves a final
image or retains a live VM. Earlier idle snapshots remain available.
Snapshotting an image with unsupported socket inodes can still fail. Use the
single-VM default for tasks that require those sockets until cleanup or backend
snapshot support is available.

The image import timeout and environment setup are bounded by Harbor's
`build_timeout_sec`. File uploads and downloads use 600-second per-command limits.
ConTree's backend command/VM maximum still applies; for example, a prior TB2.1
stage run rejected requested operation timeouts above 3,600 seconds.

Harbor enters the sandbox context in `start()` and releases it in `stop()`.
