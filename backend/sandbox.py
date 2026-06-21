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


def create_hero_sandbox(destination: Path) -> Path:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(HERO_REPO, destination)
    target = destination / "retrieval" / "rerank.py"
    content = target.read_text()
    original = "return [doc for doc in documents if doc.tenant_id == tenant_id]"
    mutated = "return list(documents)"
    if original not in content:
        raise RuntimeError("hero mutation target not found")
    target.write_text(content.replace(original, mutated))
    return destination


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
