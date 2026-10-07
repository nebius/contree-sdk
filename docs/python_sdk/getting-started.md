---
icon: hand-wave
---

# Run your first command

This guide runs `echo` in a remote sandbox and prints its output locally.
You need Python 3.10–3.14, a ConTree endpoint and token, and an image available
on that endpoint. The image must contain `echo`; later examples also need a POSIX shell.

## Install the SDK

These guides describe the breaking 0.5 development API. Run the installation
commands from the root of this repository checkout. A published 0.4 package
does not provide this API.

For synchronous programs:

```bash
pip install -e .
```

For asynchronous programs, including async SQLite storage:

```bash
pip install -e ".[async]"
```

## Configure the connection and image

Set the values supplied for your ConTree deployment:

```bash
export CONTREE_URL="https://your-contree-endpoint"
export CONTREE_TOKEN="your-token"
export CONTREE_IMAGE="tag:your-existing-image"
```

`CONTREE_IMAGE` is an environment variable used by these examples. It can contain
an existing image UUID or tag. Setting it does not import an image. If you need a
base image, follow {doc}`images` first.

The programs below pass the token and URL explicitly to `contree-client`.
They do not require the ConTree CLI or a saved profile.

## Run the program

Choose one version and save it as `first_command.py`. Run `python first_command.py`.

::::{tab} Sync

<!--
name: test_first_command; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="Hello from ConTree!\n")
```
-->

```python
import os

from contree_client.models import StreamRepr
from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession


def main() -> None:
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])
        result = session.run("echo", args=["Hello from ConTree!"])
        if isinstance(result.stdout, StreamRepr):
            print(result.stdout.as_text(), end="")


main()
```

<!--
name: test_first_command
```python
assert doc_api.sync.calls_for("spawn_instance")[0].args == ("echo", "base-image")
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["args"] == ["Hello from ConTree!"]
assert doc_api.sync.calls_for("spawn_instance")[0].kwargs["disposable"] is True
assert capsys.readouterr().out == "Hello from ConTree!\n"
```
-->

::::

::::{tab} Async

<!--
name: test_first_command_async; fixtures: doc_api, capsys
```python
doc_api.complete(stdout="Hello from ConTree!\n")
```
-->

```python
import asyncio
import os

from contree_client.asyncio import ContreeAsyncClient
from contree_client.models import StreamRepr

from contree_sdk import ContreeAsyncSession


async def main() -> None:
    async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])
        result = await session.run("echo", args=["Hello from ConTree!"])
        if isinstance(result.stdout, StreamRepr):
            print(result.stdout.as_text(), end="")


asyncio.run(main())
```

<!--
name: test_first_command_async
```python
assert doc_api.async_client.calls_for("spawn_instance")[0].args == ("echo", "base-image")
assert doc_api.async_client.calls_for("spawn_instance")[0].kwargs["args"] == ["Hello from ConTree!"]
assert doc_api.async_client.calls_for("spawn_instance")[0].kwargs["disposable"] is True
assert capsys.readouterr().out == "Hello from ConTree!\n"
```
-->

::::

Expected output:

```text
Hello from ConTree!
```

The client context closes the connection. The session selects the starting image.
`run()` starts a command, waits for it, and returns an `InstanceResult`.
`StreamRepr.as_text()` decodes stdout for display.

The synchronous session resolves its image during construction. The async session
loads its state on first use; call `await session.ensure_ready()` if you need
`image_uuid` before running anything.

## Keep a command's filesystem changes

`run()` defaults to `disposable=True`. Use `disposable=False` when a command creates
files or installs packages that the next command needs. Continue with {doc}`files`
for a complete upload–run–download example, or {doc}`sessions` to resume work later.

## Use a saved profile instead

If you already configured the ConTree CLI, replace client construction with
`ContreeClient.from_profile()` or `ContreeAsyncClient.from_profile()`.
An explicit profile name takes precedence over `CONTREE_PROFILE`, then the active
profile in the configuration file. Setting `CONTREE_TOKEN` and `CONTREE_URL` alone
does not select a saved profile.

For environment-based profile loading, `contree_client.profiles.from_env()` returns
a `Profile` when both a token and URL are present. Pass that object to
`from_profile(profile)`. See {doc}`troubleshooting` if configuration fails.
