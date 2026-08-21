import pytest

from contree_sdk.store import Store


async def test_append_creates_root_entry(store: Store):
    entry = await store.append("s1", image_uuid="img-1", parent_id=None, kind="init")
    assert entry.id > 0
    assert entry.session_id == "s1"
    assert entry.image_uuid == "img-1"
    assert entry.parent_id is None
    assert await store.active_branch("s1") == "main"
    assert await store.tip("s1") == entry


async def test_append_chains_history(store: Store):
    root = await store.append("s1", image_uuid="img-0", parent_id=None, kind="init")
    child = await store.append("s1", image_uuid="img-1", parent_id=root.id, kind="run", title="echo hi", exit_code=0)
    assert child.parent_id == root.id
    assert child.exit_code == 0
    tip = await store.tip("s1")
    assert tip == child


async def test_get_entry_missing_raises(store: Store):
    with pytest.raises(ValueError):
        await store.get_entry("s1", 999)


async def test_get_entry_wrong_session_raises(store: Store):
    root = await store.append("s1", image_uuid="img-0", parent_id=None)
    with pytest.raises(ValueError):
        await store.get_entry("other-session", root.id)


async def test_tip_of_unknown_session_is_none(store: Store):
    assert await store.tip("does-not-exist") is None


async def test_navigate_absolute_and_back(store: Store):
    root = await store.append("s1", image_uuid="img-0", parent_id=None)
    mid = await store.append("s1", image_uuid="img-1", parent_id=root.id)
    tip = await store.append("s1", image_uuid="img-2", parent_id=mid.id)

    back_one = await store.navigate("s1", -1)
    assert back_one == mid

    jumped = await store.navigate("s1", tip.id)
    assert jumped == tip

    with pytest.raises(ValueError):
        await store.navigate("s1", 0)


async def test_rollback_walks_back_and_errors_past_root(store: Store):
    root = await store.append("s1", image_uuid="img-0", parent_id=None)
    await store.append("s1", image_uuid="img-1", parent_id=root.id)

    entry = await store.rollback("s1")
    assert entry == root

    with pytest.raises(ValueError):
        await store.rollback("s1")


async def test_navigate_forward_picks_latest_child(store: Store):
    root = await store.append("s1", image_uuid="img-0", parent_id=None)
    await store.append("s1", image_uuid="img-1a", parent_id=root.id, title="first branch")
    second = await store.append("s1", image_uuid="img-1b", parent_id=root.id, title="second branch")

    await store.navigate("s1", root.id)
    forward = await store.navigate_forward("s1")
    assert forward == second

    with pytest.raises(ValueError):
        await store.navigate_forward("s1")


async def test_branch_create_switch_list_delete(store: Store):
    root = await store.append("s1", image_uuid="img-0", parent_id=None)
    await store.append("s1", image_uuid="img-1", parent_id=root.id)

    await store.create_branch("s1", "feature", from_branch="main")
    branches = dict(await store.list_branches("s1"))
    assert branches == {"main": True, "feature": False}

    switched = await store.switch_branch("s1", "feature")
    assert switched.image_uuid == "img-1"
    assert await store.active_branch("s1") == "feature"

    with pytest.raises(ValueError):
        await store.delete_branch("s1", "feature")

    await store.switch_branch("s1", "main")
    await store.delete_branch("s1", "feature")
    assert dict(await store.list_branches("s1")) == {"main": True}


async def test_create_branch_diverges_history(store: Store):
    root = await store.append("s1", image_uuid="img-0", parent_id=None)
    await store.create_branch("s1", "feature", from_branch="main")

    await store.append("s1", image_uuid="img-main", parent_id=root.id, branch="main")
    await store.append("s1", image_uuid="img-feature", parent_id=root.id, branch="feature")

    main_tip = await store.tip("s1", branch="main")
    feature_tip = await store.tip("s1", branch="feature")
    assert main_tip is not None
    assert feature_tip is not None
    assert main_tip.image_uuid == "img-main"
    assert feature_tip.image_uuid == "img-feature"


async def test_list_find_delete_sessions(store: Store):
    await store.append("proj_alpha", image_uuid="img-0", parent_id=None)
    await store.append("proj_beta", image_uuid="img-0", parent_id=None)

    assert await store.list_sessions() == ["proj_alpha", "proj_beta"]
    assert await store.find_session("alpha") == "proj_alpha"

    with pytest.raises(ValueError):
        await store.find_session("missing")

    assert await store.delete_session("proj_alpha") is True
    assert await store.delete_session("proj_alpha") is False
    assert await store.list_sessions() == ["proj_beta"]


async def test_history_dag_reports_branch_pointers(store: Store):
    root = await store.append("s1", image_uuid="img-0", parent_id=None)
    tip = await store.append("s1", image_uuid="img-1", parent_id=root.id)
    await store.create_branch("s1", "feature")

    entries, branch_map = await store.history_dag("s1")
    assert [entry.id for entry in entries] == [root.id, tip.id]
    assert set(branch_map[tip.id]) == {"main", "feature"}
