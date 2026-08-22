import re

import pytest

from contree_sdk.docker.dockerignore import is_ignored, parse_dockerignore, pattern_to_regex
from contree_sdk.docker.local_context import LocalContext


# -- pattern_to_regex --


@pytest.mark.parametrize(
    ("pattern", "subject", "expected"),
    [
        ("foo", "foo", True),
        ("foo", "bar", False),
        ("foo", "foo/bar", False),  # bare pattern, no subpath match
        ("foo/", "foo/bar", True),
        ("foo/", "foo", True),  # trailing slash also matches the bare dir name
        ("*.log", "x.log", True),
        ("*.log", "sub/x.log", False),  # * does not cross /
        ("**/*.log", "x.log", True),
        ("**/*.log", "a/x.log", True),
        ("**/*.log", "a/b/x.log", True),
        ("src/**", "src/a/b.c", True),
        ("src/**", "src/a.txt", True),
        ("a/**/b", "a/b", True),
        ("a/**/b", "a/x/b", True),
        ("a/**/b", "a/x/y/b", True),
        ("a?b", "axb", True),
        ("a?b", "ab", False),
        ("file[12]", "file1", True),
        ("file[12]", "file3", False),
    ],
)
def test_pattern_to_regex_matches(pattern, subject, expected):
    regex = pattern_to_regex(pattern)
    assert bool(re.fullmatch(regex, subject)) is expected


# -- parse_dockerignore --


def test_missing_file_returns_empty(tmp_path):
    assert parse_dockerignore(tmp_path) == ()


def test_comments_and_blank_lines_skipped(tmp_path):
    (tmp_path / ".dockerignore").write_text("# header\n\nfoo\n  # indented comment kept as literal? no\n!bar\n")
    rules = parse_dockerignore(tmp_path)
    # "  # indented" is not a comment in Docker; we follow a simple lstrip-then-startswith("#")
    # check, so after strip it becomes "# indented comment..." which IS treated as a comment.
    assert len(rules) == 2
    assert rules[0].raw.strip() == "foo"
    assert rules[1].negate is True


def test_negation_then_match(tmp_path):
    (tmp_path / ".dockerignore").write_text("*.log\n!keep.log\n")
    rules = parse_dockerignore(tmp_path)
    assert is_ignored("x.log", rules) is True
    assert is_ignored("keep.log", rules) is False


def test_match_order_last_wins(tmp_path):
    (tmp_path / ".dockerignore").write_text("!keep.log\n*.log\n")
    rules = parse_dockerignore(tmp_path)
    # *.log comes after !keep.log so keep.log gets re-ignored
    assert is_ignored("keep.log", rules) is True


# LocalContext walk + .dockerignore integration


def test_dockerignore_filters_dir_walk(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("ok")
    (tmp_path / "src" / "ignore.log").write_text("nope")
    (tmp_path / ".dockerignore").write_text("**/*.log\n")

    local = LocalContext.from_dir(tmp_path)
    mapped = local.collect(("src",), "/app", uid=0, gid=0, mode_override=None)
    paths = sorted(m.instance_path for m in mapped)
    assert paths == ["/app/app.py"]


def test_dockerignore_blocks_file_source(tmp_path):
    (tmp_path / "secret.env").write_text("token=hi")
    (tmp_path / ".dockerignore").write_text("*.env\n")

    local = LocalContext.from_dir(tmp_path)
    mapped = local.collect(("secret.env",), "/app.env", uid=0, gid=0, mode_override=None)
    assert mapped == []


def test_default_excludes_still_apply(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    (tmp_path / "app.py").write_text("ok")

    local = LocalContext.from_dir(tmp_path)
    mapped = local.collect((".",), "/app/", uid=0, gid=0, mode_override=None)
    paths = sorted(m.instance_path for m in mapped)
    # .git filtered out by DEFAULT_EXCLUDES
    assert all(".git" not in p for p in paths)
    assert "/app/app.py" in paths


def test_negation_reincludes(tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "keep.log").write_text("k")
    (tmp_path / "logs" / "junk.log").write_text("j")
    (tmp_path / ".dockerignore").write_text("logs/*.log\n!logs/keep.log\n")

    local = LocalContext.from_dir(tmp_path)
    mapped = local.collect(("logs",), "/dest", uid=0, gid=0, mode_override=None)
    paths = sorted(m.instance_path for m in mapped)
    assert paths == ["/dest/keep.log"]


def test_source_escaping_context_raises(tmp_path):
    local = LocalContext.from_dir(tmp_path)
    with pytest.raises(ValueError, match="escapes context"):
        local.collect(("../outside",), "/dst", uid=0, gid=0, mode_override=None)


def test_missing_source_raises(tmp_path):
    local = LocalContext.from_dir(tmp_path)
    with pytest.raises(FileNotFoundError, match="not found"):
        local.collect(("nope.txt",), "/dst", uid=0, gid=0, mode_override=None)


def test_mode_override_applies_to_file(tmp_path):
    (tmp_path / "a.sh").write_text("echo hi")
    local = LocalContext.from_dir(tmp_path)
    mapped = local.collect(("a.sh",), "/a.sh", uid=0, gid=0, mode_override=0o755)
    assert mapped[0].mode == 0o755
