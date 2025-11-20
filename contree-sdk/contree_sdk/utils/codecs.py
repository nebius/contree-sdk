from collections.abc import Callable
from functools import partial

from contree_sdk.api.models.instance import StreamDescription
from contree_sdk.utils.objects.stream import StreamEncoding


def _decode_base64(value: str) -> str:
    import base64

    return base64.b64decode(value).decode("utf-8")


_DECODERS: dict[str, Callable[[str], str]] = {
    "base64": _decode_base64,
    "ascii": str,
}


def _fallback_decoder(value: str, encoding: str) -> str:
    return value.encode("latin-1").decode(encoding)


def io_decode(value: str, encoding: str, truncated: bool) -> str:
    # todo use truncated
    encoding = encoding.lower()
    decoder = _DECODERS.get(encoding, partial(_fallback_decoder, encoding=encoding))
    return decoder(value)


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


# todo move codecs inside stream object
