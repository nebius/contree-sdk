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
    print(f"Created session: {session.session_id=}, {session.image_uuid=}")

    print("\nExample 1: A non-disposable run advances the session's history")
    result1 = await session.run(shell="echo 'First command' > /tmp/data.txt", disposable=False)
    print(f"First run: {exit_code(result1)=}, image now {session.image_uuid=}")

    print("\nExample 2: Later runs see state from earlier ones")
    result2 = await session.run(shell="cat /tmp/data.txt")
    print(f"Read file: {stdout_text(result2)=}")

    print("\nExample 3: Session history is a log of every non-disposable run")
    result3 = await session.run(shell="echo 'Second line' >> /tmp/data.txt", disposable=False)
    print(f"Append to file: {exit_code(result3)=}")

    entries, _ = await session.history()
    print(f"History: {[(entry.kind, entry.title) for entry in entries]}")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile()))
