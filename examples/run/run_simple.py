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


def stderr_text(result: InstanceResult) -> str:
    stream = result.stderr
    if isinstance(stream, EllipsisType):
        raise TypeError("command produced no stderr")
    return stream.as_text()


def exit_code(result: InstanceResult) -> int:
    state = result.state
    if isinstance(state, EllipsisType) or isinstance(state.exit_code, EllipsisType):
        raise TypeError("command produced no exit code")
    return state.exit_code


async def main(client: ContreeAsyncClientBase):
    session = ContreeAsyncSession(client, image="tag:busybox:latest")

    result = await session.run(shell="echo 'Hello World'")
    print(f"Simple echo: {stdout_text(result)=}, {exit_code(result)=}")

    result = await session.run(shell="pwd")
    print(f"Current directory: {stdout_text(result)=}, {exit_code(result)=}")

    result = await session.run(shell="ls -la")
    print(f"Directory listing: {stdout_text(result)=}, {exit_code(result)=}")

    result = await session.run(shell="cat -", stdin="Hello from stdin\n")
    print(f"Cat with stdin: {stdout_text(result)=}, {exit_code(result)=}")

    result = await session.run(shell="echo 'Error message' >&2; exit 1")
    print(f"Error command: {stdout_text(result)=}, {stderr_text(result)=}, {exit_code(result)=}")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile()))
