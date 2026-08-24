:icon: bolt

Cache
=====

Used by :class:`~contree_sdk.docker.ContreeDockerBuilder`/
:class:`~contree_sdk.docker.ContreeAsyncDockerBuilder` to deduplicate local
file uploads and ``ADD <url>`` downloads across rebuilds.

.. automodule:: contree_sdk.cache
   :members: SyncCache, AsyncCache, SyncMemoryCache, AsyncMemoryCache, SyncSQLiteCache, AsyncSQLiteCache
   :inherited-members:
   :undoc-members:
   :member-order: bysource
