import subprocess
import sys


def test_sdk_import_without_harbor():
    code = """
import importlib.abc
import sys

class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'harbor', 'httpx'}:
            raise ModuleNotFoundError('blocked optional dependency', name=fullname)

sys.meta_path.insert(0, BlockOptional())
import contree_sdk
assert 'harbor' not in sys.modules
assert 'httpx' not in sys.modules
try:
    from contree_sdk.harbor import ConTreeEnvironment
except ImportError as exc:
    expected = 'Python 3.12' if sys.version_info < (3, 12) else 'contree-sdk[harbor]'
    assert expected in str(exc), str(exc)
else:
    raise AssertionError('Missing extra should produce an actionable ImportError')
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, result.stderr
