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
    session = ContreeSession(client, image="tag:alpine:3.20")

    print("\nExample 1: Positional command")
    result = session.run("/bin/echo", args=["Hello from command parameter!"])
    print(f"Result: {stdout_text(result)=}, {exit_code(result)=}")

    print("\nExample 2: Command with arguments")
    result = session.run("/bin/ls", args=["-la", "/tmp"])
    print(f"Result: {stdout_text(result)=}, {exit_code(result)=}")

    print("\nExample 3: Command with environment variables")
    result = session.run("/bin/printenv", args=["MY_VAR"], env={"MY_VAR": "test_value"})
    print(f"Result: {stdout_text(result)=}, {exit_code(result)=}")

    print("\nExample 4: Preserve environment variables in the resulting image")
    session.run(
        shell="true",
        env={"MY_PERSISTED_VAR": "persisted_value"},
        preserve_env=True,
        disposable=False,
    )
    result = session.run("/bin/printenv", args=["MY_PERSISTED_VAR"])
    print(f"Result: {stdout_text(result)=}, {exit_code(result)=}")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
