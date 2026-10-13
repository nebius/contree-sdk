---
icon: hand-wave
---

# Run your first command

Create a sandbox, execute a command, and print its output. The SDK loads your
connection from environment variables or a saved profile by default.

## Create a sandbox

Save either program as `first_command.py` and run it with Python. Both programs
print `Hello from ConTree!` and save pending work when the context exits.

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

::::{tab} Sync

<!-- name: test_first_command; fixtures: sandbox_api, capsys -->

```python
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

The image tag must already exist on your endpoint and provide `sleep` and `echo`.
Replace `tag:alpine:latest` with an available tag or image UUID; the factory does
not import it. See {doc}`images` if you need to prepare a base image.

## Configuration

Configure the endpoint, token, and **AI project** using the
{ref}`connection guide <sandbox-connection>`. It lists the supported environment
variables, Profile fields, INI format, and source precedence. A token and URL
without the project are not a complete working configuration.

You can also pass credentials directly. These arguments create a regular
`contree-client` Profile inside the factory:

<!-- name: test_first_command_direct; fixtures: sandbox_api -->

```python
from contree_sdk import create_sync_sandbox_session


with create_sync_sandbox_session(
    image="tag:alpine:latest",
    url="https://contree.example.com",
    token="your-token",
    project="your-ai-project",
    auth_type="iam",
) as session:
    session.run("echo", args=["Hello from ConTree!"])
```

Use `auth_type="jwt"` for JWT credentials. To reuse an existing Profile object or
name, pass `profile=profile` instead of the four credential arguments. An explicit
INI file is selected with `config_path="config.ini"`; omitting it uses the client's
standard paths. The factory rejects a profile combined with direct credentials.

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

The default policy snapshots after 60 idle seconds. Files survive a snapshot;
processes and memory do not. Local history uses a memory store by default. Supply
`storage` and `session_id` to resume a session later.

Continue with {doc}`sandbox-factory` for all factory parameters, explicit session
classes, cache/storage options, and ownership rules. See {doc}`lazy-session` for
snapshot policies and live file limitations, or {doc}`sessions` and
{doc}`branching` for persistent history and branches.

For advanced use, {doc}`manual-sandbox` shows how to construct and own each
component yourself. Start there before implementing a custom factory.
