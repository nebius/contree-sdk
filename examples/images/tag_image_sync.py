from contree_client.sync import ContreeClient
from contree_client.types import ContreeSyncClient


def main(client: ContreeSyncClient, image_uuid: str):
    client.update_image_tag(image_uuid, "my-custom-tag:v1")
    print(f"Tagged {image_uuid} as my-custom-tag:v1")

    resolved = client.resolve_image("tag:my-custom-tag:v1")
    print(f"Resolves back to: {resolved=}")

    client.delete_image_tag(image_uuid, tag="my-custom-tag:v1")
    print("Tag removed")


if __name__ == "__main__":
    main_client = ContreeClient.from_profile()
    tagged_images = main_client.list_images(tagged=True, limit=1)
    main_image_uuid = tagged_images.images[0].uuid
    if not isinstance(main_image_uuid, str):
        raise TypeError("expected image uuid in list_images response")
    main(client=main_client, image_uuid=main_image_uuid)
