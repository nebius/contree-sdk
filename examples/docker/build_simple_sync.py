from pathlib import Path
from tempfile import TemporaryDirectory
from types import EllipsisType

from contree_client.models import InstanceResult
from contree_client.sync import ContreeClient
from contree_client.types import ContreeSyncClient

from contree_sdk.docker import ContreeDockerBuilder


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


def main(client: ContreeSyncClient):
    with TemporaryDirectory() as context_dir:
        Path(context_dir, "Dockerfile").write_text(DOCKERFILE)
        Path(context_dir, "greet.sh").write_text('#!/bin/sh\necho "$GREETING"\n')

        builder = ContreeDockerBuilder(client)
        image_uuid = builder.build(context_dir, tag="example/greeter:latest")
        print(f"Built image: {image_uuid=}")

        session = builder.session
        if session is None:
            raise RuntimeError("build produced no session")
        result = session.run(shell="/greet.sh")
        print(f"Output: {stdout_text(result)=}")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
