"""Bind cache namespaces to a server and an authorization context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from contree_client.types import ContreeAsyncClient, ContreeSyncClient


@dataclass(frozen=True)
class StoreScope:
    """A non-secret digest separating endpoint, project, credential, and profile."""

    digest: str

    @classmethod
    def from_client(cls, client: ContreeSyncClient | ContreeAsyncClient, *, profile: str = "") -> StoreScope:
        """Derive a scope without storing credentials in cache keys or records.

        Returns:
            A scope that changes when endpoint, project, credential, or profile changes.

        """
        parts = [client.base_url.rstrip("/"), client.project, client.token, profile]
        return cls(hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest())

    def namespace(self, name: str) -> str:
        return json.dumps(["contree-sdk", self.digest, name], separators=(",", ":"))
