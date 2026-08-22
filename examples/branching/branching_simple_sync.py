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
    session = ContreeSession(client, image="tag:alpine:latest")

    session.run(shell='echo "$RANDOM" > /tmp/random.txt', disposable=False)
    print(f"Base commit, image: {session.image_uuid}\n")

    for letter in ("A", "B", "C"):
        result = session.run(
            shell=f"echo '{letter}' >> /tmp/random.txt && cat /tmp/random.txt",
            disposable=False,
        )
        print(f"After {letter}: {stdout_text(result).strip()}")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
