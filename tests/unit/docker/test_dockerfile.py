import pytest

from contree_sdk.docker import (
    AddKeyword,
    ArgKeyword,
    CopyKeyword,
    EnvKeyword,
    FromKeyword,
    RunKeyword,
    SkippedKeyword,
    UserKeyword,
    WorkdirKeyword,
    parse_dockerfile,
    substitute,
)


class TestSubstitute:
    def test_dollar_var(self):
        assert substitute("$FOO", {"FOO": "bar"}) == "bar"

    def test_braces(self):
        assert substitute("${FOO}_baz", {"FOO": "bar"}) == "bar_baz"

    def test_missing_var_becomes_empty(self):
        assert substitute("$NOPE/path", {}) == "/path"

    def test_keeps_literal_dollar_without_name(self):
        assert substitute("price: $", {}) == "price: $"

    def test_multiple_substitutions(self):
        env = {"A": "x", "B": "y"}
        assert substitute("$A-${B}-$A", env) == "x-y-x"


class TestParseFrom:
    def test_bare(self):
        d = parse_dockerfile("FROM ubuntu:latest")
        assert d == [FromKeyword(image_ref="ubuntu:latest", alias="")]

    def test_with_alias(self):
        d = parse_dockerfile("FROM ubuntu:latest AS base")
        assert d == [FromKeyword(image_ref="ubuntu:latest", alias="base")]

    def test_lowercase_keyword(self):
        d = parse_dockerfile("from alpine")
        assert d == [FromKeyword(image_ref="alpine", alias="")]

    def test_invalid_syntax(self):
        with pytest.raises(ValueError):
            parse_dockerfile("FROM a b c")


class TestParseRun:
    def test_shell_form(self):
        d = parse_dockerfile("RUN apt-get update && apt-get install -y curl")
        assert d == [RunKeyword(parts=("apt-get update && apt-get install -y curl",), shell_form=True)]

    def test_exec_form(self):
        d = parse_dockerfile('RUN ["echo", "hi"]')
        assert d == [RunKeyword(parts=("echo", "hi"), shell_form=False)]

    def test_invalid_exec_form(self):
        with pytest.raises(ValueError):
            parse_dockerfile("RUN [not json]")


class TestParseCopyAndAdd:
    def test_simple(self):
        d = parse_dockerfile("COPY ./app /app")
        assert d == [CopyKeyword(sources=("./app",), dest="/app", chown="", chmod="", from_stage="")]

    def test_chown_and_chmod(self):
        d = parse_dockerfile("COPY --chown=1000:1000 --chmod=0755 a.py /app.py")
        assert d == [CopyKeyword(sources=("a.py",), dest="/app.py", chown="1000:1000", chmod="0755", from_stage="")]

    def test_add(self):
        d = parse_dockerfile("ADD ./pkg.tar /opt")
        assert d == [AddKeyword(sources=("./pkg.tar",), dest="/opt", chown="", chmod="", from_stage="")]

    def test_multi_source(self):
        d = parse_dockerfile("COPY a b c /dest/")
        assert d == [CopyKeyword(sources=("a", "b", "c"), dest="/dest/", chown="", chmod="", from_stage="")]

    def test_unknown_option(self):
        with pytest.raises(ValueError):
            parse_dockerfile("COPY --weird=1 a /dst")

    def test_missing_dest(self):
        with pytest.raises(ValueError):
            parse_dockerfile("COPY only-one-arg")

    def test_from_stage(self):
        d = parse_dockerfile("COPY --from=builder /out /dst")
        assert d == [CopyKeyword(sources=("/out",), dest="/dst", chown="", chmod="", from_stage="builder")]

    def test_exec_form(self):
        d = parse_dockerfile('COPY ["a", "b", "/dest"]')
        assert d == [CopyKeyword(sources=("a", "b"), dest="/dest", chown="", chmod="", from_stage="")]


class TestParseEnvAndArg:
    def test_env_key_equals_value(self):
        d = parse_dockerfile("ENV FOO=bar BAZ=qux")
        assert d == [EnvKeyword(pairs=(("FOO", "bar"), ("BAZ", "qux")))]

    def test_env_legacy_form(self):
        d = parse_dockerfile("ENV NAME hello world")
        assert d == [EnvKeyword(pairs=(("NAME", "hello world"),))]

    def test_arg_with_default(self):
        d = parse_dockerfile("ARG VERSION=1.0")
        assert d == [ArgKeyword(name="VERSION", default="1.0")]

    def test_arg_no_default(self):
        d = parse_dockerfile("ARG TOKEN")
        assert d == [ArgKeyword(name="TOKEN", default=None)]


class TestParseWorkdirUser:
    def test_workdir(self):
        d = parse_dockerfile("WORKDIR /app")
        assert d == [WorkdirKeyword(path="/app")]

    def test_user(self):
        d = parse_dockerfile("USER nobody")
        assert d == [UserKeyword(spec="nobody")]


class TestSkipped:
    @pytest.mark.parametrize(
        "kw",
        [
            "CMD",
            "ENTRYPOINT",
            "LABEL",
            "EXPOSE",
            "VOLUME",
            "STOPSIGNAL",
            "MAINTAINER",
            "HEALTHCHECK",
            "ONBUILD",
            "SHELL",
        ],
    )
    def test_recognised_but_skipped(self, kw):
        d = parse_dockerfile(f"{kw} whatever args")
        assert isinstance(d[0], SkippedKeyword)
        assert d[0].name == kw

    def test_unknown_keyword_errors(self):
        with pytest.raises(ValueError, match="unknown"):
            parse_dockerfile("BANANARAMA hi")


class TestCommentsAndContinuations:
    def test_comments_skipped(self):
        d = parse_dockerfile("# header\nFROM alpine\n# trailing comment\nRUN echo hi\n")
        assert len(d) == 2

    def test_blank_lines_skipped(self):
        d = parse_dockerfile("\n\nFROM alpine\n\n\nRUN echo\n\n")
        assert len(d) == 2

    def test_line_continuation_joins(self):
        d = parse_dockerfile("RUN apt-get update && \\\n  apt-get install -y \\\n  curl")
        run = d[0]
        assert isinstance(run, RunKeyword)
        assert "apt-get update" in run.parts[0]
        assert "install -y" in run.parts[0]
        assert "curl" in run.parts[0]
