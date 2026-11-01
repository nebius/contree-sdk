import os
from pathlib import Path
from tempfile import TemporaryDirectory

from contree_client.sync import ContreeClient
from contree_client.types import ContreeSyncClient

from contree_sdk.docker import ContreeDockerBuilder


DOCKERFILE = """\
FROM {base_image}
ENV GREETING="hello from a built image"
COPY greet.sh /greet.sh
RUN chmod +x /greet.sh
"""


def main(client: ContreeSyncClient):
    with TemporaryDirectory() as context_dir:
        Path(context_dir, "Dockerfile").write_text(DOCKERFILE.format(base_image=os.environ["CONTREE_IMAGE"]))
        Path(context_dir, "greet.sh").write_text('#!/bin/sh\necho "$GREETING"\n')

        builder = ContreeDockerBuilder(client)
        image_uuid = builder.build(context_dir, tag="example/greeter:latest")
        print(f"Built image: {image_uuid=}")

        session = builder.session
        if session is None:
            raise RuntimeError("build produced no session")
        result = session.run(shell="/greet.sh", env={"GREETING": "hello from a built image"})
        print(result.stdout)


if __name__ == "__main__":
    with ContreeClient(token=os.environ["CONTREE_TOKEN"], base_url=os.environ["CONTREE_URL"]) as client:
        main(client=client)


def test_build_image(doc_api, capsys):
    import runpy

    doc_api.complete()
    doc_api.complete(stdout="hello from a built image\n")
    doc_api.sync.mock("update_image_tag", None)
    runpy.run_path(__file__, run_name="__main__")

    client = doc_api.sync
    calls = client.calls_for("spawn_instance")
    assert len(calls) == 2
    assert calls[0].kwargs["files"]["/greet.sh"].uuid == "uploaded-file"
    assert "chmod +x /greet.sh" in calls[0].args[0]
    assert calls[1].args[1] == "image-1"
    assert calls[1].kwargs["env"] == {"GREETING": "hello from a built image"}
    assert client.calls_for("update_image_tag")[0].args == ("image-1", "example/greeter:latest")
    assert capsys.readouterr().out.endswith("hello from a built image\n\n")
