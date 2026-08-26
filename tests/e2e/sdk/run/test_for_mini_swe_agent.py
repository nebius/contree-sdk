from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import ExitStack
from random import choices

from contree_client.httpx import ContreeClient
from rich.live import Live
from rich.text import Text

from contree_sdk import ContreeSync
from contree_sdk.sdk.objects.image import ContreeImageSync
from tests.e2e.conftest import TOKEN_FACTORY_SANDBOXES_URL


RANDOM_INT_COMMAND = "od -An -N2 -tu2 /dev/urandom"
N_RUNS = 10
N_WORKERS = 3


def test_threaded_pool_run_same_client(image_s: ContreeImageSync):
    pool = ThreadPoolExecutor(max_workers=N_WORKERS)
    futures = [pool.submit(image_s.run(shell=RANDOM_INT_COMMAND).wait) for _ in range(N_RUNS)]

    raw_results = [fut.result().stdout for fut in futures]
    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS


def test_threaded_pool_run_different_clients(_contree_token: str):
    # Each client must stay open until its submitted .wait() actually runs on
    # a worker thread, so the ExitStack closes them only after every future
    # (not just its cheap, synchronous .run() setup) has completed.
    with ExitStack() as clients, ThreadPoolExecutor(max_workers=N_WORKERS) as pool:
        futures = []
        for _ in range(N_RUNS):
            api = clients.enter_context(ContreeClient(_contree_token, base_url=TOKEN_FACTORY_SANDBOXES_URL))
            image_s = choices(ContreeSync(api).images())[0]
            futures.append(pool.submit(image_s.run(shell=RANDOM_INT_COMMAND).wait))

        raw_results = [fut.result().stdout for fut in futures]

    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS


def test_threaded_pool_create_run_and_create_client(_contree_token: str, image_tag):
    def run_once():
        with ContreeClient(_contree_token, base_url=TOKEN_FACTORY_SANDBOXES_URL) as api:
            image_s = ContreeSync(api).images.pull(image_tag)
            return image_s.run(shell=RANDOM_INT_COMMAND).wait()

    pool = ThreadPoolExecutor(max_workers=N_WORKERS)
    futures = [pool.submit(run_once) for _ in range(N_RUNS)]

    raw_results = [fut.result().stdout for fut in futures]
    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS


def test_thread_pool_create_run_same_client(contree_s: ContreeSync, image_tag):
    def _run():
        image_s = contree_s.images.pull(image_tag)
        return image_s.run(shell=RANDOM_INT_COMMAND).wait()

    pool = ThreadPoolExecutor(max_workers=N_WORKERS)
    futures = [pool.submit(_run) for _ in range(N_RUNS)]

    raw_results = [fut.result().stdout for fut in futures]
    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS


def test_threaded_pool_with_rich_live_context(_contree_token: str, image_tag):
    def run_once():
        with ContreeClient(_contree_token, base_url=TOKEN_FACTORY_SANDBOXES_URL) as api:
            client = ContreeSync(api)
            session = client.images.pull(image_tag).session()
            return session.run(shell=RANDOM_INT_COMMAND).wait()

    with Live(Text("Testing..."), refresh_per_second=40), ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
        futures = [executor.submit(run_once) for _ in range(N_RUNS)]
        raw_results = [fut.result().stdout for fut in futures]

    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS
