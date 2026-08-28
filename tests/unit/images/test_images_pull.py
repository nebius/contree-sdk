from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from contree_client.models import Image

from contree_sdk import Contree


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
        patch.object(fake_contree._api, "inspect_find_image_by_tag", new_callable=AsyncMock) as get_by_tag_mock,
        patch.object(fake_contree._api, "inspect_image", new_callable=AsyncMock) as get_by_uuid_mock,
        patch.object(fake_contree.images, "_import_image", new_callable=AsyncMock) as import_mock,
    ):
        get_by_tag_mock.return_value = "12345678-1234-5678-9012-123456789012"
        get_by_uuid_mock.return_value = Image(tag="uuid-tag", uuid="12345678-1234-5678-9012-123456789012")
        import_mock.return_value = Image(tag="import-tag", uuid="12345678-1234-5678-9012-123456789012")

        res = await fake_contree.images.pull(input_value)
        expected_tags = {"tag": str(input_value), "uuid": "uuid-tag", "import": "import-tag"}
        assert res.tag == expected_tags[method]

        expected_calls = {"tag": get_by_tag_mock, "uuid": get_by_uuid_mock, "import": import_mock}
        assert_called = expected_calls.pop(method)
        assert_called.assert_called_once()
        for not_called in expected_calls.values():
            not_called.assert_not_called()
