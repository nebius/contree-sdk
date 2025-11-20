from dataclasses import dataclass


@dataclass
class UploadedFile:
    uuid: str
    sha256: str
