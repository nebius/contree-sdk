from typing import NamedTuple

import pytest

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
        DockerImageTestCase("python:3.12", "docker://docker.io/library/python:3.12", "python:3.12"),
        DockerImageTestCase("vpupkin/myimage:v1.0", "docker://docker.io/vpupkin/myimage:v1.0", "vpupkin/myimage:v1.0"),
        DockerImageTestCase(
            "docker://docker.io/something/python:3.12-slim",
            "docker://docker.io/something/python:3.12-slim",
            "something/python:3.12-slim",
        ),
        DockerImageTestCase(
            "alexgshaw/adaptive-rejection-sampler:20251031",
            "docker://docker.io/alexgshaw/adaptive-rejection-sampler:20251031",
            "alexgshaw/adaptive-rejection-sampler:20251031",
        ),
        DockerImageTestCase("docker.io/user/img:tag", "docker://docker.io/user/img:tag", "user/img:tag"),
        DockerImageTestCase("docker.io/python:3.12", "docker://docker.io/library/python:3.12", "python:3.12"),
        DockerImageTestCase("librarything/img:1", "docker://docker.io/librarything/img:1", "librarything/img:1"),
        DockerImageTestCase(
            "cr.eu-north1.nebius.cloud/org/img:tag",
            "docker://cr.eu-north1.nebius.cloud/org/img:tag",
            "cr.eu-north1.nebius.cloud/org/img:tag",
        ),
        DockerImageTestCase(
            "localhost:5000/img:tag", "docker://docker.io/localhost:5000/img:tag", "localhost:5000/img:tag"
        ),
        DockerImageTestCase("docker.io/library/python:3.12", "docker://docker.io/library/python:3.12", "python:3.12"),
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
    assert ref.url == test_case.url

    assert ref.tag == test_case.tag


@pytest.mark.parametrize("invalid_input", ["", ":", ":tag", "nodocker://url"])
def test_docker_url_canonize_errors(invalid_input):
    with pytest.raises(ValueError):
        OCIReference.from_oci(invalid_input)
