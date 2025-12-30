from asyncio import run

from contree_sdk import Contree


async def main(client: Contree):
    base = await client.images.pull("alpine:latest")

    child = await base.run(shell='echo "$RANDOM" > /tmp/random.txt', disposable=False)
    print(f"Child created from base, UUID: {child.uuid}\n")

    for i, letter in enumerate(["A", "B", "C"], 1):
        gc = await child.run(
            shell=f"echo '{letter}' >> /tmp/random.txt && cat /tmp/random.txt",
            disposable=False,
        )
        print(f"Grandchild {i}: {gc.stdout.strip()}")


if __name__ == "__main__":
    run(main(client=Contree()))
