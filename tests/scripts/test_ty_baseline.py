from __future__ import annotations

import pytest
import scripts.ty_baseline as tb
import yaml
from click.testing import CliRunner
from scripts.ty_baseline import Diagnostic, Improvement, Regression, cli


def make_diag(path: str, rule: str, line: int = 1, severity: str = "major") -> Diagnostic:
    return Diagnostic(path=path, rule=rule, line=line, col=1, description=rule, severity=severity)


@pytest.fixture
def mock_ty(monkeypatch):
    diagnostics: list[Diagnostic] = []
    monkeypatch.setattr(tb, "run_ty", lambda *_, **__: list(diagnostics))
    return diagnostics


@pytest.fixture
def baseline_path(tmp_path, monkeypatch):
    path = tmp_path / "baseline.yaml"
    monkeypatch.setattr(tb, "BASELINE_PATH", path)
    return path


def test_normalize_path():
    assert tb.normalize_path("./papyrax/foo.py") == "papyrax/foo.py"
    assert tb.normalize_path("papyrax/") == "papyrax"


def test_diagnostic_parse():
    raw = {
        "severity": "major",
        "check_name": "unresolved-import",
        "location": {
            "path": "./papyrax/foo.py",
            "positions": {"begin": {"line": 5, "column": 3}},
        },
        "description": "error: Cannot resolve 'foo'",
    }
    diag = Diagnostic.parse(raw)
    assert diag == Diagnostic(
        path="papyrax/foo.py",
        rule="unresolved-import",
        line=5,
        col=3,
        description="Cannot resolve 'foo'",
        severity="major",
    )


def test_diagnostic_parse_no_colon_prefix():
    raw = {
        "severity": "major",
        "check_name": "rule",
        "location": {"path": "f.py", "positions": {"begin": {"line": 1, "column": 1}}},
        "description": "just a message",
    }
    assert Diagnostic.parse(raw).description == "just a message"


def test_diagnostic_format():
    diag = Diagnostic(
        path="a.py",
        rule="unresolved-import",
        line=5,
        col=3,
        description="Cannot resolve 'foo'",
        severity="major",
    )
    assert diag.format() == "a.py:5:3: error[unresolved-import] Cannot resolve 'foo'"


def test_analyze():
    diags = [
        make_diag("z.py", "rule-b"),
        make_diag("a.py", "rule-a"),
        make_diag("a.py", "rule-a"),
        make_diag("a.py", "rule-b"),
    ]
    counts, grouped = tb.analyze(diags)
    assert list(counts.keys()) == ["a.py", "z.py"]
    assert counts["a.py"] == {"rule-a": 2, "rule-b": 1}
    assert list(counts["a.py"].keys()) == ["rule-a", "rule-b"]
    assert len(grouped["a.py", "rule-a"]) == 2


def test_total():
    assert tb.total({"a.py": {"r1": 3, "r2": 2}, "b.py": {"r1": 1}}) == 6
    assert tb.total({}) == 0


def test_get_count():
    counts = {"a.py": {"r": 5}}
    assert tb.get_count(counts, "a.py", "r") == 5
    assert tb.get_count(counts, "a.py", "other") == 0
    assert tb.get_count(counts, "missing.py", "r") == 0


def test_is_under():
    assert tb.is_under("papyrax/foo/bar.py", ("papyrax",))
    assert not tb.is_under("papyrax_extra/foo.py", ("papyrax",))
    assert tb.is_under("swan/bar.py", ("papyrax", "swan"))
    assert not tb.is_under("other/foo.py", ("papyrax", "swan"))
    assert not tb.is_under("papyrax/foo.py", ())


def test_filter_baseline():
    baseline = {
        "papyrax/foo.py": {"r": 1},
        "swan/bar.py": {"r": 2},
        "papyrax_extra/baz.py": {"r": 3},
    }
    assert tb.filter_baseline(baseline, ()) is baseline
    assert tb.filter_baseline(baseline, ("papyrax",)) == {"papyrax/foo.py": {"r": 1}}
    assert tb.filter_baseline(baseline, ("papyrax/foo.py",)) == {"papyrax/foo.py": {"r": 1}}


def test_diff():
    scoped = {"a.py": {"r": 1}, "fixed.py": {"r": 2}}
    current = {"a.py": {"r": 3}, "new.py": {"r": 1}}
    diags = [make_diag("a.py", "r")] * 3 + [make_diag("new.py", "r")]
    _, grouped = tb.analyze(diags)
    regressions, improvements = tb.diff(scoped, current, grouped)
    reg_map = {reg.path: reg for reg in regressions}
    assert reg_map["a.py"] == Regression("a.py", "r", 1, 3, grouped["a.py", "r"])
    assert reg_map["new.py"] == Regression("new.py", "r", 0, 1, grouped["new.py", "r"])
    assert improvements == [Improvement("fixed.py", "r", 2, 0)]


def test_load_baseline_normalizes_dotslash(tmp_path, monkeypatch):
    path = tmp_path / "baseline.yaml"
    path.write_text(yaml.dump({"./papyrax/foo.py": {"rule": 1}}))
    monkeypatch.setattr(tb, "BASELINE_PATH", path)
    data = tb.load_baseline()
    assert "papyrax/foo.py" in data
    assert "./papyrax/foo.py" not in data


def test_save_load_roundtrip(baseline_path):
    counts = {"papyrax/foo.py": {"rule": 2}, "swan/bar.py": {"rule": 1}}
    tb.save_baseline(counts)
    assert tb.load_baseline() == counts


def test_save_baseline_creates_nested_parents(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "dir" / "baseline.yaml"
    monkeypatch.setattr(tb, "BASELINE_PATH", path)
    tb.save_baseline({"a.py": {"r": 1}})
    assert path.exists()


def test_check_no_regressions_no_output(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"a.py": {"rule": 2}}))
    mock_ty += [make_diag("a.py", "rule"), make_diag("a.py", "rule")]
    result = CliRunner().invoke(cli, ["check"])
    assert result.exit_code == 0
    assert result.output == ""


def test_check_improvements_reported(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"a.py": {"rule": 3}}))
    mock_ty.append(make_diag("a.py", "rule"))
    result = CliRunner().invoke(cli, ["check"])
    assert result.exit_code == 0
    assert "2 error(s) fixed" in result.output
    assert tb._UPDATE_CMD in result.output


def test_check_regression_exits_1(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"a.py": {"rule": 1}}))
    mock_ty += [make_diag("a.py", "rule"), make_diag("a.py", "rule")]
    result = CliRunner().invoke(cli, ["check"])
    assert result.exit_code == 1
    assert "1 → 2" in result.output
    assert tb._UPDATE_CMD in result.output


def test_check_regression_items_sorted_by_line(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"a.py": {"rule": 0}}))
    mock_ty += [make_diag("a.py", "rule", line=30), make_diag("a.py", "rule", line=10)]
    result = CliRunner().invoke(cli, ["check"])
    assert result.output.index(":10:") < result.output.index(":30:")


def test_check_warnings_not_counted(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"a.py": {"rule": 1}}))
    mock_ty += [make_diag("a.py", "rule"), make_diag("a.py", "rule", severity="minor")]
    result = CliRunner().invoke(cli, ["check"])
    assert result.exit_code == 0


def test_check_scoped(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"papyrax/foo.py": {"rule": 1}, "swan/bar.py": {"rule": 99}}))
    mock_ty += [
        make_diag("papyrax/foo.py", "rule"),
        make_diag("papyrax/foo.py", "rule"),
        make_diag("other/baz.py", "rule"),
    ]
    result = CliRunner().invoke(cli, ["check", "./papyrax"])
    assert result.exit_code == 1
    assert "swan/bar.py" not in result.output
    assert "other/baz.py" not in result.output


def test_check_scoped_no_regression(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"papyrax/foo.py": {"rule": 1}, "swan/bar.py": {"rule": 99}}))
    mock_ty.append(make_diag("papyrax/foo.py", "rule"))
    result = CliRunner().invoke(cli, ["check", "papyrax"])
    assert result.exit_code == 0


def test_check_missing_baseline(baseline_path):
    result = CliRunner().invoke(cli, ["check"])
    assert result.exit_code != 0


def test_check_multiple_regressions(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"a.py": {"rule": 1}, "b.py": {"rule": 1}}))
    mock_ty += [
        make_diag("a.py", "rule"),
        make_diag("a.py", "rule"),
        make_diag("b.py", "rule"),
        make_diag("b.py", "rule"),
    ]
    result = CliRunner().invoke(cli, ["check"])
    assert result.exit_code == 1
    assert "2 new error(s)" in result.output


def test_update_creates_baseline(mock_ty, baseline_path):
    mock_ty += [make_diag("a.py", "rule"), make_diag("b.py", "other")]
    CliRunner().invoke(cli, ["update"])
    data = yaml.safe_load(baseline_path.read_text())
    assert data == {"a.py": {"rule": 1}, "b.py": {"other": 1}}


def test_update_partial_preserves_other_files(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"papyrax/foo.py": {"rule": 5}, "swan/bar.py": {"rule": 3}}))
    mock_ty.append(make_diag("papyrax/foo.py", "rule"))
    CliRunner().invoke(cli, ["update", "papyrax"])
    data = yaml.safe_load(baseline_path.read_text())
    assert data["papyrax/foo.py"] == {"rule": 1}
    assert data["swan/bar.py"] == {"rule": 3}


def test_update_partial_removes_fixed_file(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"papyrax/foo.py": {"rule": 2}, "swan/bar.py": {"rule": 1}}))
    CliRunner().invoke(cli, ["update", "papyrax"])
    data = yaml.safe_load(baseline_path.read_text())
    assert "papyrax/foo.py" not in data
    assert data["swan/bar.py"] == {"rule": 1}


def test_update_out_of_scope_diagnostics_not_written(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"papyrax/foo.py": {"rule": 1}, "swan/bar.py": {"rule": 1}}))
    mock_ty += [make_diag("papyrax/foo.py", "rule"), make_diag("other/baz.py", "rule")]
    CliRunner().invoke(cli, ["update", "papyrax"])
    data = yaml.safe_load(baseline_path.read_text())
    assert "other/baz.py" not in data


def test_update_reports_delta(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"a.py": {"rule": 3}}))
    mock_ty.append(make_diag("a.py", "rule"))
    result = CliRunner().invoke(cli, ["update"])
    assert "3 → 1" in result.output
    assert "-2" in result.output


def test_stats_shows_rule_table(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"a.py": {"my-rule": 2}}))
    mock_ty.append(make_diag("a.py", "my-rule"))
    result = CliRunner().invoke(cli, ["stats"])
    assert "my-rule" in result.output
    assert " ↓" in result.output
    assert " !" not in result.output


def test_stats_scoped(mock_ty, baseline_path):
    baseline_path.write_text(yaml.dump({"papyrax/foo.py": {"rule": 1}, "swan/bar.py": {"rule": 5}}))
    mock_ty += [make_diag("papyrax/foo.py", "rule"), make_diag("swan/bar.py", "rule")]
    result = CliRunner().invoke(cli, ["stats", "papyrax"])
    assert "Baseline: 1" in result.output
    assert "Current: 1" in result.output


def test_stats_no_baseline_file(mock_ty, baseline_path):
    mock_ty.append(make_diag("a.py", "rule"))
    result = CliRunner().invoke(cli, ["stats"])
    assert result.exit_code == 0
    assert "Baseline: 0" in result.output
