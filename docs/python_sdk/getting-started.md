# Getting Started

This guide will help you get up and running with Contree SDK. By the end of this guide, you'll understand how to create clients, work with images, and run your first commands.

## Creating a Client

The first step is to create a Contree client. You can choose between async and sync versions depending on your application needs.

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

Images are the foundation of Contree. You can pull existing images from registries or work with images that are already available in your Contree environment.

### Pulling Images

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

You can pull images from several sources:

- **By tag**: `"ubuntu:latest"` - Pull from your Contree registry
- **By UUID**: `"550e8400-e29b-41d4-a716-446655440000"` - Pull a specific image version
- **Docker Hub**: `"docker://docker.io/busybox:latest"` - Import from Docker Hub
- **Other registries**: `"docker://ghcr.io/user/image:tag"` - Import from other Docker registries

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
