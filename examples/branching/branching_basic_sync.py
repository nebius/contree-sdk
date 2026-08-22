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


def main(client: ContreeSyncClient):
    session = ContreeSession(client, image="tag:alpine:latest", session_id="branching-demo")

    print("Example 1: Commit on main")
    session.run(shell="echo base > /tmp/state.txt", disposable=False)

    print("\nExample 2: Branch off main and diverge")
    session.create_branch("experiment")
    session.switch_branch("experiment")
    session.run(shell="echo experiment >> /tmp/state.txt", disposable=False)
    print(f"Branches: {session.list_branches()}")

    print("\nExample 3: Switching back to main leaves the experiment branch untouched")
    session.switch_branch("main")
    result = session.run(shell="cat /tmp/state.txt")
    print(f"Main branch content: {stdout_text(result)=}")

    print("\nExample 4: Roll back a commit on main")
    session.run(shell="echo second-commit >> /tmp/state.txt", disposable=False)
    session.rollback()
    result = session.run(shell="cat /tmp/state.txt")
    print(f"After rollback: {stdout_text(result)=}")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
