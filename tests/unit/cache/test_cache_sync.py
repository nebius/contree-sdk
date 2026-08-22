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
