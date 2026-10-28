"""Values shared by synchronous and asynchronous stdin forwarding."""

from collections.abc import Iterator
from dataclasses import dataclass


DEFAULT_STDIN_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class StdinResult:
    """Acknowledged input bytes and whether EOF was sent or the process ended.

    A successful write does not prove that the remote process read the bytes.
    An ambiguous transport error raises instead of returning a partial result.
    """

    bytes_sent: int = 0
    eof_sent: bool = False
    process_exited: bool = False


def stdin_chunks(data: str | bytes, chunk_size: int) -> Iterator[bytes]:
    """Split input without allocating an encoded copy of the complete string.

    Yields:
        Byte chunks of at most chunk_size bytes.

    Raises:
        TypeError: A source chunk is neither str nor bytes.

    """
    if not isinstance(data, (str, bytes)):
        raise TypeError("stdin chunks must be str or bytes")
    for offset in range(0, len(data), chunk_size):
        part = data[offset : offset + chunk_size]
        encoded = part.encode() if isinstance(part, str) else part
        for start in range(0, len(encoded), chunk_size):
            yield encoded[start : start + chunk_size]
