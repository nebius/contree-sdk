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
    session = ContreeSession(client, image="tag:busybox:latest")

    operation = session.spawn(shell="sleep 300")
    with operation:
        subprocess = operation.run("echo hello from a subspawn")
        result = subprocess.wait()
        print(f"Subprocess: {stdout_text(result)=}, {exit_code(result)=}")

        second = operation.run("echo another one")
        result = second.wait()
        print(f"Second subprocess: {stdout_text(result)=}, {exit_code(result)=}")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
