from uuid import UUID

import pytest
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.image_like.state import ImageState
from contree_sdk.sdk.objects.session._async import ContreeSession
from contree_sdk.sdk.objects.session._sync import ContreeSessionSync
from tests.e2e.sdk.session.test_basic_session import test_session_multiple_runs as _test_session_multiple_runs
from tests.e2e.sdk.session.test_basic_session import test_session_run as _test_session_run
from tests.e2e.sdk.session.test_basic_session import test_session_run_s as _test_session_run_s
from tests.unit.fixtures.operations import queue_run
from tests.unit.fixtures.runs import RUN_STDERR, RUN_STDOUT


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
def fake_session(fake_image: ContreeImage, fake_api: ContreeAsyncClient, result_image_uuid: UUID) -> ContreeSession:
    queue_run(fake_api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    return fake_image.session()


@pytest.fixture
def fake_session_s(
    fake_image_s: ContreeImageSync, fake_api_s: ContreeClient, result_image_uuid: UUID
) -> ContreeSessionSync:
    queue_run(fake_api_s, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    return fake_image_s.session()


async def test_session_run(fake_session: ContreeSession):
    await _test_session_run(fake_session)


def test_session_run_s(fake_session_s: ContreeSessionSync):
    _test_session_run_s(fake_session_s)


@pytest.fixture
def fake_session_multiple(
    fake_image_s: ContreeImageSync, fake_api_s: ContreeClient, result_image_uuid: UUID
) -> ContreeSessionSync:
    # a session mutates itself in place (`copy_self` is a no-op), so each
    # queued run must keep handing back a live `uuid` -- otherwise the next
    # `.run()` in the chain sees an unreferenceable (disposed) image and
    # raises `DisposableImageRunError`.
    for stdout in ("", "some other step\n", "some data"):
        queue_run(fake_api_s, stdout=stdout, result_image_uuid=str(result_image_uuid))
    return fake_image_s.session()


def test_session_multiple_runs(fake_session_multiple: ContreeSessionSync):
    _test_session_multiple_runs(fake_session_multiple)
