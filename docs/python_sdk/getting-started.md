---
icon: hand-wave
---

# Your first sandbox

Create a sandbox, execute a command, and print its output. The SDK loads your
connection from environment variables or a saved profile by default.

## Create a sandbox

Save either program as `first_command.py` and run it with Python. Both programs
print `Hello from ConTree!` and save pending work when the context exits.
Construction performs no I/O. Context entry prepares the session; the first
command starts the VM.

::::{tab} Sync

<!-- name: test_first_command; fixtures: sandbox_api, capsys -->

```python
"""Run a command in a sandbox and print its output."""

from contree_sdk import create_sandbox_session


def main() -> None:
    with create_sandbox_session(image="tag:alpine:latest") as session:
        result = session.run("echo", args=["Hello from ConTree!"])
        print(result.stdout.as_text(), end="")


main()
```

<!--
name: test_first_command
```python
assert len(sandbox_api.sync.calls_for("spawn_instance")) == 1
assert sandbox_api.sync.calls_for("operation_subprocess_create")[0].args[1] == "echo"
assert capsys.readouterr().out == "Hello from ConTree!\n"
```
-->

::::

::::{tab} Async

<!-- name: test_first_command_async; fixtures: sandbox_api, capsys -->

```python
import asyncio

from contree_sdk import create_sandbox_session


async def main() -> None:
    async with create_sandbox_session(image="tag:alpine:latest") as session:
        result = await session.run("echo", args=["Hello from ConTree!"])
        print(result.stdout.as_text(), end="")


asyncio.run(main())
```

<!--
name: test_first_command_async
```python
assert len(sandbox_api.async_client.calls_for("spawn_instance")) == 1
assert sandbox_api.async_client.calls_for("operation_subprocess_create")[0].args[1] == "echo"
assert capsys.readouterr().out == "Hello from ConTree!\n"
```
-->

::::

The image tag must already exist on your endpoint and provide `sleep` and `echo`.
Replace `tag:alpine:latest` with an available tag or image UUID; the factory does
not import it. See {doc}`images` if you need to prepare a base image.

## Install the SDK

These guides describe the breaking **0.5 development API** and require Python
3.10–3.14. Run the installation command from this repository checkout; the
published 0.4 package does not provide the new API.

```bash
pip install -e ".[async]"
```

For synchronous programs only, `pip install -e .` is sufficient.

## Keep and reuse work

The default session is `AsyncLazySession` or `LazySession`. The first command
starts a VM; later commands reuse it until a snapshot. Normal context exit saves
pending filesystem changes. An exception or cancellation discards changes since
the last completed snapshot.

The default policy snapshots after 10 idle seconds. Snapshots are lightweight;
you can take one after every command. Each snapshot stops the VM: files survive,
but processes and memory do not. An unchanged filesystem can return the same
`image_uuid`, which is normal.

For automatic saving after each command, select `session_type=ContreeSession`
or `ContreeAsyncSession`; see [Save after every command](session-model.md#save-after-every-command).
These classes start a separate VM for each command and save by default.
Use `disposable=True` to leave the session image unchanged.

Local history uses a memory store by default. Supply `storage` and `session_id`
to resume a session later.

Save a checkpoint before an experiment, give it a branch, and return to the
baseline without running setup again. {doc}`Work with a Session <session-model>`
explains the model and leads through snapshots, branching, rollback, and resume.

## Configuration

Configure the endpoint, token, and **AI project**. The
{ref}`connection sources <sandbox-connection>` section below lists environment
variables, Profile fields, INI format, and source precedence.

You can also pass credentials directly. These arguments create a regular
`contree-client` Profile inside the factory:

::::{tab} Sync

<!-- name: test_first_command_direct; fixtures: sandbox_api -->

```python
"""Run a command in a sandbox and print its output."""

from contree_sdk import create_sandbox_session


def main() -> None:
    with create_sandbox_session(
        image="tag:alpine:latest",
        url="https://contree.example.com",
        token="your-token",
        project="your-ai-project",
    ) as session:
        result = session.run("echo", args=["Hello from ConTree!"])
        print(result.stdout.as_text(), end="")


main()
```

::::

::::{tab} Async

<!-- name: test_first_command_direct_async; fixtures: sandbox_api -->

```python
import asyncio

from contree_sdk import create_sandbox_session


async def main() -> None:
    async with create_sandbox_session(
        image="tag:alpine:latest",
        url="https://contree.example.com",
        token="your-token",
        project="your-ai-project",
    ) as session:
        result = await session.run("echo", args=["Hello from ConTree!"])
        print(result.stdout.as_text(), end="")


asyncio.run(main())
```

::::

To select the context protocol explicitly, use `create_sync_sandbox_session()`
with `with`, or `create_async_sandbox_session()` with `async with`. Both helpers
are exported from `contree_sdk` and accept the same connection arguments.

To reuse an existing Profile object or name, pass `profile=profile` instead of
the credential arguments. Select an INI file with `config_path="config.ini"`;
omitting it uses the client's standard paths. The factory rejects a profile
combined with direct credentials.

(sandbox-connection)=

### Connection sources

Configure the endpoint URL, token, and AI project for your deployment. The
project identifies where the sandbox runs; omitting it is not a complete working
configuration.

| Setting    | Environment                              | Profile / INI | Direct factory argument |
| ---------- | ---------------------------------------- | ------------- | ----------------------- |
| Endpoint   | `CONTREE_URL`                            | `url`         | `url`                   |
| Token      | `CONTREE_TOKEN` or `NEBIUS_API_KEY`      | `token`       | `token`                 |
| AI project | `CONTREE_PROJECT` or `NEBIUS_AI_PROJECT` | `project`     | `project`               |

The SDK delegates environment parsing to contree-client.

Use exactly one explicit source:

| Source             | Arguments                                | Behavior                                                                                                |
| ------------------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Direct credentials | `url`, `project`, `token`                | Build a regular client `Profile`. Token is required. An omitted URL uses the client's default endpoint. |
| Profile object     | `profile=profile`                        | Use that exact profile. Do not combine it with direct credentials or `config_path`.                     |
| Named profile      | `profile="work"`, optional `config_path` | Resolve that name through contree-client.                                                               |
| Explicit INI       | `config_path="config.ini"`               | Resolve the file's active profile, or the name selected by `CONTREE_PROFILE`.                           |
| Automatic          | Omit all source arguments                | Use `contree_client.profiles.from_env()`, then the client's default profile resolution.                 |

Direct credentials cannot be combined with `profile` or `config_path`.
Incomplete explicit credentials raise an error rather than falling back to ENV.
An explicit source takes priority over ENV. Without one, the environment needs
both `CONTREE_URL` and `CONTREE_TOKEN` (or `NEBIUS_API_KEY`). Provide the project
through `CONTREE_PROJECT` (or `NEBIUS_AI_PROJECT`).

For INI resolution, contree-client uses an explicit profile name, then
`CONTREE_PROFILE`, then the active profile in the file. Its default files are
`cli.ini` and `auth.ini` under `CONTREE_HOME`; `auth.ini` takes priority. Without
`CONTREE_HOME`, the client uses its XDG configuration directory. A supplied
`config_path` replaces the auth file path and can be named `config.ini`; the
client also reads `cli.ini` from the same directory.

For example, a configuration file contains:

```ini
[DEFAULT]
profile = work

[profile:work]
type = iam
url = https://your-contree-endpoint
token = your-token
project = your-ai-project
```

The SDK uses the credentials from the selected profile. It does not acquire or
refresh credentials itself.

::::{tab} Sync

<!-- name: test_factory_direct_profile; fixtures: sandbox_api -->

```python
from contree_sdk import create_sync_sandbox_session, profile_from_args


profile = profile_from_args(
    url="https://contree.example.com",
    token="your-token",
    project="your-ai-project",
)
with create_sync_sandbox_session(image="tag:alpine:latest", profile=profile) as session:
    session.run("echo", args=["Hello!"])
```

::::

::::{tab} Async

<!-- name: async test_factory_direct_profile_async; fixtures: sandbox_api -->

```python
from contree_sdk import create_async_sandbox_session, profile_from_args


profile = profile_from_args(
    url="https://contree.example.com",
    token="your-token",
    project="your-ai-project",
)
async with create_async_sandbox_session(image="tag:alpine:latest", profile=profile) as session:
    await session.run("echo", args=["Hello!"])
```

::::

`profile_from_args` only constructs a `Profile`; it does not write an INI file.
You can instead pass the same arguments directly to any factory.

Continue with {doc}`images` to import a Docker image for your sandbox.
