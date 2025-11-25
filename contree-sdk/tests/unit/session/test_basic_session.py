from uuid import uuid4

import pytest

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.image_like.state import ImageState
from contree_sdk.sdk.objects.session._async import ContreeSession
from contree_sdk.sdk.objects.session._sync import ContreeSessionSync


@pytest.fixture
def fake_image(fake_contree) -> ContreeImage:
    return ContreeImage(
        client=fake_contree,
        tag="fake-image",
        uuid=uuid4(),
    )


@pytest.fixture
def fake_image_s(fake_contree_s) -> ContreeImageSync:
    return ContreeImageSync(
        client=fake_contree_s,
        tag="fake-image",
        uuid=uuid4(),
    )


def test_create_session(fake_image):
    session = fake_image.session()
    assert isinstance(session, ContreeSession)

    assert session.state != ImageState.PREPARED
    session.run("some command")

    assert session.state == ImageState.PREPARED


def test_create_session_s(fake_image_s):
    session = fake_image_s.session()
    assert isinstance(session, ContreeSessionSync)

    assert session.state != ImageState.PREPARED
    session.run("some command")

    assert session.state == ImageState.PREPARED
