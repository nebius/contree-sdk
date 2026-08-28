from uuid import uuid4

from contree_client.models import DirectoryList, FileItem
from contree_client.testing import ContreeAsyncClient, ContreeClient
from examples.run.preserve_env import main as preserve_env_main
from examples.run.preserve_env_sync import main as preserve_env_main_s
from examples.run.run_command import main as run_command_main
from examples.run.run_command_sync import main as run_command_main_s
from examples.run.run_file_inspect import main as run_file_inspect_main
from examples.run.run_file_inspect_sync import main as run_file_inspect_main_s
from examples.run.run_files import main as run_files_main
from examples.run.run_files_sync import main as run_files_main_s
from examples.run.run_io_files import main as run_io_files_main
from examples.run.run_io_files_sync import main as run_io_files_main_s
from examples.run.run_io_objects import main as run_io_objects_main
from examples.run.run_io_objects_sync import main as run_io_objects_main_s
from examples.run.run_popen_sync import main as run_popen_main_s
from examples.run.run_simple import main as run_simple_main
from examples.run.run_simple_sync import main as run_simple_main_s

from tests.unit.fixtures.files import queue_upload
from tests.unit.fixtures.images import queue_image_lookup
from tests.unit.fixtures.operations import queue_run


DIR_LISTING = [
    FileItem(
        size=4,
        path="passwd",
        owner="root",
        group="root",
        uid=0,
        gid=0,
        mode=0o100644,
        mtime=1700000000,
        nlink=1,
        is_dir=False,
        is_regular=True,
        is_symlink=False,
        is_socket=False,
        is_fifo=False,
        symlink_to="",
    )
]


def queue_runs(api, count: int, **kwargs) -> None:
    """Queue `count` independent runs, each with a fresh, valid `result_image_uuid`."""
    for _ in range(count):
        queue_run(api, result_image_uuid=str(uuid4()), **kwargs)


async def test_run_simple_example(fake_api: ContreeAsyncClient):
    queue_runs(fake_api, 4)
    queue_run(fake_api, exit_code=1, stderr="Error message\n", result_image_uuid=str(uuid4()))
    await run_simple_main(fake_api)


def test_run_simple_example_s(fake_api_s: ContreeClient):
    queue_runs(fake_api_s, 4)
    queue_run(fake_api_s, exit_code=1, stderr="Error message\n", result_image_uuid=str(uuid4()))
    run_simple_main_s(fake_api_s)


async def test_run_command_example(fake_api: ContreeAsyncClient, image_uuid, image_tag):
    queue_image_lookup(fake_api, image_uuid, image_tag)
    queue_runs(fake_api, 3)
    queue_runs(fake_api, 2)  # preserve_env run, then the chained prepared.run()
    await run_command_main(fake_api)


def test_run_command_example_s(fake_api_s: ContreeClient, image_uuid, image_tag):
    queue_image_lookup(fake_api_s, image_uuid, image_tag)
    queue_runs(fake_api_s, 3)
    queue_runs(fake_api_s, 2)
    run_command_main_s(fake_api_s)


async def test_run_file_inspect_example(fake_api: ContreeAsyncClient):
    queue_runs(fake_api, 1)
    fake_api.mock("inspect_find_image_by_tag", str(uuid4()))
    fake_api.mock("inspect_image_download", b"Generated inside container\n")
    fake_api.mock("inspect_image_list", DirectoryList(path="/etc", files=DIR_LISTING))
    await run_file_inspect_main(fake_api)


def test_run_file_inspect_example_s(fake_api_s: ContreeClient):
    queue_runs(fake_api_s, 1)
    fake_api_s.mock("inspect_find_image_by_tag", str(uuid4()))
    fake_api_s.mock("inspect_image_download", b"Generated inside container\n")
    fake_api_s.mock("inspect_image_list", DirectoryList(path="/etc", files=DIR_LISTING))
    run_file_inspect_main_s(fake_api_s)


async def test_run_files_example(fake_api: ContreeAsyncClient, file_uuid, file_sha256):
    queue_upload(fake_api, file_uuid, file_sha256)
    queue_runs(fake_api, 5)
    await run_files_main(fake_api)


def test_run_files_example_s(fake_api_s: ContreeClient, file_uuid, file_sha256):
    queue_upload(fake_api_s, file_uuid, file_sha256)
    queue_runs(fake_api_s, 5)
    run_files_main_s(fake_api_s)


async def test_run_io_files_example(fake_api: ContreeAsyncClient):
    queue_runs(fake_api, 3, stdout="ls output\n")
    await run_io_files_main(fake_api)


def test_run_io_files_example_s(fake_api_s: ContreeClient):
    queue_runs(fake_api_s, 3, stdout="ls output\n")
    run_io_files_main_s(fake_api_s)


async def test_run_io_objects_example(fake_api: ContreeAsyncClient):
    queue_runs(fake_api, 5, stdout="apple\nbanana\n", stderr="to stderr\n")
    await run_io_objects_main(fake_api)


def test_run_io_objects_example_s(fake_api_s: ContreeClient):
    queue_runs(fake_api_s, 5, stdout="apple\nbanana\n", stderr="to stderr\n")
    run_io_objects_main_s(fake_api_s)


def test_run_popen_sync_example(fake_api_s: ContreeClient):
    queue_runs(fake_api_s, 5, stdout="output\n", stderr="stderr output\n")
    run_popen_main_s(fake_api_s)


async def test_preserve_env_example(fake_api: ContreeAsyncClient):
    queue_runs(fake_api, 2, stdout="persisted_value\n")
    await preserve_env_main(fake_api)


def test_preserve_env_example_s(fake_api_s: ContreeClient):
    queue_runs(fake_api_s, 2, stdout="persisted_value\n")
    preserve_env_main_s(fake_api_s)
