from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


class ContreeProcessBase:
    def __init__(self, image: _ImageLikeBase):
        self._image = image
        self._res_image: _ImageLikeBase | None = None
        self._executed = False

    @property
    def stdout(self) -> str:
        return self._image.stdout

    @property
    def stderr(self) -> str:
        return self._image.stderr

    @property
    def returncode(self) -> int:
        return self._image.exit_code

    async def _wait(self):
        assert not self._executed
        self._res_image = await self._image._await()

    # todo to implement
    # __aenter__
    # __aexit__
    # __repr__
    # communicate
    # kill
    # pid
    # send_signal
    # stdin
    # terminate
    # wait

    # __repr__
    # __enter__
    # __exit__
    # __del__
    # communicate
    # kill
    # pid
    # poll
    # send_signal
    # stdin
    # terminate
    # wait
