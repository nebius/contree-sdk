import pytest

from contree_sdk.sdk.exceptions import ContreeImageStateError
from contree_sdk.sdk.objects.image import ContreeImage
from contree_sdk.sdk.objects.image_like.state import ImageState


def test_pulled_image_has_no_result(fake_image: ContreeImage):
    assert fake_image.state == ImageState.PULLED
    with pytest.raises(ContreeImageStateError):
        _ = fake_image.result


def test_run_prepares_a_copy(fake_image: ContreeImage):
    prepared = fake_image.run(shell="true")

    assert prepared.state == ImageState.PREPARED
    assert fake_image.state == ImageState.PULLED


async def test_await_unprepared_raises(fake_image: ContreeImage):
    with pytest.raises(ContreeImageStateError):
        await fake_image


async def test_executing_image_cannot_be_reconfigured(fake_image: ContreeImage, api_fake_run):
    started = await fake_image.run(shell="true").start()

    assert started.state == ImageState.EXECUTING
    with pytest.raises(ContreeImageStateError):
        started.run(shell="again")


async def test_succeeded_image_can_run_again(fake_image: ContreeImage, api_fake_run):
    result = await fake_image.run(shell="true")

    assert result.state == ImageState.SUCCEEDED
    assert result.run(shell="again").state == ImageState.PREPARED
