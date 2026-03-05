from contree_sdk import Contree, ContreeSync
from contree_sdk.utils.models.auth import WhoAmI


async def test_whoami(contree: Contree):
    info = await contree.get_token_info()
    assert isinstance(info, WhoAmI)
    assert info.token_uuid
    assert info.limits
    assert info.permissions


def test_whoami_sync(contree_s: ContreeSync):
    info = contree_s.get_token_info()
    assert isinstance(info, WhoAmI)
    assert info.token_uuid
    assert info.limits
    assert info.permissions
