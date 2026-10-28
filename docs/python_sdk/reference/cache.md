# Caches and upload sources

Builders keep layer history, upload results, and URL-download metadata in one
Store. Helpers and direct builders accept `store=`. Tree kinds
separate reusable records from user sessions. Node data contains JSON values.
See {doc}`../building-images`, {doc}`store`, and {doc}`../caching` for retention,
connection scope, and upload provenance.

```{eval-rst}
.. automodule:: contree_sdk.upload_cache
   :members: CachedFileTransfer, AsyncCachedFileTransfer
   :inherited-members:
```

```{eval-rst}
.. automodule:: contree_sdk.file_sources
   :members: FileSource, SyncFileSources, AsyncFileSources
```

```{eval-rst}
.. automodule:: contree_sdk.scope
   :members: StoreScope
```
