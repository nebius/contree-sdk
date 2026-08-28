from pathlib import PurePosixPath

import pytest

from contree_sdk.utils.models.file import UploadFileSpec


def test_prepare_files_bytes_source_in_dict():
    specs = UploadFileSpec.prepare_files({"/a.txt": b"data"})

    assert len(specs) == 1
    assert specs[0].path == PurePosixPath("/a.txt")
    assert specs[0].source == b"data"


def test_prepare_files_bytes_source_without_path_raises():
    files: list = [b"data"]
    with pytest.raises(ValueError, match="must have a path"):
        UploadFileSpec.prepare_files(files)


def test_prepare_files_bytes_spec_without_path_raises():
    with pytest.raises(ValueError, match="no information about path"):
        UploadFileSpec.prepare_files([UploadFileSpec(source=b"data")])
