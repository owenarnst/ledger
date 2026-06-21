"""Shared test fixtures.

The Step 2/3 tests run against a real git repository so they exercise the
git-archive sandbox and the baseline-green -> mutant-red validation for real,
without depending on any repository outside the source tree. The bundled
hero-repo fixture (a faithful copy of the demo repo) is committed into a
throwaway git repo under ``tmp_path``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from backend.sandbox import HERO_REPO


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.fixture
def hero_repo_path() -> Path:
    """Path to the bundled, un-versioned hero-repo fixture (for AST-only tests)."""
    return HERO_REPO


@pytest.fixture
def git_repo(tmp_path) -> tuple[Path, str]:
    """A committed git repo built from the hero fixture; returns (path, head_sha)."""
    repo = tmp_path / "docs-search-api"
    shutil.copytree(
        HERO_REPO, repo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv")
    )
    _git(["init", "-q"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Ledger Test"], repo)
    _git(["config", "commit.gpgsign", "false"], repo)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "seed hero repo"], repo)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    return repo, sha
