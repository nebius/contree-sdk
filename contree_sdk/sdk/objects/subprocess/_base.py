from __future__ import annotations

from typing import TYPE_CHECKING

from contree_sdk.sdk.io.typing import INPUT_TYPES, OUTPUT_TYPES


if TYPE_CHECKING:
    from contree_sdk.sdk.objects.image_like._base import ImageLikeBase


class ContreeProcessBase:
    def __init__(self, image: ImageLikeBase, check: bool):
        self.image = image
        self.check = check

    @property
    def stdin(self) -> INPUT_TYPES | None:
        return self.image.stdin

    @property
    def stdout(self) -> OUTPUT_TYPES | None:
        return self.image.stdout

    @property
    def stderr(self) -> OUTPUT_TYPES | None:
        return self.image.stderr

    @property
    def returncode(self) -> int:
        return self.image.exit_code

    def __repr__(self):
        return f"{type(self).__name__}(image={self.image!r})"

    # todo to implement
    # __aenter__
    # __aexit__

    # __repr__
    # kill
    # pid
    # send_signal
    # stdin
    # terminate

    # __enter__
    # __exit__
    # __del__
    # communicate
    # kill
    # pid
    # poll
    # send_signal
    # terminate
