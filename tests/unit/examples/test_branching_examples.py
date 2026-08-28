from contree_client.testing import ContreeAsyncClient, ContreeClient
from examples.branching.branching_basic import main as branching_basic_main
from examples.branching.branching_basic_sync import main as branching_basic_main_s
from examples.branching.branching_simple import main as branching_simple_main
from examples.branching.branching_simple_sync import main as branching_simple_main_s

from tests.unit.examples.test_run_examples import queue_runs


async def test_branching_simple_example(fake_api: ContreeAsyncClient):
    queue_runs(fake_api, 4)  # child, then 3 grandchildren chained off it
    await branching_simple_main(fake_api)


def test_branching_simple_example_s(fake_api_s: ContreeClient):
    queue_runs(fake_api_s, 4)
    branching_simple_main_s(fake_api_s)


async def test_branching_basic_example(fake_api: ContreeAsyncClient):
    queue_runs(fake_api, 9)  # 3 + 2 + (1 base + 2 chained off it) + 2
    await branching_basic_main(fake_api)


def test_branching_basic_example_s(fake_api_s: ContreeClient):
    queue_runs(fake_api_s, 9)
    branching_basic_main_s(fake_api_s)
