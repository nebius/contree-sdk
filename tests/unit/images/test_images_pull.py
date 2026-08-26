from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from contree_sdk import Contree
from contree_sdk.sdk.objects.image import ContreeImage


@pytest.mark.parametrize(
    ("input_value", "method"),
    [
        ("env-94e7fe25d6cf22df8654492fbf845b4680da0d68bab77a97c3:v0.0.3", "tag"),
        ("12345678-1234-5678-9012-123456789012", "uuid"),
        (UUID("12345678-1234-5678-9012-123456789012"), "uuid"),
        ("https://registry.example.com/image:tag", "import"),
        ("docker://ghcr.io/linuxserver/code-server:latest", "import"),
    ],
)
async def test_pull_routing(fake_contree: Contree, input_value, method):
    with (
        patch.object(fake_contree.images, "get_image_by_tag", new_callable=AsyncMock) as get_by_tag_mock,
        patch.object(fake_contree.images, "get_image_by_uuid", new_callable=AsyncMock) as get_by_uuid_mock,
        patch.object(fake_contree.images, "import_image", new_callable=AsyncMock) as import_mock,
    ):
        uuid_value = UUID("12345678-1234-5678-9012-123456789012")
        get_by_tag_mock.return_value = ContreeImage(client=fake_contree, uuid=uuid_value, tag="tag-tag")
        get_by_uuid_mock.return_value = ContreeImage(client=fake_contree, uuid=uuid_value, tag="uuid-tag")
        import_mock.return_value = ContreeImage(client=fake_contree, uuid=uuid_value, tag="import-tag")

        res = await fake_contree.images.pull_image(input_value)
        assert res.tag == f"{method}-tag"

        expected_calls = {"tag": get_by_tag_mock, "uuid": get_by_uuid_mock, "import": import_mock}
        assert_called = expected_calls.pop(method)
        assert_called.assert_called_once()
        for not_called in expected_calls.values():
            not_called.assert_not_called()
