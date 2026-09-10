# Harbor

Run Harbor tasks on ConTree using a prebuilt Linux image. The integration uses
ConTree filesystem snapshots: files persist between commands, while processes and
in-memory state do not. This supports Oracle tasks and agents that communicate
through files and sequential commands.

## Installation and authentication

Harbor is optional and requires Python 3.12 or newer. The integration targets
Harbor 0.22.x; ordinary SDK usage continues to support Python 3.10+.

```bash
pip install 'contree-sdk[harbor]'
```

Install the extra in the same Python environment as the `harbor` executable. For
an existing isolated uv tool installation, use:

```bash
uv tool install harbor --with 'contree-sdk[harbor]'
```

Authentication uses `contree_client.httpx.ContreeAsyncClient.from_profile()`.
Configure a ConTree profile first, as described in
[client authentication](../python_sdk/getting-started.md). The adapter resolves
the profile from `--ek profile=NAME`, then `CONTREE_PROFILE`, then the active
profile in the ConTree configuration. Credentials stay on the host.

## Running a task

```bash
harbor run --path /path/to/task \
  --agent oracle \
  --env contree_sdk.harbor:ConTreeEnvironment
```

No modification to Harbor's built-in environment registry is needed.

The task must contain `task.toml`, `instruction.md`, an `environment/` directory,
`solution/solve.sh` for Oracle, and `tests/test.sh` for verification. Set a prebuilt
image in `task.toml`:

```toml
[environment]
docker_image = "docker.io/library/ubuntu:24.04"
workdir = "/app"
build_timeout_sec = 180
```

The image must run as root and provide Bash and tar. Startup checks these
requirements. If `environment/` contains files and no Dockerfile or Compose
definition, Harbor's prebuilt-image convention copies its contents into the
configured workdir, or the image's default workdir.

The SDK repository includes a complete example:

```bash
uv run --extra harbor harbor run --path examples/harbor \
  --agent oracle --env contree_sdk.harbor:ConTreeEnvironment
```

The Oracle solution writes `/app/greeting.txt`; the verifier checks its contents
and writes a reward of `1`. Harbor downloads Oracle logs, verifier output, rewards,
and artifacts into its job directory.

## Configuration support

| Setting | Behavior |
| --- | --- |
| `docker_image` | Required. Resolve an existing ConTree image or import the OCI image. UUID references also work. |
| Dockerfile | No builds. A supplied prebuilt image takes precedence; `--force-build` with a Dockerfile fails. |
| Docker Compose and overlays | Unsupported. |
| `build_timeout_sec` | Bounds image import and environment preparation. |
| `workdir` | Default command directory; per-command `cwd` overrides it. |
| Task/trial/command environment variables | Harbor resolves host substitutions. Precedence: task, trial, command, then scoped Harbor overrides. Commands invoke `/bin/bash -c` directly, independently of `SHELL`. Supplied variables are saved into subsequent snapshots with `preserve_env=True`. |
| `HOME` | When unset, initialized from the executing user's home directory using Bash. Image-defined and explicit Harbor values, including an empty value, are preserved. |
| `cpus`, `memory_mb`, and numeric overrides | Not enforced. Harbor `auto` mode warns when a value is supplied; `ignore` explicitly accepts this. `limit`, `request`, and `guarantee` fail. |
| `storage_mb` and `override_storage_mb` | Accepted with a warning and ignored. The override takes precedence when reporting the requested value. The client's writable-layer byte limit is not equivalent to a total storage allocation. |
| GPUs, GPU types, TPUs, Windows | Unsupported. |
| Networking | Public networking only. No-network, allowlist, and unsupported phase policies fail before startup. |
| `user` / agent default user | Root or UID 0 only. Other explicit users fail rather than being ignored. |
| Mounts | Harbor's standard log mounts use file transfers. Custom host mounts are unsupported. |
| Healthchecks and skills | Supported through Harbor's exec and file-transfer helpers. A healthcheck cannot establish persistence of a background service. |
| Task MCP servers | Unsupported in this initial integration. |
| Interactive attach and background services across exec calls | Unsupported. |

### Harbor capability declarations

All `EnvironmentCapabilities` flags are explicitly `False` for the current
adapter. Harbor treats command execution and file transfers as ordinary
environment methods; these supported operations do not have capability flags.

| Capability | Reason |
| --- | --- |
| `gpus`, `tpus` | The SDK's `Session.run()` has no accelerator allocation options. |
| `disable_internet` | The SDK's `RunRequest` and execution path do not expose networking controls. The lower-level `contree-client` has `InstanceNetworking(enabled=False)`, but the adapter cannot advertise this until the SDK forwards it and the adapter applies Harbor's policy to every command. |
| `network_allowlist` and all `network_allowlist_*` flags | No SDK support for filtering egress by hostname, IP address, or CIDR. |
| `dynamic_network_policy` | The adapter has no implementation for changing and enforcing network policies between phases. |
| `windows` | The adapter requires Linux images and uses POSIX paths, Bash, and tar. |
| `mounted` | Logs are copied from snapshots, not shared with the host through mounted directories. |
| `docker_compose` | SDK sessions do not manage Compose services or route operations to individual services. |

The separate `EnvironmentResourceCapabilities` declaration also sets
`cpu_limit`, `cpu_request`, `memory_limit`, and `memory_request` to `False`:
the SDK does not expose these allocations. Command timeouts, output limits,
and the lower-level client's writable-layer size limit do not provide them.

Capability declarations do not automatically exclude incompatible benchmark
tasks. Select a compatible subset before running; GPU tasks require a provider
that can allocate GPUs. Check separate verifier environments as well as agent
environments when selecting tasks.

### Adapter options

Adapter-specific kwargs can be supplied through Harbor's `--ek` option:

```bash
harbor run --path /path/to/task --agent oracle \
  --env contree_sdk.harbor:ConTreeEnvironment \
  --ek profile=my-profile --ek operation_timeout=1800
```

`operation_timeout` defaults to 1000 seconds and applies when a command has no
explicit timeout. Directory uploads use a 600-second execution timeout.
Command output capture is capped at 10 MiB per stream; truncation produces a
warning. File and directory downloads do not use command-output capture.

Python callers can pass `client=Contree(...)` to the environment constructor. An
injected client remains owned by the caller; profile-created clients are closed
by the adapter.

## State and cleanup

Each completed command creates the next filesystem snapshot, including commands
with nonzero exit codes. Operations on one environment are serialized to avoid
losing concurrent filesystem updates; different trials use independent sessions.

If a command times out, is cancelled, or fails at the API level, the adapter keeps
the last completed snapshot for log collection. Changes and logs from the failed
operation may be unavailable. Commands are not automatically replayed.

Stopping the environment cancels an active command and closes an owned client.
With `delete=False` (Harbor's `--no-delete`), the final image gets a unique
`harbor-...` tag, reported in the log. The environment exposes
`final_image_uuid` and `retained_image_tag` for Python callers. With `delete=True`,
snapshots remain untagged and their lifetime is controlled by the service. The
adapter does not physically delete images or remove shared source-image tags.
