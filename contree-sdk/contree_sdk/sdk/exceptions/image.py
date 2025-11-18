from contree_sdk.sdk.exceptions.base import ContreeException


class ContreeImageNotFound(ContreeException):
    def __init__(self, image: str):
        self.image = image
        super().__init__(f"Image '{image}' not found")


class ContreeImageParametersError(ContreeException): ...


class ContreeImageEmptyRequestError(ContreeException): ...
