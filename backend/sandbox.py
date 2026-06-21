from __future__ import annotations

import io
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
HERO_REPO = PACKAGE_ROOT / "fixtures" / "hero_repo"

# Recipes refer to bundled fixtures by alias so the database stays portable
# across installs (no machine-specific absolute paths).
FIXTURE_ALIASES = {"@hero_repo": HERO_REPO}


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    output: str
    elapsed_ms: int


@dataclass(frozen=True)
class RecipeValidation:
    """The baseline-green -> mutant-red evidence a repo-derived recipe must show."""

    baseline_passed: bool
    mutant_failed: bool
    target_test_failed: bool
    baseline_output: str
    mutant_output: str

    @property
    def ok(self) -> bool:
        # A recipe is only trustworthy if the pristine tree is green and the
        # curated mutation turns it red on the test it claims to target.
        return self.baseline_passed and self.mutant_failed and self.target_test_failed


def resolve_fixture(fixture_source: str) -> Path:
    if fixture_source in FIXTURE_ALIASES:
        return FIXTURE_ALIASES[fixture_source]
    return Path(fixture_source).expanduser()


def apply_mutation(
    destination: Path, target_file: str, mutation_before: str, mutation_after: str
) -> None:
    """Apply the recipe's curated substring mutation to the sandbox target."""
    target = destination / target_file
    content = target.read_text()
    if mutation_before not in content:
        raise RuntimeError("recipe mutation target not found")
    target.write_text(content.replace(mutation_before, mutation_after))


def _extract_git_revision(destination: Path, repo_path: Path, revision_sha: str) -> None:
    """Materialize a repository tree at a pinned commit (source only, no .git)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_path), "archive", revision_sha],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            f"git archive failed for {revision_sha} in {repo_path}: "
            f"{proc.stderr.decode(errors='replace').strip()}"
        )
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(proc.stdout)) as tar:
        tar.extractall(destination)


def create_sandbox_from_recipe(
    destination: Path,
    *,
    fixture_source: str,
    target_file: str,
    mutation_before: str,
    mutation_after: str,
    repo_path: str | Path | None = None,
    revision_sha: str | None = None,
    mutate: bool = True,
) -> Path:
    """Build a sandbox for a recipe and (optionally) apply the curated mutation.

    Two sources are supported and chosen by ``revision_sha``:

    * **repo-derived** — when ``revision_sha`` is set, the tree is extracted from
      ``repo_path`` at that exact commit via ``git archive`` (source only). This
      is the Step-2 path: a real revision of a real enrolled repository.
    * **fixture** — otherwise the bundled fixture named by ``fixture_source`` is
      copied. This is the disclosed-demo path.

    ``mutate=False`` produces the pristine baseline used to prove the tree is
    green before the mutation makes it red.
    """
    if destination.exists():
        shutil.rmtree(destination)

    if revision_sha:
        if not repo_path:
            raise RuntimeError("repo-derived recipe requires a repo_path")
        root = Path(repo_path).expanduser()
        if not root.exists():
            raise RuntimeError(f"recipe repo path not found: {repo_path}")
        _extract_git_revision(destination, root, revision_sha)
    else:
        source = resolve_fixture(fixture_source)
        if not source.exists():
            raise RuntimeError(f"recipe fixture source not found: {fixture_source}")
        shutil.copytree(source, destination)

    if mutate:
        apply_mutation(destination, target_file, mutation_before, mutation_after)
    return destination


def run_test_command(sandbox_path: Path, command: str) -> CheckResult:
    """Run the recipe's own test command inside the sandbox.

    A leading ``python``/``python3`` token is rewritten to the active
    interpreter so the sandbox uses the same environment Ledger runs in.
    """
    argv = shlex.split(command)
    if not argv:
        raise RuntimeError("empty test command")
    if argv[0] in {"python", "python3"}:
        argv[0] = sys.executable
    started = time.monotonic()
    proc = subprocess.run(
        argv,
        cwd=sandbox_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return CheckResult(
        passed=proc.returncode == 0,
        output=proc.stdout,
        elapsed_ms=elapsed_ms,
    )


def validate_recipe(
    *,
    fixture_source: str,
    target_file: str,
    test_command: str,
    mutation_before: str,
    mutation_after: str,
    repo_path: str | Path | None = None,
    revision_sha: str | None = None,
    target_test: str | None = None,
) -> RecipeValidation:
    """Prove baseline-green -> mutant-red for a recipe in throwaway sandboxes.

    Builds the pristine tree and runs the test command (must pass), then builds
    the mutated tree and runs it again (must fail, and fail the ``target_test``
    if one is named). Temporary sandboxes are always cleaned up.
    """
    workspace = Path(tempfile.mkdtemp(prefix="ledger-validate-"))
    try:
        baseline = workspace / "baseline"
        create_sandbox_from_recipe(
            baseline,
            fixture_source=fixture_source,
            target_file=target_file,
            mutation_before=mutation_before,
            mutation_after=mutation_after,
            repo_path=repo_path,
            revision_sha=revision_sha,
            mutate=False,
        )
        baseline_result = run_test_command(baseline, test_command)

        mutant = workspace / "mutant"
        create_sandbox_from_recipe(
            mutant,
            fixture_source=fixture_source,
            target_file=target_file,
            mutation_before=mutation_before,
            mutation_after=mutation_after,
            repo_path=repo_path,
            revision_sha=revision_sha,
            mutate=True,
        )
        mutant_result = run_test_command(mutant, test_command)

        if target_test:
            # pytest only prints a test's name when it fails (passing tests are
            # dots), so the leaf appearing in a non-green run means it went red.
            leaf = target_test.split("::")[-1]
            target_test_failed = not mutant_result.passed and leaf in mutant_result.output
        else:
            target_test_failed = not mutant_result.passed

        return RecipeValidation(
            baseline_passed=baseline_result.passed,
            mutant_failed=not mutant_result.passed,
            target_test_failed=target_test_failed,
            baseline_output=baseline_result.output,
            mutant_output=mutant_result.output,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
