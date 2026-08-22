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
    print(f"Created session: {session.session_id=}, {session.image_uuid=}")

    print("\nExample 1: A non-disposable run advances the session's history")
    result1 = session.run(shell="echo 'First command' > /tmp/data.txt", disposable=False)
    print(f"First run: {exit_code(result1)=}, image now {session.image_uuid=}")

    print("\nExample 2: Later runs see state from earlier ones")
    result2 = session.run(shell="cat /tmp/data.txt")
    print(f"Read file: {stdout_text(result2)=}")

    print("\nExample 3: Session history is a log of every non-disposable run")
    result3 = session.run(shell="echo 'Second line' >> /tmp/data.txt", disposable=False)
    print(f"Append to file: {exit_code(result3)=}")

    entries, _ = session.history()
    print(f"History: {[(entry.kind, entry.title) for entry in entries]}")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
