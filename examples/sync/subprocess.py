import os
from types import EllipsisType

from contree_client.models import InstanceResult
from contree_client.sync import ContreeClient
from contree_client.types import ContreeSyncClient

from contree_sdk.session import ContreeSession


def exit_code(result: InstanceResult) -> int:
    state = result.state
    if isinstance(state, EllipsisType) or isinstance(state.exit_code, EllipsisType):
        raise TypeError("command produced no exit code")
    return state.exit_code


def main(client: ContreeSyncClient):
    session = ContreeSession(client, image=os.environ["CONTREE_IMAGE"])

    operation = session.spawn(shell="sleep 300")
    with operation:
        subprocess = operation.run("echo", args=["hello from a subspawn"])
        result = subprocess.wait()
        print(result.stdout)
        print(f"Exit code: {exit_code(result)}")

        second = operation.run("echo", args=["another one"])
        result = second.wait()
        print(result.stdout)
        print(f"Exit code: {exit_code(result)}")


if __name__ == "__main__":
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        main(client=client)


def test_subprocess(doc_api, capsys):
    import runpy

    from contree_client.models import InstanceResult, InstanceResultState, StreamRepr
    from tests.unit.session.lazy_clients import event, subprocess_events

    doc_api.subprocess(stdout="hello from a subspawn\n")
    client = doc_api.sync
    client.mock("operation_subprocess_create", 3)
    client.mocks["follow_operation_events"].clear()
    client.mock(
        "follow_operation_events",
        [
            *subprocess_events(
                2,
                InstanceResult(
                    state=InstanceResultState(exit_code=0), stdout=StreamRepr.from_text("hello from a subspawn\n")
                ),
            ),
            *subprocess_events(
                3, InstanceResult(state=InstanceResultState(exit_code=0), stdout=StreamRepr.from_text("another one\n"))
            ),
            event("completion"),
        ],
    )
    runpy.run_path(__file__, run_name="__main__")

    calls = client.calls_for("operation_subprocess_create")
    assert len(calls) == 2
    assert calls[0].kwargs["args"] == ["hello from a subspawn"]
    assert calls[1].kwargs["args"] == ["another one"]
    assert not client.calls_for("operation_subprocess")
    output = capsys.readouterr().out
    assert output == "hello from a subspawn\n\nExit code: 0\nanother one\n\nExit code: 0\n"
