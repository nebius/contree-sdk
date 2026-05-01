import os

from contree_sdk import ContreeSync


def main():
    # Get client
    client = ContreeSync()

    # Get images (to verify that connection works)
    client.images()


if __name__ == "__main__":
    token = os.getenv("NEBIUS_API_KEY")
    if not token:
        os.environ["NEBIUS_API_KEY"] = input("Please enter Nebius IAM token: ")
    main()
