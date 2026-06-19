from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import click
import yaml
from ty import find_ty_bin


BASELINE_PATH = Path(".ty/baseline.yaml")
ERROR_SEVERITY = "major"
_UPDATE_CMD = "make type-check-ignore"


def normalize_path(path: str) -> str:
    return Path(path).as_posix()


@dataclass(frozen=True)
class Diagnostic:
    path: str
    rule: str
    line: int
    col: int
    description: str
    severity: str

    @classmethod
    def parse(cls, raw: dict) -> Diagnostic:
        begin = raw["location"]["positions"]["begin"]
        return cls(
            path=normalize_path(raw["location"]["path"]),
            rule=raw["check_name"],
            line=begin["line"],
            col=begin["column"],
            description=raw["description"].split(": ", 1)[-1],
            severity=raw["severity"],
        )

    def format(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: error[{self.rule}] {self.description}"


Counts: TypeAlias = dict[str, dict[str, int]]
Grouped: TypeAlias = dict[tuple[str, str], list[Diagnostic]]


class NormalizedPath(click.ParamType):
    name = "PATH"

    def convert(self, value: str, param, ctx) -> str:  # noqa: ANN001, PLR6301
        return normalize_path(value)


NORM_PATH = NormalizedPath()


@dataclass
class Regression:
    path: str
    rule: str
    was: int
    now: int
    items: list[Diagnostic]


@dataclass
class Improvement:
    path: str
    rule: str
    was: int
    now: int


def run_ty(*paths: str, config_file: str | None = None) -> list[Diagnostic]:
    config_args = ["--config-file", config_file] if config_file else []
    result = subprocess.run(  # noqa: S603
        [
            find_ty_bin(),
            "check",
            *config_args,
            "--force-exclude",
            "--no-respect-ignore-files",
            "--output-format",
            "gitlab",
            *paths,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode not in {0, 1}:
        raise click.ClickException(f"ty failed (exit {result.returncode}):\n{result.stderr}")
    raw = json.loads(result.stdout) if result.stdout.strip() else []
    return [Diagnostic.parse(entry) for entry in raw]


def is_under(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(Path(path).is_relative_to(prefix) for prefix in prefixes)


def fetch_errors(paths: tuple[str, ...], config_file: str | None = None) -> list[Diagnostic]:
    diagnostics = run_ty(*paths, config_file=config_file)
    errors = [diag for diag in diagnostics if diag.severity == ERROR_SEVERITY]
    if not paths:
        return errors
    return [diag for diag in errors if is_under(diag.path, paths)]


def analyze(diagnostics: list[Diagnostic]) -> tuple[Counts, Grouped]:
    counts: Counts = defaultdict(lambda: defaultdict(int))
    grouped: Grouped = defaultdict(list)
    for diag in diagnostics:
        counts[diag.path][diag.rule] += 1
        grouped[diag.path, diag.rule].append(diag)
    return (
        {path: dict(sorted(rule_counts.items())) for path, rule_counts in sorted(counts.items())},
        dict(grouped),
    )


def total(counts: Counts) -> int:
    return sum(sum(rule_counts.values()) for rule_counts in counts.values())


def get_count(counts: Counts, path: str, rule: str) -> int:
    return counts.get(path, {}).get(rule, 0)


def filter_baseline(baseline: Counts, paths: tuple[str, ...]) -> Counts:
    if not paths:
        return baseline
    return {path: rule_counts for path, rule_counts in baseline.items() if is_under(path, paths)}


def load_baseline(path: Path = BASELINE_PATH) -> Counts:
    if not path.exists():
        raise click.ClickException(f"Baseline not found: {path}. Run `{_UPDATE_CMD}` to create it.")
    data = yaml.safe_load(path.read_text()) or {}
    return {normalize_path(p): rule_counts for p, rule_counts in data.items()}


def save_baseline(counts: Counts, path: Path = BASELINE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(counts, default_flow_style=False, allow_unicode=True))


def diff(scoped: Counts, current: Counts, grouped: Grouped) -> tuple[list[Regression], list[Improvement]]:
    all_keys = {
        (path, rule) for counts in (scoped, current) for path, rule_counts in counts.items() for rule in rule_counts
    }
    regressions: list[Regression] = []
    improvements: list[Improvement] = []
    for path, rule in all_keys:
        was = get_count(scoped, path, rule)
        now = get_count(current, path, rule)
        if now > was:
            regressions.append(Regression(path, rule, was, now, grouped.get((path, rule), [])))
        elif now < was:
            improvements.append(Improvement(path, rule, was, now))
    return regressions, improvements


@click.group()
@click.option("--config-file", "config_file", default=None, type=click.Path(), help="ty config file to use")
@click.option("--baseline-path", "baseline_path", default=None, type=click.Path(), help="path to baseline YAML file")
@click.pass_context
def cli(ctx: click.Context, config_file: str | None, baseline_path: str | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config_file
    ctx.obj["baseline_path"] = Path(baseline_path) if baseline_path else BASELINE_PATH


@cli.command()
@click.argument("paths", nargs=-1, type=NORM_PATH)
@click.pass_context
def check(ctx: click.Context, paths: tuple[str, ...]) -> None:
    """Run ty and report regressions beyond baseline.

    Raises:
        SystemExit: if regressions are found.

    """
    config_file = ctx.obj["config_file"]
    baseline_path = ctx.obj["baseline_path"]
    scoped = filter_baseline(load_baseline(baseline_path), paths)
    current, grouped = analyze(fetch_errors(paths, config_file=config_file))
    regressions, improvements = diff(scoped, current, grouped)

    if not regressions:
        if improvements:
            fixed = sum(imp.was - imp.now for imp in improvements)
            click.echo(f"{fixed} error(s) fixed since baseline. Run `{_UPDATE_CMD}` to record the progress.")
        return

    for reg in sorted(regressions, key=lambda regression: (regression.path, regression.rule)):
        click.echo(f"\n{reg.path}: {reg.rule}: {reg.was} → {reg.now} (+{reg.now - reg.was})")
        for diag in sorted(reg.items, key=lambda diagnostic: diagnostic.line):
            click.echo(f"  {diag.format()}")

    new_errors = sum(reg.now - reg.was for reg in regressions)
    click.echo(f"\nFound {new_errors} new error(s). Fix the excess errors or run `{_UPDATE_CMD}` to accept them.")
    raise SystemExit(1)


@cli.command()
@click.argument("paths", nargs=-1, type=NORM_PATH)
@click.pass_context
def update(ctx: click.Context, paths: tuple[str, ...]) -> None:
    """Regenerate baseline. With PATHS, updates only those entries."""
    config_file = ctx.obj["config_file"]
    baseline_path = ctx.obj["baseline_path"]
    click.echo("Running ty check...")
    current, _ = analyze(fetch_errors(paths, config_file=config_file))
    old_baseline = load_baseline(baseline_path) if baseline_path.exists() else {}

    if paths:
        retained = {p: rule_counts for p, rule_counts in old_baseline.items() if not is_under(p, paths)}
        counts = dict(sorted({**retained, **current}.items()))
    else:
        counts = current

    old_total = total(filter_baseline(old_baseline, paths))
    new_total = total(current)
    save_baseline(counts, baseline_path)
    scope = f"{len(paths)} path(s)" if paths else f"{len(counts)} files"
    click.echo(
        f"Baseline updated: {old_total} → {new_total} ({new_total - old_total:+d}) across {scope} → {baseline_path}"
    )


@cli.command()
@click.argument("paths", nargs=-1, type=NORM_PATH)
@click.pass_context
def stats(ctx: click.Context, paths: tuple[str, ...]) -> None:
    """Show error counts per rule vs baseline."""
    config_file = ctx.obj["config_file"]
    baseline_path = ctx.obj["baseline_path"]
    baseline = filter_baseline(load_baseline(baseline_path) if baseline_path.exists() else {}, paths)
    click.echo("Running ty check...")
    current, _ = analyze(fetch_errors(paths, config_file=config_file))

    baseline_total = total(baseline)
    current_total = total(current)
    click.echo(f"Baseline: {baseline_total}  Current: {current_total}  Delta: {current_total - baseline_total:+d}\n")

    all_rules = {rule for counts in (current, baseline) for rule_counts in counts.values() for rule in rule_counts}
    rule_stats = sorted(
        (
            (
                rule,
                sum(rc.get(rule, 0) for rc in baseline.values()),
                sum(rc.get(rule, 0) for rc in current.values()),
            )
            for rule in all_rules
        ),
        key=lambda row: -row[2],
    )

    click.echo(f"{'Rule':<45} {'Baseline':>8} {'Current':>8} {'Delta':>8}")
    click.echo("-" * 73)
    for rule, base_count, cur_count in rule_stats:
        delta = cur_count - base_count
        marker = " !" if delta > 0 else (" ↓" if delta < 0 else "")
        click.echo(f"{rule:<45} {base_count:>8} {cur_count:>8} {delta:>+8}{marker}")


if __name__ == "__main__":
    cli()
