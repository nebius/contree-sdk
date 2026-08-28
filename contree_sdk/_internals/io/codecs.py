from collections.abc import Callable

from contree_sdk.utils.models.stream import StreamDescription, StreamEncoding


def _encode_base64(value: bytes) -> str:
    import base64

    return base64.b64encode(value).decode("ascii")


_ENCODERS: dict[str, Callable[[bytes], str]] = {"base64": _encode_base64}


def io_encode(value: str | bytes, encoding: StreamEncoding | str | None = None) -> StreamDescription:
    if isinstance(value, str):
        return StreamDescription(
            value=value,
            encoding=StreamEncoding.ascii,
            truncated=False,
        )
    encoding = encoding or StreamEncoding.base64
    encoder = _ENCODERS[encoding]
    return StreamDescription(
        value=encoder(value),
        encoding=encoding,
        truncated=False,
    )
