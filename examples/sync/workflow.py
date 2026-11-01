"""Upload input, compare branches, and resume the saved baseline."""

import os
from uuid import uuid4

from contree_client.sync import ContreeClient

from contree_sdk import ContreeSession
from contree_sdk.store import SyncSQLiteStore


def main() -> None:
    session_id = f"example-{uuid4().hex}"
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        with SyncSQLiteStore("workflow.db") as store:
            session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"], store=store, session_id=session_id)
            session.run(
                shell="sort /input.txt > /result.txt",
                files={"/input.txt": b"pear\napple\n"},
            )
            baseline_node = session.tip_id
            session.create_branch("reverse")
            session.switch_branch("reverse")
            session.run(shell="sort -r /input.txt > /result.txt")
            print("Reverse:")
            print((session.read_file("/result.txt")).decode())
            session.switch_branch("main")

        # Reopen the saved node. Local branch selection is not shared through Store.
        with SyncSQLiteStore("workflow.db") as store:
            resumed = ContreeSession(client, store=store, session_id=session_id, node_id=baseline_node)
            print("Baseline:")
            print((resumed.read_file("/result.txt")).decode())


if __name__ == "__main__":
    main()


def test_workflow(doc_api, capsys):
    import runpy

    doc_api.complete()
    doc_api.complete()
    doc_api.download(b"pear\napple\n")
    doc_api.download(b"apple\npear\n")
    runpy.run_path(__file__, run_name="__main__")

    client = doc_api.sync
    calls = client.calls_for("spawn_instance")
    assert len(calls) == 2
    assert calls[0].kwargs["files"]["/input.txt"].uuid == "uploaded-file"
    assert calls[0].args == ("sort /input.txt > /result.txt", "base-image")
    assert calls[1].args[1] == "image-1"
    assert calls[1].args[0] == "sort -r /input.txt > /result.txt"
    assert [call.args for call in client.calls_for("inspect_image_download")] == [
        ("image-2", "/result.txt"),
        ("image-1", "/result.txt"),
    ]
    assert len(client.calls_for("resolve_image")) == 1
    assert capsys.readouterr().out == "Reverse:\npear\napple\n\nBaseline:\napple\npear\n\n"
