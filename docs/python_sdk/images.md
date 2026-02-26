# Working with Images

ConTree SDK provides several ways to reference and import container images. The simplest way is `images.use()`, which creates an image reference by tag without making an API call — the tag is resolved by the server at execution time. For importing images from external registries, use `images.pull()`.

For detailed API documentation, see {class}`~contree_sdk.sdk.managers.images.ImagesManager` and {class}`~contree_sdk.sdk.managers.images.ImagesManagerSync`.

## Using Images by Tag

The simplest way to get an image is `images.use(tag)`. This creates an image object immediately without any API call — the tag is resolved at execution time when you run a command:

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

## Pulling Images

For importing images from external registries or resolving a tag/UUID to an image upfront, use `images.pull()`.
You can pull images by UUID, tag, or import them from external registries:

````{tab} Async
```{literalinclude} ../../examples/images/pull_image.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.managers.images.ImagesManager.pull` for all parameters.
````

````{tab} Sync
```{literalinclude} ../../examples/images/pull_image_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.pull` for all parameters.
````

### Image Access Methods

- **By tag (lazy)**: `client.images.use("ubuntu:latest")` - Reference by tag, resolved at execution time (no API call)
- **By tag (eager)**: `client.images.pull("ubuntu:latest")` - Resolve tag to UUID immediately via API call
- **By UUID**: `client.images.pull(uuid)` - Pull existing image by UUID
- **From registry**: `client.images.pull("docker://ghcr.io/owner/image:tag")` - Import from external registry
- **From private registry**: `client.images.pull("docker://ghcr.io/owner/image:tag", username="user", password="token")` - Import from private registry with authentication

The `docker://` prefix allows you to import any publicly accessible Docker image directly into ConTree.

## Listing Images

View all available images in your ConTree instance:

````{tab} Async
```{literalinclude} ../../examples/images/list_images.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {class}`~contree_sdk.sdk.managers.images.ImagesManager` for filtering and iteration options.
````

````{tab} Sync
```{literalinclude} ../../examples/images/list_images_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {class}`~contree_sdk.sdk.managers.images.ImagesManagerSync` for filtering and iteration options.
````
