import pytest

from contree_sdk.store import AsyncStore


async def test_append_creates_root_entry(async_store: AsyncStore):
    entry = await async_store.append("s1", image_uuid="img-1", parent_id=None, kind="init")
    assert entry.id > 0
    assert entry.session_id == "s1"
    assert entry.image_uuid == "img-1"
    assert entry.parent_id is None
    assert await async_store.active_branch("s1") == "main"
    assert await async_store.tip("s1") == entry


async def test_append_chains_history(async_store: AsyncStore):
    root = await async_store.append("s1", image_uuid="img-0", parent_id=None, kind="init")
    child = await async_store.append(
        "s1", image_uuid="img-1", parent_id=root.id, kind="run", title="echo hi", exit_code=0
    )
    assert child.parent_id == root.id
    assert child.exit_code == 0
    tip = await async_store.tip("s1")
    assert tip == child


async def test_get_entry_missing_raises(async_store: AsyncStore):
    with pytest.raises(ValueError):
        await async_store.get_entry("s1", 999)


async def test_get_entry_wrong_session_raises(async_store: AsyncStore):
    root = await async_store.append("s1", image_uuid="img-0", parent_id=None)
    with pytest.raises(ValueError):
        await async_store.get_entry("other-session", root.id)


async def test_tip_of_unknown_session_is_none(async_store: AsyncStore):
    assert await async_store.tip("does-not-exist") is None


async def test_navigate_absolute_and_back(async_store: AsyncStore):
    root = await async_store.append("s1", image_uuid="img-0", parent_id=None)
    mid = await async_store.append("s1", image_uuid="img-1", parent_id=root.id)
    tip = await async_store.append("s1", image_uuid="img-2", parent_id=mid.id)

    back_one = await async_store.navigate("s1", -1)
    assert back_one == mid

    jumped = await async_store.navigate("s1", tip.id)
    assert jumped == tip

    with pytest.raises(ValueError):
        await async_store.navigate("s1", 0)


async def test_rollback_walks_back_and_errors_past_root(async_store: AsyncStore):
    root = await async_store.append("s1", image_uuid="img-0", parent_id=None)
    await async_store.append("s1", image_uuid="img-1", parent_id=root.id)

    entry = await async_store.rollback("s1")
    assert entry == root

    with pytest.raises(ValueError):
        await async_store.rollback("s1")


async def test_navigate_forward_picks_latest_child(async_store: AsyncStore):
    root = await async_store.append("s1", image_uuid="img-0", parent_id=None)
    await async_store.append("s1", image_uuid="img-1a", parent_id=root.id, title="first branch")
    second = await async_store.append("s1", image_uuid="img-1b", parent_id=root.id, title="second branch")

    await async_store.navigate("s1", root.id)
    forward = await async_store.navigate_forward("s1")
    assert forward == second

    with pytest.raises(ValueError):
        await async_store.navigate_forward("s1")


async def test_branch_create_switch_list_delete(async_store: AsyncStore):
    root = await async_store.append("s1", image_uuid="img-0", parent_id=None)
    await async_store.append("s1", image_uuid="img-1", parent_id=root.id)

    await async_store.create_branch("s1", "feature", from_branch="main")
    branches = dict(await async_store.list_branches("s1"))
    assert branches == {"main": True, "feature": False}

    switched = await async_store.switch_branch("s1", "feature")
    assert switched.image_uuid == "img-1"
    assert await async_store.active_branch("s1") == "feature"

    with pytest.raises(ValueError):
        await async_store.delete_branch("s1", "feature")

    await async_store.switch_branch("s1", "main")
    await async_store.delete_branch("s1", "feature")
    assert dict(await async_store.list_branches("s1")) == {"main": True}


async def test_create_branch_diverges_history(async_store: AsyncStore):
    root = await async_store.append("s1", image_uuid="img-0", parent_id=None)
    await async_store.create_branch("s1", "feature", from_branch="main")

    await async_store.append("s1", image_uuid="img-main", parent_id=root.id, branch="main")
    await async_store.append("s1", image_uuid="img-feature", parent_id=root.id, branch="feature")

    main_tip = await async_store.tip("s1", branch="main")
    feature_tip = await async_store.tip("s1", branch="feature")
    assert main_tip is not None
    assert feature_tip is not None
    assert main_tip.image_uuid == "img-main"
    assert feature_tip.image_uuid == "img-feature"


async def test_list_find_delete_sessions(async_store: AsyncStore):
    await async_store.append("proj_alpha", image_uuid="img-0", parent_id=None)
    await async_store.append("proj_beta", image_uuid="img-0", parent_id=None)

    assert await async_store.list_sessions() == ["proj_alpha", "proj_beta"]
    assert await async_store.find_session("alpha") == "proj_alpha"

    with pytest.raises(ValueError):
        await async_store.find_session("missing")

    assert await async_store.delete_session("proj_alpha") is True
    assert await async_store.delete_session("proj_alpha") is False
    assert await async_store.list_sessions() == ["proj_beta"]


async def test_find_session_prefers_exact_match_over_suffix_match(async_store: AsyncStore):
    # "bar" is both an exact session_id and a suffix of "foobar" - the exact
    # match must win, not whichever match a query happens to find first
    await async_store.append("bar", image_uuid="img-0", parent_id=None)
    await async_store.append("foobar", image_uuid="img-0", parent_id=None)

    assert await async_store.find_session("bar") == "bar"


async def test_find_session_does_not_treat_underscore_as_a_wildcard(async_store: AsyncStore):
    # the suffix pattern is "_<name>" with a LITERAL underscore separator; before
    # escaping, SQL's own "_" wildcard let ANY single character satisfy that slot
    await async_store.append("fooXbar", image_uuid="img-0", parent_id=None)

    with pytest.raises(ValueError):
        await async_store.find_session("bar")


async def test_history_dag_reports_branch_pointers(async_store: AsyncStore):
    root = await async_store.append("s1", image_uuid="img-0", parent_id=None)
    tip = await async_store.append("s1", image_uuid="img-1", parent_id=root.id)
    await async_store.create_branch("s1", "feature")

    entries, branch_map = await async_store.history_dag("s1")
    assert [entry.id for entry in entries] == [root.id, tip.id]
    assert set(branch_map[tip.id]) == {"main", "feature"}


async def test_append_records_files_on_the_entry(async_store: AsyncStore):
    entry = await async_store.append("s1", image_uuid="img-0", parent_id=None, files=("/a.txt", "/b.txt"))
    assert entry.files == ("/a.txt", "/b.txt")

    entries, _ = await async_store.history_dag("s1")
    assert entries[0].files == ("/a.txt", "/b.txt")


async def test_get_session_metadata_defaults_to_empty(async_store: AsyncStore):
    metadata = await async_store.get_session_metadata("s1")
    assert metadata.cwd is None
    assert metadata.env == {}


async def test_set_session_cwd_round_trips(async_store: AsyncStore):
    await async_store.set_session_cwd("s1", "/app")
    assert (await async_store.get_session_metadata("s1")).cwd == "/app"

    await async_store.set_session_cwd("s1", None)
    assert (await async_store.get_session_metadata("s1")).cwd is None


async def test_set_session_env_merges_and_unsets(async_store: AsyncStore):
    await async_store.set_session_env("s1", {"FOO": "1", "BAR": "2"})
    assert (await async_store.get_session_metadata("s1")).env == {"FOO": "1", "BAR": "2"}

    await async_store.set_session_env("s1", {"FOO": "updated", "BAR": None})
    assert (await async_store.get_session_metadata("s1")).env == {"FOO": "updated"}
