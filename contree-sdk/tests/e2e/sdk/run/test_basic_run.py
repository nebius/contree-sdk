import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync


@pytest.fixture
async def image(contree: Contree) -> ContreeImage:
    return await contree.images.pull("0bd59a5d-9f0d-4fab-9376-001ec247cd78")


@pytest.fixture
async def image_s(contree_s: ContreeSync) -> ContreeImageSync:
    return contree_s.images.pull("0bd59a5d-9f0d-4fab-9376-001ec247cd78")


_shell_command = 'cat - ; echo "this is stdout" ; echo "this is stderr" 1>&2'
_stdin = "my input\n"
_stdout = _stdin + "this is stdout\n"
_stderr = "this is stderr\n"


async def test_basic_run(image):
    result = await image.run(shell=_shell_command, stdin=_stdin)
    assert isinstance(result, ContreeImage)

    assert result.stdout == _stdout
    assert result.stderr == _stderr
    assert result.exit_code == 0


def test_basic_run_s(image_s):
    result = image_s.run(shell=_shell_command, stdin=_stdin).wait()
    assert isinstance(result, ContreeImageSync)

    assert result.stdout == _stdout
    assert result.stderr == _stderr
    assert result.exit_code == 0
