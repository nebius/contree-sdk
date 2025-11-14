from dataclasses import dataclass

from strenum import StrEnum


class ContreeEndpoint(StrEnum):
    PRODUCTION = "https://eu-north.nebius.computer"
    STAGE = "https://eu-north-stage.nebius.computer"


@dataclass
class ContreeConfig:
    token: str
    base_url: ContreeEndpoint | str = ContreeEndpoint.STAGE
