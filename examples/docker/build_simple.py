from asyncio import run, to_thread
from pathlib import Path
from tempfile import TemporaryDirectory
from types import EllipsisType

from contree_client.asyncio import ContreeAsyncClient
from contree_client.models import InstanceResult
from contree_client.types import ContreeAsyncClient as ContreeAsyncClientBase

from contree_sdk.docker import ContreeAsyncDockerBuilder


DOCKERFILE = """\
FROM tag:alpine:latest
ENV GREETING="hello from a built image"
COPY greet.sh /greet.sh
RUN chmod +x /greet.sh
"""


def stdout_text(result: InstanceResult) -> str:
    stream = result.stdout
    if isinstance(stream, EllipsisType):
        raise TypeError("command produced no stdout")
    return stream.as_text()


def write_context_files(context_dir: str) -> None:
    Path(context_dir, "Dockerfile").write_text(DOCKERFILE)
    Path(context_dir, "greet.sh").write_text('#!/bin/sh\necho "$GREETING"\n')


async def main(client: ContreeAsyncClientBase):
    with TemporaryDirectory() as context_dir:
        await to_thread(write_context_files, context_dir)

        builder = ContreeAsyncDockerBuilder(client)
        image_uuid = await builder.build(context_dir, tag="example/greeter:latest")
        print(f"Built image: {image_uuid=}")

        session = builder.session
        if session is None:
            raise RuntimeError("build produced no session")
        result = await session.run(shell="/greet.sh")
        print(f"Output: {stdout_text(result)=}")


if __name__ == "__main__":
    run(main(client=ContreeAsyncClient.from_profile()))
