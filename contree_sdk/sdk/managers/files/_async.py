from contree_sdk.sdk.managers.files._base import _FilesBaseManager


class FilesManager(_FilesBaseManager):
    upload = _FilesBaseManager._upload_file
