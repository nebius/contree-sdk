---
icon: hand-wave
---

# Getting Started

This guide will help you get up and running with ConTree SDK. By the end of this guide, you'll understand how to create clients, work with images, and run your first commands.

## Configuration

`contree_sdk` performs no auth, transport, or configuration of its own — `Contree`/`ContreeSync` just take an already-constructed `contree_client.base.ContreeAsyncClient`/`ContreeSyncClient` (e.g. from `contree_client.httpx`) as their first argument. Credentials, base URL, timeouts, and retries are entirely `contree_client`'s concern, configured directly when you build that client:

```python
from contree_client.httpx import ContreeAsyncClient

api_client = ContreeAsyncClient("YOUR-NEBIUS-API-KEY", base_url="https://your-instance.of.contree")
```

`contree_client` clients can also be built from a saved profile with `from_profile()`, which resolves credentials in this order: an explicit `profile` argument, then the `CONTREE_PROFILE` environment variable, then the active profile recorded in the profile config file (`$CONTREE_HOME/auth.ini`, defaulting to `~/.config/contree/auth.ini`):

```python
from contree_client.httpx import ContreeAsyncClient

api_client = ContreeAsyncClient.from_profile()
```

## Creating a Client

The first step is to create a ConTree client. You can choose between async and sync versions depending on your application needs.

Here's how to create a client and verify the connection by listing available images:

````{tab} Async
```{literalinclude} ../../examples/client/client.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {class}`~contree_sdk.Contree` for all client options.
````

````{tab} Sync
```{literalinclude} ../../examples/client/client_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {class}`~contree_sdk.ContreeSync` for all client options.
````

## Working with Images

Images are the foundation of ConTree. The simplest way to reference an image is by tag using `images.use()`, which creates an image object without making an API call:

````{tab} Async
```python
image = await contree.images.use("ubuntu:latest")
result = await image.run(shell="echo hello")
```
````

````{tab} Sync
```python
image = contree.images.use("ubuntu:latest")
result = image.run(shell="echo hello").wait()
```
````

To resolve a tag or UUID upfront via an API call, use `images.use(strict=True)`. To import from an external registry (or return an existing image if already imported), use `images.oci()`.

See {doc}`images` for a full overview of available methods, examples, and what you can pass as a reference.

## Running Commands

Once you have an image, you can run commands inside it. Each command execution creates a new version of the image with your changes.

### Basic Command Execution

You can run various shell commands and handle their output:

````{tab} Async
```{literalinclude} ../../examples/run/run_simple.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.objects.image.ContreeImage.run` for all command execution options.
````

````{tab} Sync
```{literalinclude} ../../examples/run/run_simple_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.objects.image.ContreeImageSync.run` for all command execution options.
````

### Understanding the Results

When you run a command, you get back a result object that contains:

- **`stdout`**: Standard output from the command
- **`stderr`**: Standard error from the command
- **`exit_code`**: The exit code (0 for success, non-zero for errors)
- **`uuid`**: The UUID of the new image version created by this command
