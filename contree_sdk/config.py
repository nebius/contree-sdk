from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace


logger = logging.getLogger(__name__)


@dataclass
class ContreeConfig:
    """Configuration for the ConTree SDK client.

    Fields ``base_url`` and ``token`` support env var lookup: if the value
    matches an existing environment variable name, the value is loaded from it.
    """

    base_url: str = field(default="CONTREE_BASE_URL")
    """API server URL or env var name to load from."""
    token: str = field(default="CONTREE_TOKEN", repr=False)
    """Auth token or env var name to load from."""

    transport_timeout: float = 10.0
    """HTTP timeout in seconds."""

    file_upload_chunk_size: int = 1024 * 1024
    """Chunk size in bytes for uploads."""

    operation_import_timeout: float | None = None
    """Import operation timeout, falls back to operation_timeout."""
    operation_run_timeout: float | None = None
    """Run operation timeout, falls back to operation_timeout."""
    operation_timeout: float = 600.0
    """Default timeout for operations."""
    operation_poll_secs_min: float = 0.1
    """Min polling interval for operation status checks."""
    operation_poll_secs_max: float = 10.0
    """Max polling interval for operation status checks."""
    operation_poll_secs_backoff_grow: float = 1.75
    """Backoff multiplier between polls. Higher values mean faster backoff growth; recommended range is 1 to 2."""
    operation_poll_not_found_limit: int = 10
    """Maximum number of not found responses when awaiting operation"""

    images_list_batch_size: int = 100
    """Batch size for listing images."""

    def _load_field_from_env(self, field_name: str) -> ContreeConfig:
        value = getattr(self, field_name)
        if value in os.environ:
            logger.info(f"Loading {field_name} from environment variable {value}")
            return replace(self, **{field_name: os.environ[value]})
        return self
