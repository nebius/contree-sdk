import os
from types import EllipsisType

from contree_client.models import InstanceResult
from contree_client.sync import ContreeClient
from contree_client.types import ContreeSyncClient

from contree_sdk.session import ContreeSession


def stdout_text(result: InstanceResult) -> str:
    stream = result.stdout
    if isinstance(stream, EllipsisType):
        raise TypeError("command produced no stdout")
    return stream.as_text()


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
        print(f"Subprocess: {stdout_text(result)=}, {exit_code(result)=}")

        second = operation.run("echo", args=["another one"])
        result = second.wait()
        print(f"Second subprocess: {stdout_text(result)=}, {exit_code(result)=}")


if __name__ == "__main__":
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        main(client=client)


def test_subprocess(doc_api, capsys):
    import runpy

    from contree_client.models import InstanceResult, InstanceResultState, StreamRepr

    doc_api.subprocess(stdout="hello from a subspawn\n")
    client = doc_api.sync
    client.mock("operation_subprocess_create", 3)
    client.mock(
        "operation_subprocess",
        InstanceResult(state=InstanceResultState(exit_code=0), stdout=StreamRepr.from_text("another one\n")),
    )
    runpy.run_path(__file__, run_name="__main__")

    calls = client.calls_for("operation_subprocess_create")
    assert len(calls) == 2
    assert calls[0].kwargs["args"] == ["hello from a subspawn"]
    assert calls[1].kwargs["args"] == ["another one"]
    assert [call.args for call in client.calls_for("operation_subprocess")] == [("operation-1", 2), ("operation-1", 3)]
    output = capsys.readouterr().out
    assert "hello from a subspawn" in output
    assert "another one" in output
