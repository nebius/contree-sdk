from concurrent.futures.thread import ThreadPoolExecutor
from random import choices

from rich.live import Live
from rich.text import Text

from contree_sdk import ContreeSync
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.objects.image import ContreeImageSync


RANDOM_INT_COMMAND = "od -An -N2 -tu2 /dev/urandom"
N_RUNS = 10
N_WORKERS = 3


def test_threaded_pool_run_same_client(image_s: ContreeImageSync):
    pool = ThreadPoolExecutor(max_workers=N_WORKERS)
    futures = []
    for _ in range(N_RUNS):
        futures.append(pool.submit(image_s.run(shell=RANDOM_INT_COMMAND).wait))

    raw_results = [fut.result().stdout for fut in futures]
    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS


def test_threaded_pool_run_different_clients(contree_config: ContreeConfig):
    pool = ThreadPoolExecutor(max_workers=N_WORKERS)
    futures = []
    for _ in range(N_RUNS):
        image_s = choices(ContreeSync(contree_config).images())[0]
        futures.append(pool.submit(image_s.run(shell=RANDOM_INT_COMMAND).wait))

    raw_results = [fut.result().stdout for fut in futures]
    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS


def test_threaded_pool_create_run_and_create_client(contree_config: ContreeConfig, image_tag):
    def _run():
        image_s = ContreeSync(contree_config).images.pull(image_tag)
        return image_s.run(shell=RANDOM_INT_COMMAND).wait()

    pool = ThreadPoolExecutor(max_workers=N_WORKERS)
    futures = []
    for _ in range(N_RUNS):
        futures.append(pool.submit(_run))

    raw_results = [fut.result().stdout for fut in futures]
    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS


def test_thread_pool_create_run_same_client(contree_s: ContreeSync, image_tag):
    def _run():
        image_s = contree_s.images.pull(image_tag)
        return image_s.run(shell=RANDOM_INT_COMMAND).wait()

    pool = ThreadPoolExecutor(max_workers=N_WORKERS)
    futures = []
    for _ in range(N_RUNS):
        futures.append(pool.submit(_run))

    raw_results = [fut.result().stdout for fut in futures]
    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS


def test_threaded_pool_with_rich_live_context(contree_config: ContreeConfig, image_tag):
    def _run():
        client = ContreeSync(contree_config)
        session = client.images.pull(image_tag).session()
        return session.run(shell=RANDOM_INT_COMMAND).wait()

    with Live(Text("Testing..."), refresh_per_second=40), ThreadPoolExecutor(max_workers=N_WORKERS) as executor:
        futures = [executor.submit(_run) for _ in range(N_RUNS)]
        raw_results = [fut.result().stdout for fut in futures]

    results = list(map(int, raw_results))
    assert len(set(results)) == len(results) == len(futures) == N_RUNS
