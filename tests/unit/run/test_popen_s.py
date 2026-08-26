from uuid import UUID

from tests.e2e.sdk.run.test_popen_s import test_popen_communicate_s as _test_popen_communicate_s
from tests.e2e.sdk.run.test_popen_s import test_popen_env_variables_s as _test_popen_env_variables_s
from tests.e2e.sdk.run.test_popen_s import test_popen_error_s as _test_popen_error_s
from tests.e2e.sdk.run.test_popen_s import test_popen_s as _test_popen_s
from tests.e2e.sdk.run.test_popen_s import test_popen_shell_s as _test_popen_shell_s
from tests.e2e.sdk.run.test_popen_s import test_popen_stdin_s as _test_popen_stdin_s
from tests.unit.fixtures.operations import queue_run


def test_popen_s(fake_image_s, result_image_uuid: UUID):
    ls_output = (
        "total 0\n"
        "drwxr-xr-x  5 root  root  180 Jan  7 10:00 .\n"
        "drwxr-xr-x 18 root  root  360 Jan  7 10:00 ..\n"
        "crw-rw-rw-  1 root  tty   5, 0 Jan  7 10:00 tty\n"
        "crw-rw-rw-  1 root  root  1, 8 Jan  7 10:00 random\n"
        "crw-rw-rw-  1 root  root  1, 3 Jan  7 10:00 null\n"
    )
    queue_run(fake_image_s.client.api, stdout=ls_output, result_image_uuid=str(result_image_uuid))
    _test_popen_s(fake_image_s)


def test_popen_error_s(fake_image_s, result_image_uuid: UUID):
    error_stderr = "ls: cannot access '/totally/fake/directory': No such file or directory\n"
    queue_run(fake_image_s.client.api, stderr=error_stderr, exit_code=2, result_image_uuid=str(result_image_uuid))
    _test_popen_error_s(fake_image_s)


def test_popen_shell_s(fake_image_s, result_image_uuid: UUID):
    queue_run(
        fake_image_s.client.api,
        stdout="Hello World\n",
        stderr="Error message\n",
        result_image_uuid=str(result_image_uuid),
    )
    _test_popen_shell_s(fake_image_s)


def test_popen_stdin_s(fake_image_s, result_image_uuid: UUID):
    queue_run(
        fake_image_s.client.api, stdout="Hello from stdin\nSecond line\n", result_image_uuid=str(result_image_uuid)
    )
    _test_popen_stdin_s(fake_image_s)


def test_popen_communicate_s(fake_image_s, result_image_uuid: UUID):
    queue_run(fake_image_s.client.api, stdout="test line\ntest again\n", result_image_uuid=str(result_image_uuid))
    _test_popen_communicate_s(fake_image_s)


def test_popen_env_variables_s(fake_image_s, result_image_uuid: UUID):
    queue_run(fake_image_s.client.api, stdout="test_value\nanother_value\n", result_image_uuid=str(result_image_uuid))
    _test_popen_env_variables_s(fake_image_s)
