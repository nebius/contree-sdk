import pytest
from pytest_httpx import HTTPXMock

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.image_like.state import ImageState
from contree_sdk.sdk.objects.session._async import ContreeSession
from contree_sdk.sdk.objects.session._sync import ContreeSessionSync
from tests.e2e.sdk.session.test_basic_session import test_session_multiple_runs as _test_session_multiple_runs
from tests.e2e.sdk.session.test_basic_session import test_session_run as _test_session_run
from tests.e2e.sdk.session.test_basic_session import test_session_run_s as _test_session_run_s


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


@pytest.fixture
def fake_session(fake_image: ContreeImage, api_fake_run: HTTPXMock) -> ContreeSession:
    return fake_image.session()


@pytest.fixture
def fake_session_s(fake_image_s: ContreeImageSync, api_fake_run: HTTPXMock) -> ContreeSessionSync:
    return fake_image_s.session()


async def test_session_run(fake_session: ContreeSession):
    await _test_session_run(fake_session)


def test_session_run_s(fake_session_s: ContreeSessionSync):
    _test_session_run_s(fake_session_s)


@pytest.fixture
def fake_session_multiple(
    fake_image_s: ContreeImageSync, api_fake_session_multiple_runs: HTTPXMock
) -> ContreeSessionSync:
    return fake_image_s.session()


def test_session_multiple_runs(fake_session_multiple: ContreeSessionSync):
    _test_session_multiple_runs(fake_session_multiple)
