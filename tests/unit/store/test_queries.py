"""The public query contract behaves the same for every native store."""

import inspect

import pytest


async def call(store, method, *args, **kwargs):
    value = getattr(store, method)(*args, **kwargs)
    return await value if inspect.isawaitable(value) else value


async def populate(store):
    root = await call(store, "append", "project_demo", image_uuid="root", parent_id=None, kind="init")
    common = await call(store, "append", "project_demo", image_uuid="common", parent_id=root.id, operation_uuid="op-2")
    await call(store, "create_branch", "project_demo", "feature")
    main = await call(store, "append", "project_demo", image_uuid="main", parent_id=common.id, operation_uuid="op-3")
    fork = await call(store, "append", "project_demo", image_uuid="fork", parent_id=common.id, branch="feature")
    tip = await call(
        store, "append", "project_demo", image_uuid="feature", parent_id=fork.id, branch="feature", files=("/file",)
    )
    await call(store, "set_session_cwd", "project_demo", "/work")
    await call(store, "set_session_env", "project_demo", {"MODE": "test"})
    return root, common, main, fork, tip


async def test_queries_do_not_move_head_branch_or_metadata(store_case):
    root, common, main, fork, tip = await populate(store_case)
    before = await call(store_case, "read_session", "project_demo")
    assert await call(store_case, "resolve_history", "project_demo") == main
    assert await call(store_case, "resolve_history", "project_demo", offset=-1) == common
    assert await call(store_case, "resolve_history", "project_demo", offset=-2) == root
    assert await call(store_case, "resolve_history", "project_demo", branch="feature") == tip
    assert await call(store_case, "resolve_history", "project_demo", branch="feature", offset=-1) == fork
    assert await call(store_case, "resolve_history", "project_demo", history_id=common.id, offset=1) == fork
    assert await call(store_case, "resolve_history", "project_demo", history_id=common.id, offset=2) == tip
    assert await call(store_case, "resolve_history", "project_demo", history_id=root.id) == root
    assert await call(store_case, "read_session", "project_demo") == before
    # A detached snapshot remains usable after local state moves or the store closes.
    await call(store_case, "switch_branch", "project_demo", "feature")
    await call(store_case, "set_session_cwd", "project_demo", "/changed")
    assert before.resolve() == main
    assert before.metadata.cwd == "/work"
    before.metadata.env["MODE"] = "local copy"
    assert (await call(store_case, "get_session_metadata", "project_demo")).env == {"MODE": "test"}


@pytest.mark.parametrize(
    "position",
    [
        {"offset": -3},
        {"offset": 1},
        {"history_id": 0},
        {"history_id": -1},
        {"history_id": 999},
        {"branch": "missing"},
        {"history_id": 1, "branch": "main"},
    ],
)
async def test_invalid_positions_leave_state_unchanged(store_case, position):
    await populate(store_case)
    before = await call(store_case, "read_session", "project_demo")
    with pytest.raises(ValueError):
        await call(store_case, "resolve_history", "project_demo", **position)
    assert await call(store_case, "read_session", "project_demo") == before


async def test_session_lookup_and_foreign_ids_are_explicit(store_case):
    root, _, _, _, _ = await populate(store_case)
    foreign = await call(store_case, "append", "other_demo", image_uuid="other", parent_id=None)
    with pytest.raises(ValueError, match="ambiguous"):
        await call(store_case, "find_session", "demo")
    assert await call(store_case, "find_session", "project_demo") == "project_demo"
    with pytest.raises(ValueError, match="not found"):
        await call(store_case, "resolve_history", "demo")
    with pytest.raises(ValueError, match="not found"):
        await call(store_case, "resolve_history", "project_demo", history_id=foreign.id)
    with pytest.raises(ValueError, match="not found"):
        await call(store_case, "resolve_history", "other_demo", history_id=root.id)


async def test_operation_lookup_does_not_fall_back_to_an_ancestor(store_case):
    root, common, main, fork, tip = await populate(store_case)
    assert await call(store_case, "resolve_operation", "project_demo") == "op-3"
    assert await call(store_case, "resolve_operation", "project_demo", offset=-1) == "op-2"
    for position in ({"history_id": root.id}, {"branch": "feature"}, {"history_id": fork.id}):
        with pytest.raises(ValueError, match="no operation UUID"):
            await call(store_case, "resolve_operation", "project_demo", **position)
    assert await call(store_case, "tip", "project_demo") == main


async def test_summaries_include_all_branches_and_use_literal_prefixes(store_case):
    root, common, main, fork, tip = await populate(store_case)
    await call(store_case, "append", "project_%_literal", image_uuid="other", parent_id=None)
    await call(store_case, "append", "project_x_literal", image_uuid="other", parent_id=None)
    summary = await call(store_case, "get_session_summary", "project_demo")
    assert summary.tip == main
    assert summary.active_branch == "main"
    assert summary.entry_count == 5
    assert summary.created_at == root.created_at
    assert summary.last_entry_at == tip.created_at
    assert summary.metadata.cwd == "/work"
    assert [(item.name, item.tip, item.is_active) for item in summary.branches] == [
        ("feature", tip, False),
        ("main", main, True),
    ]
    summaries = await call(store_case, "list_session_summaries", prefix="project_%_")
    assert [item.session_id for item in summaries] == ["project_%_literal"]
    assert await call(store_case, "list_session_summaries", prefix="missing") == []


async def test_prune_retains_active_keep_history_metadata_and_other_sessions(store_case):
    await populate(store_case)
    for name in ("svc:active", "svc:keep", "svc:old", "svc:older", "ordinary"):
        await call(store_case, "create_branch", "project_demo", name)
    await call(store_case, "switch_branch", "project_demo", "svc:active")
    await call(store_case, "append", "other", image_uuid="other", parent_id=None, branch="svc:old")
    before = await call(store_case, "read_session", "project_demo")
    options = {"prefix": "svc:", "keep": ["svc:keep", "missing"]}
    assert await call(store_case, "prune_branches", "project_demo", dry_run=True, **options) == ("svc:old", "svc:older")
    assert await call(store_case, "read_session", "project_demo") == before
    assert await call(store_case, "prune_branches", "project_demo", **options) == ("svc:old", "svc:older")
    after = await call(store_case, "read_session", "project_demo")
    assert after.entries == before.entries
    assert after.metadata == before.metadata
    assert after.resolve() == before.resolve()
    assert [item.name for item in after.branches] == ["feature", "main", "ordinary", "svc:active", "svc:keep"]
    assert await call(store_case, "list_branches", "other") == [("svc:old", True)]
    assert await call(store_case, "prune_branches", "project_demo", **options) == ()


async def test_prune_requires_explicit_scope_and_literal_names(store_case):
    await populate(store_case)
    for name in ("svc:%_one", "svc:xxone", "svc:keep"):
        await call(store_case, "create_branch", "project_demo", name)
    before = await call(store_case, "read_session", "project_demo")
    with pytest.raises(ValueError, match="nonempty"):
        await call(store_case, "prune_branches", "project_demo", prefix="")
    with pytest.raises(TypeError, match="one string"):
        await call(store_case, "prune_branches", "project_demo", prefix="svc:", keep="svc:keep")
    assert await call(store_case, "read_session", "project_demo") == before
    assert await call(store_case, "prune_branches", "project_demo", prefix="svc:%_") == ("svc:%_one",)


async def test_unknown_queries_do_not_create_sessions(store_case):
    for method, kwargs in [("read_session", {}), ("get_session_summary", {}), ("prune_branches", {"prefix": "svc:"})]:
        with pytest.raises(ValueError, match="not found"):
            await call(store_case, method, "unknown", **kwargs)
    assert await call(store_case, "list_sessions") == []
    assert await call(store_case, "list_session_summaries") == []
