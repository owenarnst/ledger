from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
HERO_REPO = PACKAGE_ROOT / "fixtures" / "hero_repo"


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    output: str
    elapsed_ms: int


@dataclass(frozen=True)
class SandboxSpec:
    """How to stage one topic's Debug-to-Own exercise in the hero repo.

    ``target_file`` is the file the learner edits. ``original`` is the correct,
    invariant-preserving code; the sandbox replaces it with ``mutated`` to inject
    the bug, so restoring ``original`` is the fix and the (whole) hero test suite
    is what verifies it. ``original`` must be a unique substring of the target.
    """

    target_file: str
    original: str
    mutated: str


# One spec per seeded demo topic. Each injected bug is the canonical violation of
# that topic's invariant, and at least one shipped hero-repo test catches it (see
# fixtures/hero_repo/tests). Unknown topics fall back to the tenant exercise — the
# historical default — so checks on non-demo topics behave as before.
SANDBOX_SPECS: dict[str, SandboxSpec] = {
    # Tenant isolation: the pre-rerank visibility filter is dropped, so the
    # tenant-blind candidate set is returned unfiltered (test_rerank +
    # test_pipeline + test_api tenant-scoping tests fail).
    "tenant-cache-isolation": SandboxSpec(
        target_file="retrieval/rerank.py",
        original="return [doc for doc in documents if doc.tenant_id == tenant_id]",
        mutated="return list(documents)",
    ),
    # Confidence cutoff: the score threshold stops being enforced, so weak matches
    # survive into context/results (test_rerank confidence + test_pipeline cutoff).
    "docs-search-api-rerank-rerank": SandboxSpec(
        target_file="retrieval/rerank.py",
        original="return [doc for doc in documents if doc.score >= minimum_score]",
        mutated="return list(documents)",
    ),
    # Context packing: the per-excerpt cap is removed, so one oversized document
    # can dominate/overflow the window (test_context per-document-cap test).
    "docs-search-api-context-context": SandboxSpec(
        target_file="retrieval/context.py",
        original="cost = min(len(document.text), max_excerpt)",
        mutated="cost = len(document.text)",
    ),
}

DEFAULT_SANDBOX_SPEC = SANDBOX_SPECS["tenant-cache-isolation"]


def sandbox_spec_for(topic_id: str) -> SandboxSpec:
    """The exercise spec for ``topic_id``; the tenant exercise if none is registered."""
    return SANDBOX_SPECS.get(topic_id, DEFAULT_SANDBOX_SPEC)


def create_sandbox(destination: Path, spec: SandboxSpec = DEFAULT_SANDBOX_SPEC) -> Path:
    """Copy the hero repo to ``destination`` and inject ``spec``'s bug."""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(HERO_REPO, destination)
    target = destination / spec.target_file
    content = target.read_text()
    if spec.original not in content:
        raise RuntimeError(f"sandbox mutation target not found in {spec.target_file}")
    target.write_text(content.replace(spec.original, spec.mutated))
    return destination


def create_hero_sandbox(destination: Path) -> Path:
    """Backwards-compatible alias: stage the tenant-isolation exercise."""
    return create_sandbox(destination, DEFAULT_SANDBOX_SPEC)


def run_pytest(sandbox_path: Path) -> CheckResult:
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-s", "tests"],
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
