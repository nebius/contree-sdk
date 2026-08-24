from contree_sdk.cache import SyncCache


def test_get_missing_key_returns_none(sync_cache: SyncCache):
    assert sync_cache.get("missing") is None


def test_set_then_get_roundtrips_dict_value(sync_cache: SyncCache):
    value = {"uuid": "abc", "sha256": "def"}
    sync_cache.set("key1", value)
    assert sync_cache.get("key1") == value


def test_set_then_get_roundtrips_string_value(sync_cache: SyncCache):
    sync_cache.set("key1", "hello")
    assert sync_cache.get("key1") == "hello"


def test_set_overwrites_existing_value(sync_cache: SyncCache):
    sync_cache.set("key1", "first")
    sync_cache.set("key1", "second")
    assert sync_cache.get("key1") == "second"


def test_same_key_in_different_namespaces_does_not_collide(sync_cache: SyncCache):
    sync_cache.set("key1", "from-a", namespace="a")
    sync_cache.set("key1", "from-b", namespace="b")
    assert sync_cache.get("key1", namespace="a") == "from-a"
    assert sync_cache.get("key1", namespace="b") == "from-b"
    assert sync_cache.get("key1") is None
