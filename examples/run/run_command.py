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
    session = ContreeAsyncSession(client, image="tag:alpine:3.20")

    print("\nExample 1: Positional command")
    result = await session.run("/bin/echo", args=["Hello from command parameter!"])
    print(f"Result: {stdout_text(result)=}, {exit_code(result)=}")

    print("\nExample 2: Command with arguments")
    result = await session.run("/bin/ls", args=["-la", "/tmp"])
    print(f"Result: {stdout_text(result)=}, {exit_code(result)=}")

    print("\nExample 3: Command with environment variables")
    result = await session.run("/bin/printenv", args=["MY_VAR"], env={"MY_VAR": "test_value"})
    print(f"Result: {stdout_text(result)=}, {exit_code(result)=}")

    print("\nExample 4: Preserve environment variables in the resulting image")
    await session.run(
        shell="true",
        env={"MY_PERSISTED_VAR": "persisted_value"},
        preserve_env=True,
        disposable=False,
    )
    result = await session.run("/bin/printenv", args=["MY_PERSISTED_VAR"])
    print(f"Result: {stdout_text(result)=}, {exit_code(result)=}")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile()))
