---
icon: hand-wave
---

# Getting Started

This guide will help you get up and running with ConTree SDK. By the end of this guide, you'll understand how to create a client, start a session, and run your first commands.

## Configuration

The low-level HTTP client — `ContreeClient` (sync) / `ContreeAsyncClient` (async) — lives in the separate [`contree-client`](https://pypi.org/project/contree-client/) package. There are three ways to construct one:

1. **Explicit token**: `ContreeClient(token="...", base_url="...")`.
2. **Saved profile** (recommended if the `contree` CLI is installed): `ContreeClient.from_profile()`. Resolution order:
   - an explicit `profile` argument,
   - the `CONTREE_PROFILE` environment variable,
   - the active profile recorded in the config file.

   Profiles are read from `$CONTREE_HOME/auth.ini` (merged over `$CONTREE_HOME/cli.ini`), where `CONTREE_HOME` defaults to `$XDG_CONFIG_HOME/contree` or `~/.config/contree`. Credentials written by `contree auth` are picked up automatically.
3. **Plain environment variables**, bypassing config files entirely: `contree_client.profiles.from_env()` reads `CONTREE_TOKEN` (or `NEBIUS_API_KEY`), `CONTREE_URL`, and optionally `CONTREE_PROJECT` (or `NEBIUS_AI_PROJECT`).

```bash
export CONTREE_TOKEN="your_token_here"
export CONTREE_URL="https://your-instance.of.contree"
```

## Creating a Client

You can choose between async and sync versions depending on your application needs. Here's how to create a client and verify the connection by listing available images:

````{tab} Async
```{literalinclude} ../../examples/client/client.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/client/client_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

## Starting a Session

A **`ContreeSession`** is a durable pointer into an image's history — the entry point for everything you do with ConTree. Give it an image reference and it resolves the image lazily, on the first `.run()` call:

````{tab} Async
```python
from contree_sdk.session import ContreeAsyncSession

session = ContreeAsyncSession(client, image="tag:python:3.11-slim")
result = await session.run(shell="echo hello")
```
````

````{tab} Sync
```python
from contree_sdk.session import ContreeSession

session = ContreeSession(client, image="tag:python:3.11-slim")
result = session.run(shell="echo hello")
```
````

`image` accepts anything `client.resolve_image()` does — a tag (`"tag:python:3.11-slim"`) or a UUID. To pull an image from a registry first, see {doc}`images`.

## Running Commands

Once you have a session, you can run commands inside it. By default, `.run()` is **disposable**: it executes against the session's current image without changing it. Pass `disposable=False` to commit the result and advance the session.

````{tab} Async
```{literalinclude} ../../examples/run/run_simple.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.session.ContreeAsyncSession.run` for all command execution options.
````

````{tab} Sync
```{literalinclude} ../../examples/run/run_simple_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.session.ContreeSession.run` for all command execution options.
````

### Understanding the Results

`.run()` returns `contree-client`'s `InstanceResult` as-is:

- **`stdout`/`stderr`**: `StreamRepr` objects — decode with `.as_text()` or `.as_bytes()`.
- **`state.exit_code`**: the process exit code (0 for success, non-zero for errors).

`FailedOperationError` is raised instead if the operation itself failed with no result at all (a nonzero exit code inside a successful operation is not an error). See {doc}`running-commands` for the full picture, including file uploads and session history.
