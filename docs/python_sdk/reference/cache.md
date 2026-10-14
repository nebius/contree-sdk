# Caches and upload sources

Builders use caches for file-upload and URL-download metadata. Layer history lives
in the build store. See {doc}`../building-images`. All native cache values must be JSON-serializable. See {doc}`../caching` for expiry,
scoping, upload reuse, and persistent source records.

```{eval-rst}
.. automodule:: contree_sdk.cache
   :members: SyncCache, AsyncCache, SyncMemoryCache, AsyncMemoryCache, SyncSQLiteCache, AsyncSQLiteCache, CacheEntry, CacheScope, ScopedSyncCache, ScopedAsyncCache
   :inherited-members:
   :undoc-members:
   :member-order: bysource
```

```{eval-rst}
.. automodule:: contree_sdk.upload_cache
   :members: CachedFileTransfer, AsyncCachedFileTransfer
   :inherited-members:
```

```{eval-rst}
.. automodule:: contree_sdk.file_sources
   :members: FileSource, SyncFileSources, AsyncFileSources
```
