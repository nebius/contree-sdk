import pytest


pytest.importorskip("harbor")

from harbor.models.job.config import DatasetConfig


DATASET_REF = "sha256:7d7bdc1cbedad549fc1140404bd4dc45e5fd0ea7c4186773687d177ad3a0699a"
TASKS = [
    "adaptive-rejection-sampler",
    "bn-fit-modify",
    "break-filter-js-from-html",
    "build-cython-ext",
    "build-pmars",
    "build-pov-ray",
    "cancel-async-tasks",
    "chess-best-move",
    "circuit-fibsqrt",
    "cobol-modernization",
    "code-from-image",
    "configure-git-webserver",
    "constraints-scheduling",
    "count-dataset-tokens",
    "crack-7z-hash",
    "custom-memory-heap-crash",
    "db-wal-recovery",
    "distribution-search",
    "dna-assembly",
    "dna-insert",
    "extract-elf",
    "extract-moves-from-video",
    "feal-differential-cryptanalysis",
    "feal-linear-cryptanalysis",
    "filter-js-from-html",
    "financial-document-processor",
    "fix-code-vulnerability",
    "fix-git",
    "fix-ocaml-gc",
    "gcode-to-text",
    "git-leak-recovery",
    "git-multibranch",
    "gpt2-codegolf",
    "headless-terminal",
    "hf-model-inference",
    "install-windows-3.11",
    "kv-store-grpc",
    "large-scale-text-editing",
    "largest-eigenval",
    "llm-inference-batching-scheduler",
    "log-summary-date-ranges",
    "mailman",
    "make-doom-for-mips",
    "make-mips-interpreter",
    "mcmc-sampling-stan",
    "merge-diff-arc-agi-task",
    "model-extraction-relu-logits",
    "modernize-scientific-stack",
    "mteb-leaderboard",
    "mteb-retrieve",
    "multi-source-data-merger",
    "nginx-request-logging",
    "openssl-selfsigned-cert",
    "overfull-hbox",
    "password-recovery",
    "path-tracing-reverse",
    "path-tracing",
    "polyglot-c-py",
    "polyglot-rust-c",
    "portfolio-optimization",
    "protein-assembly",
    "prove-plus-comm",
    "pypi-server",
    "pytorch-model-cli",
    "pytorch-model-recovery",
    "qemu-alpine-ssh",
    "qemu-startup",
    "query-optimize",
    "raman-fitting",
    "regex-chess",
    "regex-log",
    "reshard-c4-data",
    "rstan-to-pystan",
    "sam-cell-seg",
    "sanitize-git-repo",
    "schemelike-metacircular-eval",
    "sparql-university",
    "sqlite-db-truncate",
    "sqlite-with-gcov",
    "torch-pipeline-parallelism",
    "torch-tensor-parallelism",
    "train-fasttext",
    "tune-mjcf",
    "video-processing",
    "vulnerable-secret",
    "winning-avg-corewars",
    "write-compressor",
]
SAMPLE = [
    "break-filter-js-from-html",
    "custom-memory-heap-crash",
    "fix-git",
    "git-multibranch",
    "gpt2-codegolf",
    "log-summary-date-ranges",
    "nginx-request-logging",
    "openssl-selfsigned-cert",
    "sqlite-db-truncate",
    "torch-pipeline-parallelism",
]
KNOWN_FAILURES = {
    "break-filter-js-from-html": "ChromeDriver exits with -5; possible ConTree runtime compatibility issue",
    "build-cython-ext": "pyknotid repository test failure; cause unclear",
    "gpt2-codegolf": "GPT-2 executable segfaults; possible ConTree runtime compatibility issue",
    "mcmc-sampling-stan": "rstan dependency and analysis.R are missing",
    "protein-assembly": "DNA Chisel constraints fail; gblock.txt is not created",
    "qemu-alpine-ssh": "Debian package 404s prevent verifier bootstrap",
    "qemu-startup": "Debian package 404s prevent verifier bootstrap",
    "torch-pipeline-parallelism": "CPU allocator ENOMEM; investigate ConTree VM memory limits",
}


def pytest_generate_tests(metafunc):
    tasks = TASKS if metafunc.config.getoption("harbor_suite") == "full" else SAMPLE
    metafunc.parametrize("task_name", tasks)


@pytest.fixture(scope="module")
def harbor_dataset():
    return DatasetConfig(
        name="terminal-bench/terminal-bench-2-1",
        ref=DATASET_REF,
        exclude_task_names=["*/compile-compcert", "*/caffe-cifar-10"],
    )


def test_oracle_task(task_name, harbor_results, pytestconfig, record_property):
    trial = harbor_results[task_name]
    artifacts = trial.config.trials_dir / trial.trial_name
    record_property("harbor_artifacts", str(artifacts.resolve()))
    record_property("known_failure", KNOWN_FAILURES.get(task_name, ""))
    assert trial.finished_at is not None, f"Trial did not finish: {artifacts}"
    assert trial.exception_info is None, f"{trial.exception_info}\nArtifacts: {artifacts}"
    assert trial.verifier_result is not None, f"No verifier result: {artifacts}"
    rewards = trial.verifier_result.rewards
    assert rewards is not None, f"Missing rewards: {artifacts}"
    assert rewards.get("reward") in {0, 1}, f"Invalid reward: {artifacts}"
    assert (artifacts / "verifier" / "test-stdout.txt").is_file(), f"Missing verifier output: {artifacts}"
    assert (artifacts / "verifier" / "reward.txt").is_file(), f"Missing reward artifact: {artifacts}"
    reward = rewards["reward"]
    known_failure = KNOWN_FAILURES.get(task_name)
    if reward == 0 and known_failure and pytestconfig.getoption("harbor_suite") == "sample":
        pytest.xfail(f"{known_failure}; artifacts: {artifacts}")
    assert reward == 1, f"{known_failure or 'Unexpected zero reward'}; artifacts: {artifacts}"
