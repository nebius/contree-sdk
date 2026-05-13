# Getting Started

This guide will help you get up and running with ConTree SDK. By the end of this guide, you'll understand how to create clients, work with images, and run your first commands.

## Configuration

The SDK resolves credentials in the following priority order:

1. **Explicit values** passed to `IAMAuth` / `JWTAuth` constructors via `ContreeConfig`.
2. **Environment variables**:
   - `NEBIUS_API_KEY` — IAM token
   - `NEBIUS_PROJECT_ID` — ConTree project ID
   - `CONTREE_BASE_URL` — ConTree instance URL (for `JWTAuth`)
3. **`auth.ini`** — if the `contree` CLI is installed, credentials written by `contree auth login` are read automatically from `~/.config/contree/auth.ini`.

```bash
export NEBIUS_API_KEY="your_token_here"
export NEBIUS_PROJECT_ID="your_project_id"
export CONTREE_BASE_URL="https://your-instance.of.contree"
```

The active `auth.ini` profile defaults to `default` and can be overridden with `CONTREE_PROFILE`. The config directory respects `$CONTREE_HOME` and `$XDG_CONFIG_HOME`.

Alternatively, you can pass auth directly when creating a client via `ContreeConfig(auth=IAMAuth(...))` or use `JWTAuth` for legacy token-based access.

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
