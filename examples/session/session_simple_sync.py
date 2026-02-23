from contree_sdk import ContreeSync


def main(client: ContreeSync):
    image = client.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Create session from image")
    session = image.session()
    print(f"Created session: {session=}")

    result1 = session.run(shell="echo 'First command' > /tmp/data.txt", disposable=False).wait()
    print(f"First run: {result1.stdout=}, {result1.exit_code=}")

    result2 = session.run(shell="cat /tmp/data.txt", disposable=False).wait()
    print(f"Read file: {result2.stdout=}, {result2.exit_code=}")

    print("\nExample 2: Session maintains state between runs")
    result3 = session.run(shell="echo 'Second line' >> /tmp/data.txt", disposable=False).wait()
    print(f"Append to file: {result3.exit_code=}")

    result4 = session.run(shell="cat /tmp/data.txt", disposable=False).wait()
    print(f"File now contains: {result4.stdout=}")

    print("\nExample 3: Session from previous run result")
    run_result = image.run(shell="echo 'Base setup' > /tmp/base.txt", disposable=False).wait()
    print(f"Base run: {run_result.uuid=}")

    session_from_result = run_result.session()
    result7 = session_from_result.run(shell="cat /tmp/base.txt", disposable=False).wait()
    print(f"Session from result: {result7.stdout=}")

    session_from_result.run(shell="echo 'Additional data' >> /tmp/base.txt", disposable=False).wait()
    session_from_result.run(shell="cat /tmp/base.txt", disposable=False).wait()
    print(f"Modified in session: {session_from_result.stdout=}")


if __name__ == "__main__":
    main(
        client=ContreeSync(),
    )
