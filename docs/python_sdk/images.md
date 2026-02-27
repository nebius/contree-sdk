# Working with Images

ConTree SDK provides several ways to reference and import container images.

**Methods:**

- `images.use(ref)` — creates an image reference without any API call; the tag or UUID is resolved by the server at execution time
- `images.use(ref, strict=True)` — verifies the image exists via an API call before returning it
- `images.oci(ref)` (aliases: `docker`, `podman`, `pull_by_oci`) — like `use(strict=True)`, but falls back to importing from the external registry if not found
- `images.import_from(ref)` — explicitly imports an image from an external registry, always triggering an import operation

**What you can pass as `ref`:**

- UUID — reference an existing image by its UUID
- OCI tag (e.g. `"ubuntu:latest"`) — reference by tag
- OCI full URL (e.g. `"docker://ghcr.io/owner/image:tag"`) — full reference including registry
- {class}`~contree_sdk.utils.oci.OCIReference` object — programmatic OCI reference

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

- UUID — e.g. `"550e8400-e29b-41d4-a716-446655440000"` or `UUID(...)`
- OCI tag — e.g. `"ubuntu:latest"`
- OCI full URL — e.g. `"docker://ghcr.io/owner/image:tag"`
- {class}`~contree_sdk.utils.oci.OCIReference` object

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
