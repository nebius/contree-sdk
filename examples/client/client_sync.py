import os

from contree_sdk import ContreeSync


def main():
    # Get client
    client = ContreeSync()

    # Get images (to verify that connection works)
    client.images()


if __name__ == "__main__":
    token = os.getenv("CONTREE_TOKEN")
    if not token:
        os.environ["CONTREE_TOKEN"] = input("Please enter contree token: ")
    main()
