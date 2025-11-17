from contree_sdk.api.client.client import ContreeClient
from contree_sdk.config import ContreeConfig


class _ContreeBase:
    def __init__(self, config: ContreeConfig | None = None, *, token: str | None = None):
        if config is None:
            config = ContreeConfig(
                token=token,
            )
        else:
            assert token is None, "config is not empty, token should not be specifed"

        self._api = self._create_api_client(config)

    def _create_api_client(self, config: ContreeConfig):
        return ContreeClient(token=config.token)
