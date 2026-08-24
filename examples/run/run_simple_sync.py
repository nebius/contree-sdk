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


def main(client: ContreeSyncClient):
    session = ContreeSession(client, image="tag:busybox:latest")

    result = session.run(shell="echo 'Hello World'")
    print(f"Simple echo: {stdout_text(result)=}, {exit_code(result)=}")

    result = session.run(shell="pwd")
    print(f"Current directory: {stdout_text(result)=}, {exit_code(result)=}")

    result = session.run(shell="ls -la")
    print(f"Directory listing: {stdout_text(result)=}, {exit_code(result)=}")

    result = session.run(shell="cat -", stdin="Hello from stdin\n")
    print(f"Cat with stdin: {stdout_text(result)=}, {exit_code(result)=}")

    result = session.run(shell="echo 'Error message' >&2; exit 1")
    print(f"Error command: {stdout_text(result)=}, {stderr_text(result)=}, {exit_code(result)=}")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
