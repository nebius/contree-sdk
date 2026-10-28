"""SDK workflows use bounded Store calls without losing history semantics."""

from dataclasses import replace

import pytest

from contree_sdk.docker.context import AsyncBuildContext, BuildContext
from contree_sdk.docker.local_context import LocalContext
from contree_sdk.files import UploadedFile, UploadFileSpec
from contree_sdk.session.records import OperationRecord
from contree_sdk.store import AsyncStore, Node
from tests.unit.store.test_session_tree import client_for, session_for
from tests.unit.store.test_tree_store import call


async def test_staging_stops_at_committed_checkpoint_and_still_supports_legacy_history(store_case, mocker):
    store = store_case
    client = client_for(store, "consume")
    session = await session_for(store, client, image="base")
    await call(session.stage_files, {"/input": UploadFileSpec(source=UploadedFile(uuid="file", sha256="hash"))})
    parent = session.tip_id
    for index in range(1001):
        node = Node(id=f"legacy-{index:04}", parent_id=parent, kind="run", data={"image_uuid": "base"})
        await call(store.append, "shared", node)
        parent = node.id
    await call(session.navigate, parent)
    assert (await call(session.pending_files))[0].uuid == "file"
    await call(session.run, "consume")
    history = mocker.spy(store, "list_history")
    assert await call(session.pending_files) == ()
    assert history.call_count == 1
    assert history.call_args.kwargs["limit"] == 1
    await call(session.rollback)
    assert (await call(session.pending_files))[0].uuid == "file"
    await call(store.set_session_ttl, "shared", 0)
    with pytest.raises(ValueError, match="expired"):
        await call(session.pending_files)


async def test_operations_resolve_completions_in_batches(store_case, mocker):
    store = store_case
    session = await session_for(store, client_for(store, "unused"), image="base")
    expected = []
    for index in range(1001):
        record = OperationRecord(
            uuid=f"operation-{index:04}",
            session_id="shared",
            image_uuid="base",
            parent_id=session.tip_id,
            branch="main",
            title="work",
            disposable=False,
            request={},
            node_id=f"result-{index:04}",
        )
        await call(
            store.append,
            "shared",
            Node(
                id="operation-pending:" + record.uuid,
                parent_id=session.tip_id,
                kind="operation-pending",
                data={"record": record.to_dict(), "operation_uuid": record.uuid},
            ),
        )
        if index % 2:
            record = replace(record, response={})
            await call(
                store.append,
                "shared",
                Node(
                    id=record.node_id,
                    parent_id=session.tip_id,
                    kind="operation-result",
                    data={"record": record.to_dict()},
                ),
            )
        expected.append(record)
    pages = mocker.spy(store, "list_nodes")
    batches = mocker.spy(store, "get_nodes")
    individual = mocker.spy(store, "get_node")
    assert await call(session.list_operations, pending_only=False) == tuple(expected)
    assert pages.call_count == batches.call_count == 2
    assert individual.call_count == 0
    assert await call(session.list_operations) == tuple(record for record in expected if record.pending)


async def test_docker_lookup_reads_only_matching_children(store_case, mocker, tmp_path):
    store = store_case
    client = client_for(store, "unused")
    client.mock("check_image_archive", True)
    session = await session_for(store, client, image="base")
    root = session.tip_id
    sibling = Node(id="sibling", parent_id=root, kind="run", data={"image_uuid": "other"})
    await call(store.append, "shared", sibling)
    for index in range(1001):
        await call(
            store.append,
            "shared",
            Node(
                id=f"unrelated-{index:04}",
                parent_id=sibling.id,
                kind="run",
                data={"image_uuid": "wrong", "user": {"docker_hash": "target"}, "created_at": 100},
            ),
        )
    expected = Node(
        id="expected",
        parent_id=root,
        kind="run",
        data={
            "image_uuid": "wanted",
            "user": {"docker_hash": "target"},
            "created_at": 1,
        },
    )
    await call(store.append, "shared", expected)
    cls = AsyncBuildContext if isinstance(store, AsyncStore) else BuildContext
    context = cls(client=client, store=store, local=LocalContext(tmp_path), session_id="shared", session=session)
    pages = mocker.spy(store, "list_nodes")
    children = mocker.spy(store, "list_children")
    assert await call(context.try_cache_hit, "target") == "wanted"
    assert [request.args for request in client.calls_for("check_image_archive")] == [("wanted", "/")]
    assert pages.call_count == 0
    assert children.call_count == 1
    assert children.call_args.args == ("shared", root)
    assert children.call_args.kwargs["kind"] == "run"
