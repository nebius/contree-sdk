from dataclasses import dataclass


@dataclass
class RegistryCredentials:
    username: str
    password: str


@dataclass
class PublicRegistryInfo:
    url: str


@dataclass
class PrivateRegistryInfo(PublicRegistryInfo):
    credentials: RegistryCredentials


@dataclass
class ImageImportRequest:
    registry: PublicRegistryInfo | PrivateRegistryInfo
    tag: str | None = None
    timeout: int | None = None
