# Getting Started

This guide will help you get up and running with ConTree SDK. By the end of this guide, you'll understand how to create clients, work with images, and run your first commands.

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
image = contree.images.use("ubuntu:latest")
result = await image.run(shell="echo hello")

# Sync
image = contree.images.use("ubuntu:latest")
result = image.run(shell="echo hello").wait()
```

### Pulling Images

For importing images from external registries or resolving a tag/UUID upfront, use `images.pull()`.
You can pull images in several ways - by UUID, by tag, and from external registries:

````{tab} Async
```{literalinclude} ../../examples/images/pull_image.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.managers.images.ImagesManager.pull` for all image pulling options.
````

````{tab} Sync
```{literalinclude} ../../examples/images/pull_image_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.pull` for all image pulling options.
````

### Image Sources

You can access images in several ways:

- **By tag (lazy)**: `images.use("ubuntu:latest")` - Reference by tag, resolved at execution time (no API call)
- **By tag (eager)**: `images.pull("ubuntu:latest")` - Resolve tag via API call
- **By UUID**: `images.pull("550e8400-e29b-41d4-a716-446655440000")` - Pull a specific image version
- **Docker Hub**: `images.pull("docker://docker.io/busybox:latest")` - Import from Docker Hub
- **Other registries**: `images.pull("docker://ghcr.io/user/image:tag")` - Import from other Docker registries

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
