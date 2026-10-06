"""Stage-copy cache identity follows inputs rather than temporary path randomness."""

from unittest.mock import AsyncMock, Mock

import pytest

from contree_sdk.docker import ContreeAsyncDockerBuilder, ContreeDockerBuilder


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
@pytest.mark.parametrize("change", ["source_image", "source_path", "destination", "mode", "no_cache"])
async def test_stage_copy_cache_reuse_and_invalidation(
    doc_api, doc_stage_archive, tmp_path, monkeypatch, asynchronous, change
):
    client = doc_api.async_client if asynchronous else doc_api.sync
    images = {"tag:base": "base", "tag:source": "source-1"}

    def resolve(reference):
        return images.get(reference, reference)

    monkeypatch.setattr(
        client, "resolve_image", AsyncMock(side_effect=resolve) if asynchronous else Mock(side_effect=resolve)
    )
    for _ in range(2):
        doc_api.complete()
    dockerfile = tmp_path / "Dockerfile"
    original = "FROM tag:base\nCOPY --from=tag:source --chmod=0600 /built.txt /target.txt\n"
    dockerfile.write_text(original)
    builder = ContreeAsyncDockerBuilder(doc_api.async_client) if asynchronous else ContreeDockerBuilder(doc_api.sync)

    async def build(**kwargs):
        if isinstance(builder, ContreeAsyncDockerBuilder):
            return await builder.build(tmp_path, session_id="stage-cache", **kwargs)
        return builder.build(tmp_path, session_id="stage-cache", **kwargs)

    first = await build()
    assert await build() == first
    assert len(client.calls_for("spawn_instance")) == 1
    if change == "source_image":
        images["tag:source"] = "source-2"
    elif change == "source_path":
        dockerfile.write_text(original.replace("/built.txt", "/other.txt"))
    elif change == "destination":
        dockerfile.write_text(original.replace("/target.txt", "/elsewhere.txt"))
    elif change == "mode":
        dockerfile.write_text(original.replace("0600", "0644"))
    await build(no_cache=change == "no_cache")
    assert len(client.calls_for("spawn_instance")) == 2
