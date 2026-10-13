# ConTree SDK

[![PyPI version](https://img.shields.io/pypi/v/contree-sdk.svg)](https://pypi.org/project/contree-sdk/)
[![Python](https://img.shields.io/pypi/pyversions/contree-sdk.svg)](https://pypi.org/project/contree-sdk/)

Run commands in remote sandboxes, save their filesystem changes, and branch from
recorded checkpoints. The SDK provides sessions, history stores, operation handles,
Dockerfile builds, and deepagents adapters. `contree-client` provides the transport.

This checkout contains the breaking **0.5 development API**. Install it locally:

```bash
pip install -e .
# Include async transport and SQLite support when needed:
pip install -e ".[async]"
```

## Run a command

Configure the endpoint, token, and AI project using the
[connection guide](docs/python_sdk/getting-started.md#connection-sources).
Replace `tag:alpine:latest` with an image available on your endpoint.

### Sync

<!-- name: test_readme; fixtures: sandbox_api, capsys -->

```python
"""Run a command in a sandbox and print its output."""

from contree_sdk import create_sandbox_session


def main() -> None:
    with create_sandbox_session(image="tag:alpine:latest") as sandbox:
        result = sandbox.run("echo", args=["Hello from ConTree!"])
        print(result.stdout.as_text(), end="")


main()
```

<!--
name: test_readme
```python
assert capsys.readouterr().out == "Hello from ConTree!\n"
assert len(sandbox_api.sync.calls_for("spawn_instance")) == 1
assert len(sandbox_api.sync.calls_for("operation_subprocess_kill")) == 1
```
-->

### Async

<!-- name: test_readme_async; fixtures: sandbox_api, capsys -->

```python
import asyncio

from contree_sdk import create_sandbox_session


async def main() -> None:
    async with create_sandbox_session(image="tag:alpine:latest") as sandbox:
        result = await sandbox.run("echo", args=["Hello from ConTree!"])
        print(result.stdout.as_text(), end="")


asyncio.run(main())
```

<!--
name: test_readme_async
```python
assert capsys.readouterr().out == "Hello from ConTree!\n"
assert len(sandbox_api.async_client.calls_for("spawn_instance")) == 1
assert len(sandbox_api.async_client.calls_for("operation_subprocess_kill")) == 1
```
-->

Commands share a VM until a snapshot. Normal context exit saves pending filesystem
changes. Snapshots preserve files; running processes and memory do not survive.
See [manual assembly](docs/python_sdk/manual-sandbox.md) when you need direct
control over the components the factory supplies.

## Follow a workflow

| Task                                             | Guide                                                   |
| ------------------------------------------------ | ------------------------------------------------------- |
| Configure credentials and use sync or async code | [Your first sandbox](docs/python_sdk/getting-started.md)     |
| Import a Docker image                           | [Import a Docker image](docs/python_sdk/images.md)    |
| Build from a Dockerfile                          | [Build a Docker image](docs/python_sdk/building-images.md) |
| Select components and control their behavior     | [Advanced usage](docs/python_sdk/advanced.md)          |
| Upload inputs and download results               | [Files](docs/python_sdk/files.md)                       |
| Continue after restarting Python                 | [Save and resume](docs/python_sdk/sessions.md)          |
| Try alternatives from a checkpoint               | [Branches](docs/python_sdk/branching.md)                |
| Control a running sandbox                        | [Operations](docs/python_sdk/operation.md)              |
| Connect deepagents                               | [Agent integration](docs/integrations/langchain.md)     |
| Override policy or replace components            | [Customization](docs/python_sdk/customization.md)       |
| Upgrade from the old SDK                         | [Migration](docs/python_sdk/migration.md)               |

The [documentation](https://docs.contree.dev/sdk/) includes API references and
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
