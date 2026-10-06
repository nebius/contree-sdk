import os
from asyncio import run
from types import EllipsisType

from contree_client.asyncio import ContreeAsyncClient
from contree_client.models import InstanceResult
from contree_client.types import ContreeAsyncClient as ContreeAsyncClientBase

from contree_sdk.session import ContreeAsyncSession


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


async def main(client: ContreeAsyncClientBase):
    session = ContreeAsyncSession(client, image=os.environ["CONTREE_IMAGE"])

    async with session.run(shell="sleep 300") as operation:
        subprocess = await operation.run("echo", args=["hello from a subspawn"])
        result = await subprocess.wait()
        print(f"Subprocess: {stdout_text(result)=}, {exit_code(result)=}")

        second = await operation.run("echo", args=["another one"])
        result = await second.wait()
        print(f"Second subprocess: {stdout_text(result)=}, {exit_code(result)=}")


async def run_with_client() -> None:
    async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        await main(client=client)


if __name__ == "__main__":
    run(run_with_client())


def test_subprocess(doc_api, capsys):
    import runpy

    from contree_client.models import InstanceResult, InstanceResultState, StreamRepr

    doc_api.subprocess(stdout="hello from a subspawn\n")
    client = doc_api.async_client
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
