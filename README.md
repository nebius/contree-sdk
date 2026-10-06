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

You need a ConTree endpoint and token, plus an image already available on that
endpoint. Set `CONTREE_URL`, `CONTREE_TOKEN`, and `CONTREE_IMAGE` to your values.
The image must contain `echo`.

<!--
name: test_readme; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="Hello from ConTree!\n")
```
-->

```python
import os
from contree_client.models import StreamRepr
from contree_client.sync import ContreeClient
from contree_sdk import ContreeSession

with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
    result = session.run("echo", args=["Hello from ConTree!"])
    if isinstance(result.stdout, StreamRepr):
        print(result.stdout.as_text(), end="")
```

<!--
name: test_readme
```python
assert capsys.readouterr().out == "Hello from ConTree!\n"
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["disposable"] is True
```
-->

The program prints `Hello from ConTree!`. Commands are disposable by default.
Pass `disposable=False` to retain filesystem changes for the next command.

## Follow a workflow

| Task                                             | Guide                                               |
| ------------------------------------------------ | --------------------------------------------------- |
| Configure credentials and use sync or async code | [First command](docs/python_sdk/getting-started.md) |
| Upload inputs and download results               | [Files](docs/python_sdk/files.md)                   |
| Continue after restarting Python                 | [Save and resume](docs/python_sdk/sessions.md)      |
| Try alternatives from a checkpoint               | [Branches](docs/python_sdk/branching.md)            |
| Control a running sandbox                        | [Operations](docs/python_sdk/operation.md)          |
| Build from a Dockerfile                          | [Image builds](docs/python_sdk/building-images.md)  |
| Connect deepagents                               | [Agent integration](docs/integrations/langchain.md) |
| Override policy or replace components            | [Customization](docs/python_sdk/customization.md)   |
| Upgrade from the old SDK                         | [Migration](docs/python_sdk/migration.md)           |

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
