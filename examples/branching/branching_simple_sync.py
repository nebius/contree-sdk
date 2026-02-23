from contree_sdk import ContreeSync


def main(client: ContreeSync):
    base = client.images.use("alpine:latest")

    child = base.run(shell='echo "$RANDOM" > /tmp/random.txt', disposable=False).wait()
    print(f"Child created from base, UUID: {child.uuid}\n")

    for i, letter in enumerate(["A", "B", "C"], 1):
        gc = child.run(
            shell=f"echo '{letter}' >> /tmp/random.txt && cat /tmp/random.txt",
            disposable=False,
        ).wait()
        print(f"Grandchild {i}: {gc.stdout.strip()}")


if __name__ == "__main__":
    main(client=ContreeSync())
