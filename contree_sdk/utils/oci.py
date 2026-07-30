from __future__ import annotations

from dataclasses import dataclass
from posixpath import join
from urllib.parse import urlparse, urlunparse


DOCKER_IO = "docker.io"
DOCKER_SCHEMA = "docker"
DOCKER_NAMESPACE = "library"

__all__ = ["OCIReference"]


@dataclass(frozen=True)
class OCIReference:
    url: str
    tag: str

    @classmethod
    def from_oci(cls, ref: str) -> OCIReference:
        reference = str(ref)

        if reference.startswith(":") or not reference:
            raise ValueError(f"{reference!r} is not a valid OCI reference")

        if "://" not in reference:
            reference = f"{DOCKER_SCHEMA}://{reference}"

        parsed = urlparse(reference)
        if parsed.scheme != DOCKER_SCHEMA:
            raise ValueError(f"Invalid scheme: {reference}")
        if not parsed.path:
            parsed = urlparse(reference.replace("://", ":///"))

        host, path = parsed.netloc, parsed.path.lstrip("/")
        if "." not in host:
            path = join(host, path)
            host = ""
        path = path.lstrip("/")

        host = host or DOCKER_IO
        if host == DOCKER_IO:
            if "/" not in path:
                path = join(DOCKER_NAMESPACE, path)
            tag = path.removeprefix(f"{DOCKER_NAMESPACE}/")
        else:
            tag = join(host, path)
        return cls(url=urlunparse((parsed.scheme, host, path, "", "", "")), tag=tag.lstrip("/"))
