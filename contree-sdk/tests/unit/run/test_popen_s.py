from tests.e2e.sdk.run.test_popen_s import test_popen_error_s as _test_popen_error_s
from tests.e2e.sdk.run.test_popen_s import test_popen_s as _test_popen_s


def test_popen_s(fake_image_s, api_fake_popen):
    _test_popen_s(fake_image_s)


def test_popen_error_s(fake_image_s, api_fake_popen_error):
    _test_popen_error_s(fake_image_s)
