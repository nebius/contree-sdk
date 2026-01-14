from hashlib import sha256
from pathlib import Path

import basedpyright
import pytest
from pytest_examples import CodeExample, find_examples


README_MD_PATH = Path(__file__).parent.parent.parent.parent / "README.md"

TMP_FILES_PATH = Path(__file__).parent / "_tmp"


def test_readme_exists():
    assert README_MD_PATH.is_file()
    assert README_MD_PATH.exists()


_FIXTURE_NAME_PREFIX = "fixture:name:"


@pytest.mark.parametrize("example", find_examples(README_MD_PATH), ids=str)
def test_docstrings(example: CodeExample):
    TMP_FILES_PATH.mkdir(parents=True, exist_ok=True)
    test_name = sha256((example.prefix + str(example.start_line) + str(example.end_line)).encode()).hexdigest()[:8]
    for prefix_part in example.prefix.split(" "):
        if prefix_part.startswith(_FIXTURE_NAME_PREFIX):
            test_name = prefix_part.replace(_FIXTURE_NAME_PREFIX, "").lower().replace(" ", "_")

    filepath = TMP_FILES_PATH / f"{example.path.name}_{test_name}.py"
    filepath.write_text(example.source)
    run_check(filepath)


def run_check(path: Path):
    from nodejs_wheel.executable import node

    result = node([str(Path(basedpyright.__file__).parent / "index.js"), str(path)], return_completed_process=True)
    assert result.returncode == 0


def test_check_can_fail():
    bad_code = 'qwert.q(rq)"('
    filepath = TMP_FILES_PATH / "bad_code.py"
    filepath.write_text(bad_code)
    with pytest.raises(AssertionError):
        run_check(filepath)
