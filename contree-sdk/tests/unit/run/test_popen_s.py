from tests.e2e.sdk.run.test_popen_s import test_popen_communicate_s as _test_popen_communicate_s
from tests.e2e.sdk.run.test_popen_s import test_popen_env_variables_s as _test_popen_env_variables_s
from tests.e2e.sdk.run.test_popen_s import test_popen_error_s as _test_popen_error_s
from tests.e2e.sdk.run.test_popen_s import test_popen_s as _test_popen_s
from tests.e2e.sdk.run.test_popen_s import test_popen_shell_s as _test_popen_shell_s
from tests.e2e.sdk.run.test_popen_s import test_popen_stdin_s as _test_popen_stdin_s


def test_popen_s(fake_image_s, api_fake_popen):
    _test_popen_s(fake_image_s)


def test_popen_error_s(fake_image_s, api_fake_popen_error):
    _test_popen_error_s(fake_image_s)


def test_popen_shell_s(fake_image_s, api_fake_popen_shell):
    _test_popen_shell_s(fake_image_s)


def test_popen_stdin_s(fake_image_s, api_fake_popen_stdin):
    _test_popen_stdin_s(fake_image_s)


def test_popen_communicate_s(fake_image_s, api_fake_popen_communicate):
    _test_popen_communicate_s(fake_image_s)


def test_popen_env_variables_s(fake_image_s, api_fake_popen_env):
    _test_popen_env_variables_s(fake_image_s)
