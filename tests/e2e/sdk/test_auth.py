from contree_client.models import WhoAmIResponse

from contree_sdk import Contree, ContreeSync


async def test_whoami(contree: Contree):
    info = await contree.api.whoami()
    assert isinstance(info, WhoAmIResponse)
    assert info.token_uuid
    assert info.limits
    assert info.permissions


def test_whoami_sync(contree_s: ContreeSync):
    info = contree_s.api.whoami()
    assert isinstance(info, WhoAmIResponse)
    assert info.token_uuid
    assert info.limits
    assert info.permissions
