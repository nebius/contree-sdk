import os
from random import choices

from contree_sdk import Contree, ContreeSync
from contree_sdk.config import ContreeConfig, ContreeEndpoint


def get_contree_token():
    if not os.getenv("CONTREE_TOKEN"):
        print("CONTREE_TOKEN environment variable not set")
        os.environ["CONTREE_TOKEN"] = input("Please enter contree token: ")
    return os.getenv("CONTREE_TOKEN")


def get_config() -> ContreeConfig:
    return ContreeConfig(
        token=get_contree_token(),
        base_url=ContreeEndpoint.PRODUCTION,
    )


def get_contree():
    return Contree(token=get_contree_token())


def get_contree_sync():
    return ContreeSync(token=get_contree_token())


async def get_image():
    images = await get_contree().images()
    return choices(images)[0]


def get_image_sync():
    images = get_contree_sync().images()
    return choices(images)[0]


def get_image_uuid():
    images = get_contree_sync().images()
    return choices(images)[0].uuid


def get_image_tag():
    images = get_contree_sync().images(tagged=True)
    return choices(images)[0].tag
