# Working with Images

Contree SDK allows you to pull and manage container images. You can use images from public registries, your own private registries, or import Docker Hub images.

For detailed API documentation, see {class}`~contree_sdk.sdk.managers.images.ImagesManager` and {class}`~contree_sdk.sdk.managers.images.ImagesManagerSync`.

## Pulling Images

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

### Import Methods

- **By UUID**: `client.images.pull(uuid)` - Pull existing image by UUID
- **By tag**: `client.images.pull("ubuntu:latest")` - Pull by tag name
- **From registry**: `client.images.pull("docker://ghcr.io/owner/image:tag")` - Import from external registry
- **From private registry**: `client.images.pull("docker://ghcr.io/owner/image:tag", username="user", password="token")` - Import from private registry with authentication

The `docker://` prefix allows you to import any publicly accessible Docker image directly into Contree.

## Listing Images

View all available images in your Contree instance:

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
