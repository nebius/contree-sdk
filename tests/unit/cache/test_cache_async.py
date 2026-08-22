from contree_sdk.cache import AsyncCache


async def test_get_missing_key_returns_none(async_cache: AsyncCache):
    assert await async_cache.get("missing") is None


async def test_set_then_get_roundtrips_dict_value(async_cache: AsyncCache):
    value = {"uuid": "abc", "sha256": "def"}
    await async_cache.set("key1", value)
    assert await async_cache.get("key1") == value


async def test_set_then_get_roundtrips_string_value(async_cache: AsyncCache):
    await async_cache.set("key1", "hello")
    assert await async_cache.get("key1") == "hello"


async def test_set_overwrites_existing_value(async_cache: AsyncCache):
    await async_cache.set("key1", "first")
    await async_cache.set("key1", "second")
    assert await async_cache.get("key1") == "second"


async def test_same_key_in_different_namespaces_does_not_collide(async_cache: AsyncCache):
    await async_cache.set("key1", "from-a", namespace="a")
    await async_cache.set("key1", "from-b", namespace="b")
    assert await async_cache.get("key1", namespace="a") == "from-a"
    assert await async_cache.get("key1", namespace="b") == "from-b"
    assert await async_cache.get("key1") is None
