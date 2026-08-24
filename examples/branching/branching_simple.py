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
    session = ContreeAsyncSession(client, image="tag:alpine:latest")

    await session.run(shell='echo "$RANDOM" > /tmp/random.txt', disposable=False)
    print(f"Base commit, image: {session.image_uuid}\n")

    for letter in ("A", "B", "C"):
        result = await session.run(
            shell=f"echo '{letter}' >> /tmp/random.txt && cat /tmp/random.txt",
            disposable=False,
        )
        print(f"After {letter}: {stdout_text(result).strip()}")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile()))
