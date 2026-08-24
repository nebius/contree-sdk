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


async def main(client: ContreeAsyncClientBase):
    session = ContreeAsyncSession(client, image="tag:alpine:latest", session_id="branching-demo")

    print("Example 1: Commit on main")
    await session.run(shell="echo base > /tmp/state.txt", disposable=False)

    print("\nExample 2: Branch off main and diverge")
    await session.create_branch("experiment")
    await session.switch_branch("experiment")
    await session.run(shell="echo experiment >> /tmp/state.txt", disposable=False)
    print(f"Branches: {await session.list_branches()}")

    print("\nExample 3: Switching back to main leaves the experiment branch untouched")
    await session.switch_branch("main")
    result = await session.run(shell="cat /tmp/state.txt")
    print(f"Main branch content: {stdout_text(result)=}")

    print("\nExample 4: Roll back a commit on main")
    await session.run(shell="echo second-commit >> /tmp/state.txt", disposable=False)
    await session.rollback()
    result = await session.run(shell="cat /tmp/state.txt")
    print(f"After rollback: {stdout_text(result)=}")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile()))
