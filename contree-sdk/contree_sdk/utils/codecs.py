from collections.abc import Callable
from functools import partial

from contree_sdk._internals.models.instance import StreamDescription
from contree_sdk.utils.models.stream import StreamEncoding


def _decode_base64(value: str) -> bytes:
    import base64

    return base64.b64decode(value)


def _decode_ascii(value: str) -> bytes:
    return value.encode()


_DECODERS: dict[str, Callable[[str], bytes]] = {
    "base64": _decode_base64,
    "ascii": _decode_ascii,
}


def _fallback_decoder(value: str) -> bytes:
    return value.encode("latin-1")


def io_decode(value: StreamDescription) -> bytes:
    # todo use truncated
    encoding = value.encoding.lower()
    decoder = _DECODERS.get(encoding, partial(_fallback_decoder))
    return decoder(value.value)


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
