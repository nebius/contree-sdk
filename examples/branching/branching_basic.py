from asyncio import run

from contree_sdk import Contree


async def main(client: Contree):
    image = client.images.use("alpine:latest")
    print(f"Using {image=}")

    print("\nExample 1: Different commands from same image")
    result1 = await image.run(shell="echo 'First branch'", disposable=False)
    result2 = await image.run(shell="echo 'Second branch'", disposable=False)
    result3 = await image.run(shell="ls /bin | head -3", disposable=False)

    print(f"Branch 1: {result1.stdout=}, {result1.uuid=}")
    print(f"Branch 2: {result2.stdout=}, {result2.uuid=}")
    print(f"Branch 3: {result3.stdout=}, {result3.uuid=}")

    print("\nExample 2: Random output command (different each time)")
    random1 = await image.run(shell="od -An -N2 -tu2 /dev/urandom", disposable=False)
    random2 = await image.run(shell="od -An -N2 -tu2 /dev/urandom", disposable=False)

    print(f"Random 1: {random1.stdout=}, {random1.uuid=}")
    print(f"Random 2: {random2.stdout=}, {random2.uuid=}")

    print("\nExample 3: Chain of operations from different branches")
    base_result = await image.run(shell="echo 'apple\nbanana\ncherry' > /tmp/fruits.txt", disposable=False)

    sort_result = await base_result.run(shell="sort /tmp/fruits.txt", disposable=False)
    reverse_result = await base_result.run(shell="sort -r /tmp/fruits.txt", disposable=False)

    print(f"Base: {base_result.uuid=}")
    print(f"Sorted: {sort_result.stdout=}, {sort_result.uuid=}")
    print(f"Reverse sorted: {reverse_result.stdout=}, {reverse_result.uuid=}")

    print("\nExample 4: Same command twice - same UUID")
    same1 = await image.run(shell="echo 'Same command'", disposable=False)
    same2 = await image.run(shell="echo 'Same command'", disposable=False)

    print(f"Same 1: {same1.stdout=}, {same1.uuid=}")
    print(f"Same 2: {same2.stdout=}, {same2.uuid=}")
    print(f"UUIDs equal: {same1.uuid == same2.uuid}")


if __name__ == "__main__":
    run(
        main(
            client=Contree(),
        )
    )
