# ConTree SDK

[![PyPI version](https://img.shields.io/pypi/v/contree-sdk.svg)](https://pypi.org/project/contree-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/contree-sdk.svg)](https://pypi.org/project/contree-sdk/)

Use one sandbox session to run commands, read and write files, search contents,
and list directories. Save the filesystem as an image when you need to continue
later or try a different approach.

This checkout contains the breaking **0.5 development API**. Install it locally:

```bash
pip install -e .
# Include async transport and SQLite support when needed:
pip install -e ".[async]"
```

## Use a sandbox session

The five tools are `run`, `read_file`, `write_file`, `grep`, and `list_dir`.
Initialize the session [from a token](docs/python_sdk/getting-started.md#create-a-session-from-a-token)
or [from a saved profile](docs/python_sdk/getting-started.md#create-a-session-from-a-saved-profile).
Use an image available on your endpoint.

### Sync

<!-- name: test_readme; fixtures: sandbox_tools_api, capsys -->

```python
"""Use the five sandbox tools in one session."""

from contree_sdk import create_sandbox_session


def main() -> None:
    with create_sandbox_session(image="tag:alpine:latest") as sandbox_session:
        # Write a file in the sandbox.
        sandbox_session.write_file("/work/message.txt", b"Hello from ConTree!\n")

        # Run a command and print its output.
        result = sandbox_session.run("cat", args=["/work/message.txt"])
        print(result.stdout)

        # Read the file as bytes.
        content = sandbox_session.read_file("/work/message.txt")
        print(content.decode())

        # Search file contents.
        matches = sandbox_session.grep("Hello", path="/work/message.txt")
        print(matches)

        # List the directory with file metadata.
        directory = sandbox_session.list_dir("/work")
        print(directory)


main()
```

<!--
name: test_readme
```python
assert (
    capsys.readouterr().out
    == "Hello from ConTree!\n\nHello from ConTree!\n\n/work/message.txt:1:Hello from ConTree!\n\n-rw-r--r-- 1 root root 20 1970-01-01 00:00 message.txt\n\n"
)
client = sandbox_tools_api.sync
assert len(client.calls_for("spawn_instance")) == 1
assert len(client.calls_for("operation_subprocess_create")) == 2
assert client.calls_for("inspect_instance_download")[0].args == ("op-1", "/work/message.txt")
assert client.calls_for("inspect_instance_grep")[0].kwargs["path"] == "/work/message.txt"
assert client.calls_for("inspect_instance_list")[0].args == ("op-1", "/work")
assert len(client.calls_for("operation_subprocess_kill")) == 1
```
-->

### Async

<!-- name: test_readme_async; fixtures: sandbox_tools_api, capsys -->

```python
import asyncio

from contree_sdk import create_sandbox_session


async def main() -> None:
    async with create_sandbox_session(image="tag:alpine:latest") as sandbox_session:
        # Write a file in the sandbox.
        await sandbox_session.write_file("/work/message.txt", b"Hello from ConTree!\n")

        # Run a command and print its output.
        result = await sandbox_session.run("cat", args=["/work/message.txt"])
        print(result.stdout)

        # Read the file as bytes.
        content = await sandbox_session.read_file("/work/message.txt")
        print(content.decode())

        # Search file contents.
        matches = await sandbox_session.grep("Hello", path="/work/message.txt")
        print(matches)

        # List the directory with file metadata.
        directory = await sandbox_session.list_dir("/work")
        print(directory)


asyncio.run(main())
```

<!--
name: test_readme_async
```python
assert (
    capsys.readouterr().out
    == "Hello from ConTree!\n\nHello from ConTree!\n\n/work/message.txt:1:Hello from ConTree!\n\n-rw-r--r-- 1 root root 20 1970-01-01 00:00 message.txt\n\n"
)
client = sandbox_tools_api.async_client
assert len(client.calls_for("spawn_instance")) == 1
assert len(client.calls_for("operation_subprocess_create")) == 2
assert client.calls_for("inspect_instance_download")[0].args == ("op-1", "/work/message.txt")
assert client.calls_for("inspect_instance_grep")[0].kwargs["path"] == "/work/message.txt"
assert client.calls_for("inspect_instance_list")[0].args == ("op-1", "/work")
assert len(client.calls_for("operation_subprocess_kill")) == 1
```
-->

The command and file read both print `Hello from ConTree!`. The search prints
`/work/message.txt:1:Hello from ConTree!`, and the listing shows metadata for `message.txt`.

The default `LazySession` (`AsyncLazySession` for async code) starts a VM on the
first command and reuses it for later commands. After 10 idle seconds, it saves
the filesystem and stops the VM automatically. The next command starts a new VM
from those saved files. Processes and memory do not survive a snapshot.
Normal context exit also saves pending changes.

To save after each command, select `session_type=ContreeSession` for Sync or
`session_type=ContreeAsyncSession` for Async. Each command then uses a separate
VM. See the complete [save-after-every-command examples](docs/python_sdk/getting-started.md#save-after-every-command).

## Follow a workflow

| Task                                             | Guide                                                      |
| ------------------------------------------------ | ---------------------------------------------------------- |
| Configure credentials and use sync or async code | [Your first sandbox](docs/python_sdk/getting-started.md)   |
| Import a Docker image                            | [Import a Docker image](docs/python_sdk/images.md)         |
| Build from a Dockerfile                          | [Build a Docker image](docs/python_sdk/building-images.md) |
| Select components and control their behavior     | [Advanced usage](docs/python_sdk/advanced.md)              |
| Upload inputs and download results               | [Files](docs/python_sdk/files.md)                          |
| Continue after restarting Python                 | [Save and resume](docs/python_sdk/sessions.md)             |
| Try alternatives from a checkpoint               | [Branches](docs/python_sdk/branching.md)                   |
| Control a running sandbox                        | [Operations](docs/python_sdk/operation.md)                 |
| Connect deepagents                               | [Agent integration](docs/integrations/langchain.md)        |
| Override policy or replace components            | [Customization](docs/python_sdk/customization.md)          |
| Upgrade from the old SDK                         | [Migration](docs/python_sdk/migration.md)                  |

The [documentation](https://nebius.github.io/contree-sdk/) includes API references and
failure-handling examples. The mini-swe-agent 2.4.6 bundled adapter needs a port
before it can use this API; see the [compatibility note](docs/integrations/mini-swe-agent.md).

## Develop and test

```bash
uv sync --extra dev --extra docs
uv run pytest
```

The regular test run executes the Python scenarios in README and `docs/` through
[markdown-pytest](https://mosquito.github.io/markdown-pytest/). The SDK and stores run
normally; fixtures supply transport responses. No server credentials are required.
See [contributing](docs/contributing.md) for checks and how to add a scenario.

Licensed under [Apache 2.0](LICENSE). Report vulnerabilities through the process
in [SECURITY.md](SECURITY.md).

Standalone programs with embedded tests are in [`examples/sync/`](examples/sync/)
and [`examples/async/`](examples/async/). See the [examples guide](examples/README.md)
for prerequisites and execution commands.
