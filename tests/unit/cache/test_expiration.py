"""Native caches agree on TTL, detached records, and literal invalidation."""

import inspect

import pytest
from contree_client.testing import ContreeClient

from contree_sdk.cache import (
    AsyncMemoryCache,
    AsyncSQLiteCache,
    CacheScope,
    ScopedAsyncCache,
    ScopedSyncCache,
    SyncSQLiteCache,
)


async def call(cache, method, *args, **kwargs):
    result = getattr(cache, method)(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


async def test_expiration_boundary_no_renewal_and_permanent_records(cache_case):
    cache, now = cache_case
    await call(cache, "set", "temporary", {"uuid": "one"}, ttl=10)
    await call(cache, "set", "permanent", None)
    await call(cache, "set", "immediate", "invisible", ttl=0)
    assert (await call(cache, "get_entry", "temporary")).expires_at == 1010
    assert await call(cache, "get", "immediate") is None
    assert (await call(cache, "get_entry", "permanent")).value is None
    now[0] = 1009
    assert await call(cache, "get", "temporary") == {"uuid": "one"}
    now[0] = 1010
    assert await call(cache, "get_entry", "temporary") is None
    assert [entry.key for entry in await call(cache, "entries")] == ["permanent"]
    assert await call(cache, "delete", "temporary") is True
    assert await call(cache, "delete", "temporary") is False
    assert await call(cache, "invalidate") == 2  # Includes the expired immediate entry.


async def test_records_are_detached_json_and_overwrite_resets_expiration(cache_case):
    cache, now = cache_case
    value = {"items": [1]}
    await call(cache, "set", "key", value, ttl=10)
    value["items"].append(2)
    entry = await call(cache, "get_entry", "key")
    entry.value["items"].append(3)
    assert await call(cache, "get", "key") == {"items": [1]}
    await call(cache, "set", "key", (1, 2))
    now[0] = 2000
    assert await call(cache, "get", "key") == [1, 2]
    assert (await call(cache, "get_entry", "key")).expires_at is None


@pytest.mark.parametrize("prefix", ["a%_", "A", "雪", "x\0y"])
async def test_prefixes_are_literal_and_namespace_is_exact(cache_case, prefix):
    cache, _ = cache_case
    for name in [prefix + "b", prefix + "a", "other", "axxb", "a"]:
        await call(cache, "set", name, name, namespace="one")
    await call(cache, "set", prefix + "a", "foreign", namespace="two")
    entries = await call(cache, "entries", namespace="one", prefix=prefix)
    assert [entry.key for entry in entries] == [prefix + "a", prefix + "b"]
    assert await call(cache, "invalidate", namespace="one", prefix=prefix) == 2
    assert await call(cache, "get", prefix + "a", namespace="two") == "foreign"
    assert await call(cache, "get", "other", namespace="one") == "other"


@pytest.mark.parametrize("ttl", [-1, float("nan"), float("inf")])
async def test_invalid_expiration_preserves_existing_record(cache_case, ttl):
    cache, _ = cache_case
    await call(cache, "set", "key", "original")
    with pytest.raises(ValueError):
        await call(cache, "set", "key", "replacement", ttl=ttl)
    assert await call(cache, "get", "key") == "original"
    with pytest.raises((ValueError, TypeError)):
        await call(cache, "set", "key", {"unsupported": object()})
    assert await call(cache, "get", "key") == "original"


async def test_scoped_cache_isolates_credentials_projects_profiles_and_endpoints(cache_case):
    cache, _ = cache_case
    client = ContreeClient(token="one", project="a", base_url="https://one.invalid")
    scope = CacheScope.from_client(client)
    wrapper = ScopedAsyncCache if isinstance(cache, (AsyncMemoryCache, AsyncSQLiteCache)) else ScopedSyncCache
    view = wrapper(cache, scope)
    await call(view, "set", "key", "private", ttl=10)
    assert (await call(view, "get_entry", "key")).key == "key"
    assert [entry.key for entry in await call(view, "entries")] == ["key"]
    for options in [{"token": "two"}, {"project": "b"}, {"base_url": "https://two.invalid"}]:
        config = {"token": "one", "project": "a", "base_url": "https://one.invalid", **options}
        other = wrapper(
            cache,
            CacheScope.from_client(
                ContreeClient(token=config["token"], project=config["project"], base_url=config["base_url"])
            ),
        )
        assert await call(other, "get", "key") is None
        assert await call(other, "invalidate") == 0
    other = wrapper(cache, CacheScope.from_client(client, profile="another"))
    assert await call(other, "get", "key") is None
    assert "one" not in scope.namespace("uploads")
    await call(view, "close")
    assert await call(view, "delete", "key") is True
    await call(cache, "set", "unscoped", "still open")


async def test_sqlite_expiration_survives_sync_async_reopen(tmp_path):
    path = tmp_path / "cache.db"
    with SyncSQLiteCache(path, clock=lambda: 100) as cache:
        cache.set("key", "value", ttl=10)
    async with AsyncSQLiteCache(path, clock=lambda: 109) as cache:
        assert await cache.get("key") == "value"
    with SyncSQLiteCache(path, clock=lambda: 110) as cache:
        assert cache.get("key") is None
