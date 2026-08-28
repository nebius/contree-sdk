---
icon: layer-group
---

# Working with Images

ConTree SDK provides several ways to reference and import container images. For full API documentation, see {class}`~contree_sdk.sdk.managers.images.ImagesManager` and {class}`~contree_sdk.sdk.managers.images.ImagesManagerSync`.

## Using Images by Tag

The simplest way to get an image is `images.use(tag)`. This creates an image object immediately without any API call — the tag is resolved at execution time when you run a command:

````{tab} Async
```{literalinclude} ../../examples/images/use_by_tag.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/images/use_by_tag_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

## Pulling Images

For resolving a tag/UUID to an image upfront, use `images.use(strict=True)`. For importing images from external registries, use `images.oci()`:

````{tab} Async
```{literalinclude} ../../examples/images/pull_image.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.managers.images.ImagesManager.use` and {meth}`~contree_sdk.sdk.managers.images.ImagesManager.oci` for all parameters.
````

````{tab} Sync
```{literalinclude} ../../examples/images/pull_image_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.use` and {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.oci` for all parameters.
````

### Methods

````{tab} Async
- {meth}`~contree_sdk.sdk.managers.images.ImagesManager.use`(ref) — no API call; tag or UUID is resolved at execution time
- {meth}`~contree_sdk.sdk.managers.images.ImagesManager.use`(ref, strict=True) — verifies the image exists via an API call
- {meth}`~contree_sdk.sdk.managers.images.ImagesManager.oci`(ref) (aliases: {meth}`~contree_sdk.sdk.managers.images.ImagesManager.docker`, {meth}`~contree_sdk.sdk.managers.images.ImagesManager.podman`, {meth}`~contree_sdk.sdk.managers.images.ImagesManager.pull_by_oci`) — like `use(strict=True)`, but imports from the registry if not found locally
- {meth}`~contree_sdk.sdk.managers.images.ImagesManager.import_from`(ref) — always imports from an external registry
````

````{tab} Sync
- {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.use`(ref) — no API call; tag or UUID is resolved at execution time
- {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.use`(ref, strict=True) — verifies the image exists via an API call
- {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.oci`(ref) (aliases: {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.docker`, {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.podman`, {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.pull_by_oci`) — like `use(strict=True)`, but imports from the registry if not found locally
- {meth}`~contree_sdk.sdk.managers.images.ImagesManagerSync.import_from`(ref) — always imports from an external registry
````

:::{danger}
`import_from` always triggers a new import operation and should only be used when you explicitly need to re-import. In most cases, prefer `images.oci()`, which returns an existing image if already imported. If no import is needed at all, use `images.use()`.
:::

### What `ref` can be

- UUID — reference an existing image by its UUID, e.g. `"550e8400-e29b-41d4-a716-446655440000"` or `UUID(...)`
- OCI tag — reference by image tag, e.g. `"ubuntu:latest"`
- OCI full URL — full reference including registry host, e.g. `"docker://ghcr.io/owner/image:tag"`
- {class}`~contree_sdk.utils.oci.OCIReference` — programmatic OCI reference object

## Tagging Images

You can assign or remove a tag on any image using `tag_as()` and `untag()`. Tags are unique across all images — assigning an existing tag to a new image moves it automatically.

````{tab} Async
```{literalinclude} ../../examples/images/tag_image.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.objects.image.ContreeImage.tag_as` and {meth}`~contree_sdk.sdk.objects.image.ContreeImage.untag` for details.
````

````{tab} Sync
```{literalinclude} ../../examples/images/tag_image_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```

See {meth}`~contree_sdk.sdk.objects.image.ContreeImageSync.tag_as` and {meth}`~contree_sdk.sdk.objects.image.ContreeImageSync.untag` for details.
````

You can also tag the result of a `run()` directly by passing `tag=` to the call — the resulting image will be tagged after execution completes:

````{tab} Async
```{literalinclude} ../../examples/images/tag_on_run.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

````{tab} Sync
```{literalinclude} ../../examples/images/tag_on_run_sync.py
:language: python
:linenos:
:pyobject: main
:dedent: 4
:start-after: def main(
```
````

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
