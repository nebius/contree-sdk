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
    session = ContreeAsyncSession(client, image="tag:busybox:latest")

    async with session.run(shell="sleep 300") as operation:
        subprocess = await operation.run("echo hello from a subspawn")
        result = await subprocess.wait()
        print(f"Subprocess: {stdout_text(result)=}, {exit_code(result)=}")

        second = await operation.run("echo another one")
        result = await second.wait()
        print(f"Second subprocess: {stdout_text(result)=}, {exit_code(result)=}")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile()))
