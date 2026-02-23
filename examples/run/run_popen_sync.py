from contree_sdk import ContreeSync


def main(client: ContreeSync):
    image = client.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Basic popen with wait()")
    process = image.popen(["/bin/ls", "-la"], cwd="/bin")
    process.wait()
    print(f"Process completed: returncode={process.returncode}")
    print(f"Output: {process.stdout[:100]}...")

    print("\nExample 2: Shell command with stdout and stderr")
    process = image.popen("echo 'Hello stdout' && echo 'Hello stderr' >&2", shell=True)
    process.wait()
    print(f"Stdout: {process.stdout=}")
    print(f"Stderr: {process.stderr=}")

    print("\nExample 3: Using communicate() for input/output")
    process = image.popen(["/bin/grep", "apple"])
    stdout, stderr = process.communicate(input="apple\nbanana\ncherry\napple pie\n")
    print(f"Grep results: {stdout=}")
    print(f"Return code: {process.returncode=}")

    print("\nExample 4: Environment variables")
    process = image.popen(
        "echo $MY_VAR && echo $ANOTHER_VAR", shell=True, env={"MY_VAR": "hello_world", "ANOTHER_VAR": "test_value"}
    )
    process.wait()
    print(f"Environment output: {process.stdout=}")

    print("\nExample 5: Error handling")
    process = image.popen(["/bin/ls", "/nonexistent"])
    process.wait()
    print(f"Error case: returncode={process.returncode}")
    print(f"Error output: {process.stderr=}")


if __name__ == "__main__":
    main(
        client=ContreeSync(),
    )
