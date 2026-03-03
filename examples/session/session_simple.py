from asyncio import run

from contree_sdk import Contree


async def main(client: Contree):
    image = await client.images.use("busybox:latest")
    print(f"Using {image=}")

    print("\nExample 1: Create session from image")
    session = image.session()
    print(f"Created session: {session=}")

    result1 = await session.run(shell="echo 'First command' > /tmp/data.txt", disposable=False)
    print(f"First run: {result1.stdout=}, {result1.exit_code=}")

    result2 = await session.run(shell="cat /tmp/data.txt", disposable=False)
    print(f"Read file: {result2.stdout=}, {result2.exit_code=}")

    print("\nExample 2: Session maintains state between runs")
    result3 = await session.run(shell="echo 'Second line' >> /tmp/data.txt", disposable=False)
    print(f"Append to file: {result3.exit_code=}")

    result4 = await session.run(shell="cat /tmp/data.txt", disposable=False)
    print(f"File now contains: {result4.stdout=}")

    print("\nExample 3: Session from previous run result")
    run_result = await image.run(shell="echo 'Base setup' > /tmp/base.txt", disposable=False)
    print(f"Base run: {run_result.uuid=}")

    session_from_result = run_result.session()
    result7 = await session_from_result.run(shell="cat /tmp/base.txt", disposable=False)
    print(f"Session from result: {result7.stdout=}")

    await session_from_result.run(shell="echo 'Additional data' >> /tmp/base.txt", disposable=False)
    await session_from_result.run(shell="cat /tmp/base.txt", disposable=False)
    print(f"Modified in session: {session_from_result.stdout=}")


if __name__ == "__main__":
    run(
        main(
            client=Contree(),
        )
    )
