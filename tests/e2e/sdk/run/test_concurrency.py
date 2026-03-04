import asyncio
from time import monotonic

from contree_sdk import Contree
from contree_sdk.sdk.objects.image import ContreeImage


_OCI_URL = "docker://ghcr.io/linuxserver/code-server:latest"
_PARALLEL_IMPORTS = 2
_PARALLEL_RUNS = 3


async def test_parallel_imports_succeed_under_low_limits(low_limits_contree: Contree, *, check_timing: bool = True):
    completion_times = []

    async def import_and_record():
        result = await low_limits_contree.images.import_from(_OCI_URL, timeout=300)
        completion_times.append(monotonic())
        return result

    results = await asyncio.gather(*[import_and_record() for _ in range(_PARALLEL_IMPORTS)])

    assert len(results) == _PARALLEL_IMPORTS
    assert all(isinstance(r, ContreeImage) for r in results)
    if check_timing:
        assert max(completion_times) - min(completion_times) > 1.0


async def test_parallel_runs_succeed_under_low_limits(low_limits_contree: Contree, *, check_timing: bool = True):
    images = await low_limits_contree.images()
    image = images[0]

    completion_times = []

    async def run_and_record():
        result = await image.run(shell="echo hello")
        completion_times.append(monotonic())
        return result

    results = await asyncio.gather(*[run_and_record() for _ in range(_PARALLEL_RUNS)])

    assert len(results) == _PARALLEL_RUNS
    assert all(isinstance(r, ContreeImage) for r in results)
    assert all(r.stdout == "hello\n" for r in results)
    assert all(r.exit_code == 0 for r in results)
    if check_timing:
        assert max(completion_times) - min(completion_times) > 1.0
