import json
import sys
from pathlib import Path
from re import findall


if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib  # pyright: ignore[reportMissingImports]
from packaging.specifiers import SpecifierSet
from packaging.version import Version


def supported_python_versions(
    requires_python: str,
) -> list[str]:
    spec = SpecifierSet(requires_python)
    nums = findall(r"\d+", requires_python)
    nums = list(map(int, nums))

    res = []
    for i in range(min(nums), max(nums) + 1):
        ver = Version(f"3.{i}")
        if spec.contains(ver):
            res.append(ver.base_version)

    return res


def pyproject_python_versions(
    pyproject_path: str | Path,
) -> list[str]:
    pyproject_path = Path(pyproject_path)

    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)

    requires_python = pyproject.get("project", {}).get("requires-python")

    if not requires_python:
        raise ValueError("requires-python not found in pyproject.toml")

    return supported_python_versions(requires_python)


if __name__ == "__main__":
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    print(json.dumps(pyproject_python_versions(pyproject)))  # noqa: T201
