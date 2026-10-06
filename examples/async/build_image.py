import os
from asyncio import run, to_thread
from pathlib import Path
from tempfile import TemporaryDirectory
from types import EllipsisType

from contree_client.asyncio import ContreeAsyncClient
from contree_client.models import InstanceResult
from contree_client.types import ContreeAsyncClient as ContreeAsyncClientBase

from contree_sdk.docker import ContreeAsyncDockerBuilder


DOCKERFILE = """\
FROM {base_image}
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
    Path(context_dir, "Dockerfile").write_text(DOCKERFILE.format(base_image=os.environ["CONTREE_IMAGE"]))
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
        result = await session.run(shell="/greet.sh", env={"GREETING": "hello from a built image"})
        print(f"Output: {stdout_text(result)=}")


async def run_with_client() -> None:
    async with ContreeAsyncClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        await main(client=client)


if __name__ == "__main__":
    run(run_with_client())


def test_build_image(doc_api, capsys):
    import runpy

    doc_api.complete()
    doc_api.complete(stdout="hello from a built image\n")
    doc_api.async_client.mock("update_image_tag", None)
    runpy.run_path(__file__, run_name="__main__")

    client = doc_api.async_client
    calls = client.calls_for("spawn_instance")
    assert len(calls) == 2
    assert calls[0].kwargs["files"]["/greet.sh"].uuid == "uploaded-file"
    assert "chmod +x /greet.sh" in calls[0].args[0]
    assert calls[1].args[1] == "image-1"
    assert calls[1].kwargs["env"] == {"GREETING": "hello from a built image"}
    assert client.calls_for("update_image_tag")[0].args == ("image-1", "example/greeter:latest")
    assert "hello from a built image" in capsys.readouterr().out
