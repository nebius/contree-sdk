import pytest

from contree_sdk.store import SyncStore


def test_append_creates_root_entry(sync_store: SyncStore):
    entry = sync_store.append("s1", image_uuid="img-1", parent_id=None, kind="init")
    assert entry.id > 0
    assert entry.session_id == "s1"
    assert entry.image_uuid == "img-1"
    assert entry.parent_id is None
    assert sync_store.active_branch("s1") == "main"
    assert sync_store.tip("s1") == entry


def test_append_chains_history(sync_store: SyncStore):
    root = sync_store.append("s1", image_uuid="img-0", parent_id=None, kind="init")
    child = sync_store.append("s1", image_uuid="img-1", parent_id=root.id, kind="run", title="echo hi", exit_code=0)
    assert child.parent_id == root.id
    assert child.exit_code == 0
    tip = sync_store.tip("s1")
    assert tip == child


def test_get_entry_missing_raises(sync_store: SyncStore):
    with pytest.raises(ValueError):
        sync_store.get_entry("s1", 999)


def test_get_entry_wrong_session_raises(sync_store: SyncStore):
    root = sync_store.append("s1", image_uuid="img-0", parent_id=None)
    with pytest.raises(ValueError):
        sync_store.get_entry("other-session", root.id)


def test_tip_of_unknown_session_is_none(sync_store: SyncStore):
    assert sync_store.tip("does-not-exist") is None


def test_navigate_absolute_and_back(sync_store: SyncStore):
    root = sync_store.append("s1", image_uuid="img-0", parent_id=None)
    mid = sync_store.append("s1", image_uuid="img-1", parent_id=root.id)
    tip = sync_store.append("s1", image_uuid="img-2", parent_id=mid.id)

    back_one = sync_store.navigate("s1", -1)
    assert back_one == mid

    jumped = sync_store.navigate("s1", tip.id)
    assert jumped == tip

    with pytest.raises(ValueError):
        sync_store.navigate("s1", 0)


def test_rollback_walks_back_and_errors_past_root(sync_store: SyncStore):
    root = sync_store.append("s1", image_uuid="img-0", parent_id=None)
    sync_store.append("s1", image_uuid="img-1", parent_id=root.id)

    entry = sync_store.rollback("s1")
    assert entry == root

    with pytest.raises(ValueError):
        sync_store.rollback("s1")


def test_navigate_forward_picks_latest_child(sync_store: SyncStore):
    root = sync_store.append("s1", image_uuid="img-0", parent_id=None)
    sync_store.append("s1", image_uuid="img-1a", parent_id=root.id, title="first branch")
    second = sync_store.append("s1", image_uuid="img-1b", parent_id=root.id, title="second branch")

    sync_store.navigate("s1", root.id)
    forward = sync_store.navigate_forward("s1")
    assert forward == second

    with pytest.raises(ValueError):
        sync_store.navigate_forward("s1")


def test_branch_create_switch_list_delete(sync_store: SyncStore):
    root = sync_store.append("s1", image_uuid="img-0", parent_id=None)
    sync_store.append("s1", image_uuid="img-1", parent_id=root.id)

    sync_store.create_branch("s1", "feature", from_branch="main")
    branches = dict(sync_store.list_branches("s1"))
    assert branches == {"main": True, "feature": False}

    switched = sync_store.switch_branch("s1", "feature")
    assert switched.image_uuid == "img-1"
    assert sync_store.active_branch("s1") == "feature"

    with pytest.raises(ValueError):
        sync_store.delete_branch("s1", "feature")

    sync_store.switch_branch("s1", "main")
    sync_store.delete_branch("s1", "feature")
    assert dict(sync_store.list_branches("s1")) == {"main": True}


def test_create_branch_diverges_history(sync_store: SyncStore):
    root = sync_store.append("s1", image_uuid="img-0", parent_id=None)
    sync_store.create_branch("s1", "feature", from_branch="main")

    sync_store.append("s1", image_uuid="img-main", parent_id=root.id, branch="main")
    sync_store.append("s1", image_uuid="img-feature", parent_id=root.id, branch="feature")

    main_tip = sync_store.tip("s1", branch="main")
    feature_tip = sync_store.tip("s1", branch="feature")
    assert main_tip is not None
    assert feature_tip is not None
    assert main_tip.image_uuid == "img-main"
    assert feature_tip.image_uuid == "img-feature"


def test_list_find_delete_sessions(sync_store: SyncStore):
    sync_store.append("proj_alpha", image_uuid="img-0", parent_id=None)
    sync_store.append("proj_beta", image_uuid="img-0", parent_id=None)

    assert sync_store.list_sessions() == ["proj_alpha", "proj_beta"]
    assert sync_store.find_session("alpha") == "proj_alpha"

    with pytest.raises(ValueError):
        sync_store.find_session("missing")

    assert sync_store.delete_session("proj_alpha") is True
    assert sync_store.delete_session("proj_alpha") is False
    assert sync_store.list_sessions() == ["proj_beta"]


def test_find_session_prefers_exact_match_over_suffix_match(sync_store: SyncStore):
    # "bar" is both an exact session_id and a suffix of "foobar" - the exact
    # match must win, not whichever match a query happens to find first
    sync_store.append("bar", image_uuid="img-0", parent_id=None)
    sync_store.append("foobar", image_uuid="img-0", parent_id=None)

    assert sync_store.find_session("bar") == "bar"


def test_find_session_does_not_treat_underscore_as_a_wildcard(sync_store: SyncStore):
    # the suffix pattern is "_<name>" with a LITERAL underscore separator; before
    # escaping, SQL's own "_" wildcard let ANY single character satisfy that slot
    sync_store.append("fooXbar", image_uuid="img-0", parent_id=None)

    with pytest.raises(ValueError):
        sync_store.find_session("bar")


def test_history_dag_reports_branch_pointers(sync_store: SyncStore):
    root = sync_store.append("s1", image_uuid="img-0", parent_id=None)
    tip = sync_store.append("s1", image_uuid="img-1", parent_id=root.id)
    sync_store.create_branch("s1", "feature")

    entries, branch_map = sync_store.history_dag("s1")
    assert [entry.id for entry in entries] == [root.id, tip.id]
    assert set(branch_map[tip.id]) == {"main", "feature"}


def test_append_records_files_on_the_entry(sync_store: SyncStore):
    entry = sync_store.append("s1", image_uuid="img-0", parent_id=None, files=("/a.txt", "/b.txt"))
    assert entry.files == ("/a.txt", "/b.txt")

    entries, _ = sync_store.history_dag("s1")
    assert entries[0].files == ("/a.txt", "/b.txt")


def test_get_session_metadata_defaults_to_empty(sync_store: SyncStore):
    metadata = sync_store.get_session_metadata("s1")
    assert metadata.cwd is None
    assert metadata.env == {}


def test_set_session_cwd_round_trips(sync_store: SyncStore):
    sync_store.set_session_cwd("s1", "/app")
    assert sync_store.get_session_metadata("s1").cwd == "/app"

    sync_store.set_session_cwd("s1", None)
    assert sync_store.get_session_metadata("s1").cwd is None


def test_set_session_env_merges_and_unsets(sync_store: SyncStore):
    sync_store.set_session_env("s1", {"FOO": "1", "BAR": "2"})
    assert sync_store.get_session_metadata("s1").env == {"FOO": "1", "BAR": "2"}

    sync_store.set_session_env("s1", {"FOO": "updated", "BAR": None})
    assert sync_store.get_session_metadata("s1").env == {"FOO": "updated"}
