from contree_client.testing import ContreeAsyncClient, ContreeClient
from examples.session.session_simple import main as session_simple_main
from examples.session.session_simple_sync import main as session_simple_main_s

from tests.unit.examples.test_run_examples import queue_runs


async def test_session_simple_example(fake_api: ContreeAsyncClient):
    # session.run() x4, image.run() (base for a second session), then that
    # session's run() x3 -- 8 total, each needs a live result_image_uuid.
    queue_runs(fake_api, 8)
    await session_simple_main(fake_api)


def test_session_simple_example_s(fake_api_s: ContreeClient):
    queue_runs(fake_api_s, 8)
    session_simple_main_s(fake_api_s)
