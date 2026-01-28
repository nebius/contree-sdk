from subprocess import CalledProcessError

from contree_sdk.sdk.objects.image import ContreeImageSync
from contree_sdk.sdk.objects.subprocess import ContreeProcessSync


def test_popen_s(image_s: ContreeImageSync):
    process = image_s.popen(
        ["/bin/ls", "-la"],
        cwd="/dev",
    )

    assert isinstance(process, ContreeProcessSync)

    process.wait()

    assert process.returncode == 0
    for i in ["root", "tty", " random", "drwxr-xr-x", " null"]:
        assert i in process.stdout
    assert process.stderr == ""


def test_popen_error_s(image_s: ContreeImageSync):
    process = image_s.popen(
        ["/bin/ls", "-la", "/totally/fake/directory"],
        check=True,
    )
    assert isinstance(process, ContreeProcessSync)
    import pytest

    with pytest.raises(CalledProcessError) as exc_info:
        process.wait()

    err = exc_info.value
    assert err.returncode != 0
    assert "No such file" in (err.stderr or "")
    assert err.cmd == ["/bin/ls", "-la", "/totally/fake/directory"]


def test_popen_shell_s(image_s: ContreeImageSync):
    process = image_s.popen("echo 'Hello World' && echo 'Error message' >&2", shell=True)

    assert isinstance(process, ContreeProcessSync)

    process.wait()

    assert process.returncode == 0
    assert "Hello World" in process.stdout
    assert "Error message" in process.stderr


def test_popen_stdin_s(image_s: ContreeImageSync):
    process = image_s.popen(["/bin/cat"], stdin="Hello from stdin\nSecond line\n")

    assert isinstance(process, ContreeProcessSync)

    process.wait()

    assert process.returncode == 0
    assert "Hello from stdin" in process.stdout
    assert "Second line" in process.stdout


def test_popen_communicate_s(image_s: ContreeImageSync):
    process = image_s.popen(["/bin/grep", "test"])

    assert isinstance(process, ContreeProcessSync)

    stdout, stderr = process.communicate(input="test line\nother line\ntest again\n")

    assert process.returncode == 0
    assert "test line" in stdout
    assert "test again" in stdout
    assert "other line" not in stdout


def test_popen_env_variables_s(image_s: ContreeImageSync):
    process = image_s.popen(
        "echo $TEST_VAR && echo $ANOTHER_VAR",
        shell=True,
        env={"TEST_VAR": "test_value", "ANOTHER_VAR": "another_value"},
    )

    assert isinstance(process, ContreeProcessSync)

    process.wait()

    assert process.returncode == 0
    assert "test_value" in process.stdout
    assert "another_value" in process.stdout
