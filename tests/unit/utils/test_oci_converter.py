from typing import NamedTuple

import pytest
from httpcore import URL

from contree_sdk.utils.oci import OCIReference


class DockerImageTestCase(NamedTuple):
    input: str
    url: str
    tag: str


@pytest.mark.parametrize(
    "test_case",
    [
        DockerImageTestCase("docker:///python", "docker://docker.io/library/python", "python"),
        DockerImageTestCase(
            "docker:///python:3.12-slim", "docker://docker.io/library/python:3.12-slim", "python:3.12-slim"
        ),
        DockerImageTestCase("python", "docker://docker.io/library/python", "python"),
        DockerImageTestCase("python:3.12-slim", "docker://docker.io/library/python:3.12-slim", "python:3.12-slim"),
        DockerImageTestCase(
            "vpupkin/myimage:v1.0", "docker://docker.io/library/vpupkin/myimage:v1.0", "vpupkin/myimage:v1.0"
        ),
        DockerImageTestCase(
            "docker://docker.io/something/python:3.12-slim",
            "docker://docker.io/library/something/python:3.12-slim",
            "something/python:3.12-slim",
        ),
        DockerImageTestCase("docker://quay.io/python", "docker://quay.io/python", "quay.io/python"),
        DockerImageTestCase(
            "docker://quay.io/prometheus/prometheus:v2.45.0",
            "docker://quay.io/prometheus/prometheus:v2.45.0",
            "quay.io/prometheus/prometheus:v2.45.0",
        ),
        DockerImageTestCase(
            "docker://some.io/library/python:3.12-slim",
            "docker://some.io/library/python:3.12-slim",
            "some.io/library/python:3.12-slim",
        ),
        DockerImageTestCase(
            "docker://registry.example.com:5000/team/myapp:v1.2.3",
            "docker://registry.example.com:5000/team/myapp:v1.2.3",
            "registry.example.com:5000/team/myapp:v1.2.3",
        ),
        DockerImageTestCase("quay.io/python:3.12", "docker://quay.io/python:3.12", "quay.io/python:3.12"),
        DockerImageTestCase("gcr.io/project/image", "docker://gcr.io/project/image", "gcr.io/project/image"),
    ],
    ids=lambda tc: tc.input,
)
def test_docker_url_canonize_and_decanonize(test_case):
    ref = OCIReference.from_oci(test_case.input)
    assert ref.url == URL(test_case.url)

    assert ref.tag == test_case.tag


@pytest.mark.parametrize("invalid_input", ["", ":", ":tag", "nodocker://url"])
def test_docker_url_canonize_errors(invalid_input):
    with pytest.raises(ValueError):
        OCIReference.from_oci(invalid_input)
