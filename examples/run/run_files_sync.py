from pathlib import Path
from tempfile import NamedTemporaryFile
from types import EllipsisType

from contree_client.models import InstanceResult
from contree_client.sync import ContreeClient
from contree_client.types import ContreeSyncClient

from contree_sdk.session import ContreeSession


def stdout_text(result: InstanceResult) -> str:
    stream = result.stdout
    if isinstance(stream, EllipsisType):
        raise TypeError("command produced no stdout")
    return stream.as_text()


def exit_code(result: InstanceResult) -> int:
    state = result.state
    if isinstance(state, EllipsisType) or isinstance(state.exit_code, EllipsisType):
        raise TypeError("command produced no exit code")
    return state.exit_code


def main(client: ContreeSyncClient):
    session = ContreeSession(client, image="tag:busybox:latest")

    print("\nExample 1: Upload a local file by path")
    with NamedTemporaryFile(mode="w", suffix=".txt") as test_file:
        test_file.write("some txt file\nsecond line\n\nlast line\n")
        test_file.flush()

        result = session.run(shell=f"cat /{Path(test_file.name).name} | grep line", files=[test_file.name])
        print(f"Run with local file: {stdout_text(result)=}, {exit_code(result)=}")

    print("\nExample 2: Upload inline content to a specific path")
    result = session.run(
        shell="sh /file.sh",
        files={"/file.sh": b"#!/bin/sh\necho 'Hello from uploaded script'\npwd\n"},
    )
    print(f"Run with inline file: {stdout_text(result)=}, {exit_code(result)=}")

    print("\nExample 3: stdin from a local file")
    with NamedTemporaryFile(mode="w", suffix=".txt") as input_file:
        input_file.write("apple\nbanana\ncherry\ndate\nfig\n")
        input_file.flush()

        result = session.run(shell="cat | grep 'a' | sort", stdin=Path(input_file.name))
        print(f"Filter and sort result: {stdout_text(result)=}, {exit_code(result)=}")

    print("\nExample 4: Multiple files working together")
    result = session.run(
        shell="chmod +x /script.sh && sh /script.sh",
        files={
            "/data.txt": b"apple\nbanana\ncherry\ndate\n",
            "/script.sh": b"#!/bin/sh\necho 'Processing data:'\ngrep -E '^[ab]' /data.txt\n",
        },
    )
    print(f"Multiple files result: {stdout_text(result)=}, {exit_code(result)=}")


if __name__ == "__main__":
    main(client=ContreeClient.from_profile())
