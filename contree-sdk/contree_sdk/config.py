from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace


logger = logging.getLogger(__name__)


@dataclass
class ContreeConfig:
    """Authentication token or env var name."""

    base_url: str = field(default="CONTREE_BASE_URL")
    token: str = field(default="CONTREE_TOKEN", repr=False)

    transport_timeout: float = 10.0
    file_upload_chunk_size: int = 1024 * 1024

    operation_timeout: float = 600.0
    operation_poll_secs_min: float = 0.1
    operation_poll_secs_max: float = 10.0
    operation_poll_secs_backoff_grow: float = 1.75
    # the more value is, the faster backoff grows, better to be between 1 and 2

    images_list_batch_size: int = 100

    images_relations_registry_size: int = 1000

    def _load_field_from_env(self, field_name: str) -> ContreeConfig:
        value = getattr(self, field_name)
        if value in os.environ:
            logger.info(f"Loading {field_name} from environment variable {value}")
            return replace(self, **{field_name: os.environ[value]})
        return self
