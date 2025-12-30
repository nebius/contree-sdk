import os

from contree_sdk import ContreeSync


def main(token: str):
    # Get client
    client = ContreeSync(token=token)

    # Get images (to verify that connection works)
    client.images()


if __name__ == "__main__":
    token = os.getenv("CONTREE_TOKEN")
    if not token:
        token = input("Please enter contree token: ")
    main(token=token)
