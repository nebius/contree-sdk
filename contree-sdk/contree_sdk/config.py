from dataclasses import dataclass

from strenum import StrEnum


class ContreeEndpoint(StrEnum):
    PRODUCTION = "https://eu-north.nebius.computer"
    STAGE = "https://eu-north-stage.nebius.computer"


@dataclass
class ContreeConfig:
    token: str = "CONTREE_TOKEN"
    base_url: ContreeEndpoint | str = ContreeEndpoint.PRODUCTION

    transport_timeout: float = 10.0
    file_upload_chunk_size: int = 1024 * 1024

    operation_timeout: float = 600.0
    operation_poll_secs_min: float = 0.1
    operation_poll_secs_max: float = 10.0
    operation_poll_secs_backoff_grow: float = 1.75
    # the more value is, the faster backoff grows, better to be between 1 and 2

    images_list_batch_size: int = 100

    images_relations_registry_size: int = 1000
