# Getting Started

This guide will help you get up and running with ConTree SDK. By the end of this guide, you'll understand how to create clients, work with images, and run your first commands.

## Configuration

ConTree SDK uses environment variables for configuration:

- **CONTREE_TOKEN**: Your authentication token
- **CONTREE_BASE_URL**: Your ConTree instance URL

```bash
export CONTREE_TOKEN="your_token_here"
export CONTREE_BASE_URL="https://your-instance.of.contree"
```

Alternatively, you can pass `token` and `base_url` directly when creating a client.

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

```python
# Async
image = await contree.images.use("ubuntu:latest")
result = await image.run(shell="echo hello")

# Sync
image = contree.images.use("ubuntu:latest")
result = image.run(shell="echo hello").wait()
```

### Pulling Images

For resolving a tag/UUID upfront, use `images.use(strict=True)`. For importing images from external registries, use `images.oci()`:

````{tab} Async
```{literalinclude} ../../examples/images/pull_image.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.managers.images.ImagesManager.use` and {meth}`~contree_sdk.sdk.managers.images.ImagesManager.oci` for all image pulling options.
````

````{tab} Sync
```{literalinclude} ../../examples/images/pull_image_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.use` and {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.oci` for all image pulling options.
````

### Methods

- {meth}`~contree_sdk.sdk.managers.images.ImagesManager.use`(ref) — no API call; tag or UUID is resolved at execution time
- {meth}`~contree_sdk.sdk.managers.images.ImagesManager.use`(ref, strict=True) — verifies the image exists via an API call
- {meth}`~contree_sdk.sdk.managers.images.ImagesManager.oci`(ref) (aliases: {meth}`~contree_sdk.sdk.managers.images.ImagesManager.docker`, {meth}`~contree_sdk.sdk.managers.images.ImagesManager.podman`, {meth}`~contree_sdk.sdk.managers.images.ImagesManager.pull_by_oci`) — like `use(strict=True)`, but imports from the registry if not found locally
- {meth}`~contree_sdk.sdk.managers.images.ImagesManager.import_from`(ref) — always imports from an external registry

:::{danger}
`import_from` always triggers a new import operation and should only be used when you explicitly need to re-import. In most cases, prefer `images.oci()`, which returns an existing image if already imported. If no import is needed at all, use `images.use()`.
:::

### What `ref` can be

- UUID — e.g. `"550e8400-e29b-41d4-a716-446655440000"` or `UUID(...)`
- OCI tag — e.g. `"ubuntu:latest"`
- OCI full URL — e.g. `"docker://ghcr.io/user/image:tag"`
- {class}`~contree_sdk.utils.oci.OCIReference` object

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
