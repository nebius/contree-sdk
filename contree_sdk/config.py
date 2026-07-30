from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from contree_sdk._internals.client.transport import SyncTransportMode, TransportName
from contree_sdk.auth import IAMAuth, JWTAuth


logger = logging.getLogger(__name__)


@dataclass
class ContreeConfig:
    """Configuration for the ConTree SDK client.

    The ``auth`` field controls authentication and the target URL. String fields
    on auth objects support env var lookup: if the value matches an existing
    environment variable name, the value is loaded from it.
    """

    auth: IAMAuth | JWTAuth = field(default_factory=IAMAuth)
    """Authentication configuration. Use ``IAMAuth`` for Nebius IAM tokens or ``JWTAuth`` for legacy tokens."""

    transport_timeout: float = 10.0
    """HTTP timeout in seconds."""

    transport: TransportName = "auto"
    """HTTP backend: a contree-client backend name or "auto" for autodetection."""

    sync_transport_mode: SyncTransportMode | None = None
    """How synchronous HTTP backends are driven: "thread" offloads blocking calls
    to worker threads, "blocking" runs them directly on the event loop. Defaults
    to "blocking" for ``ContreeSync`` and "thread" for ``Contree``."""

    file_upload_chunk_size: int = 1024 * 1024
    """Chunk size in bytes for uploads."""

    operation_import_timeout: float | None = None
    """Import operation timeout, falls back to operation_timeout."""
    operation_run_timeout: float | None = None
    """Run operation timeout, falls back to operation_timeout."""
    operation_timeout: float = 1000.0
    """Default timeout for operations."""

    default_truncate_output_at: int = 65535
    """Default truncate output at which to truncate stdout and stderr."""

    token_expiration_warning_threshold: timedelta = field(default_factory=lambda: timedelta(hours=24))
    """Warn if token expires within this duration."""

    images_list_batch_size: int = 100
    """Batch size for listing images."""
