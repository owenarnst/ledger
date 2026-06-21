"""Deterministic decision-anchor extraction and trail scanning.

This is the deterministic *recall index* of Ledger's topic pipeline (ADR-0002).
It is deliberately deterministic and never an LLM: it surfaces candidate decision
anchors for the Topic Analyst (:mod:`backend.analyst`) to investigate. The analyst
decides worklist membership and order; promotion into persisted topics lives in
:mod:`backend.repository`.

The unit we look for is a **defendable decision**, not a high-fan-in symbol. A
function or constant is kept only when its body carries a decision signal
(a threshold, an ordering, an access/filter, branching, or a bounded window) so
that a coherent "defend this choice" question can be formed. Generic helpers,
pure pass-throughs, dunders, and orchestration glue carry no such signal and are
cut — the self-validating filter the spec calls for.

Nothing here mints checks or mutants, and nothing here is the worklist gate. The
output is candidate anchors plus a transparent trail-scan receipt that the
analyst weighs; the deterministic gate/ranking now lives in
:class:`backend.analyst.DeterministicAnalyst` (the heuristic fallback), not here.
"""

from __future__ import annotations

import ast
import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# Directories that never hold repository decision sites.
NON_REPO_DIR_PARTS = frozenset(
    {".git", ".venv", "venv", "node_modules", ".claude", "__pycache__", ".pytest_cache"}
)

# Module-level constant values that are too generic to be a decision on their own.
TRIVIAL_CONSTANTS = frozenset({0, 1, -1, 2, True, False, None, "", "utf-8"})

# Causal/contrastive connectives that mark a comment or docstring as capturing
# the *why*, not just the *what*. Their presence in an anchor's own span or
# docstring is what flips it from untrailed to trailed. Kept tight on purpose: a
# behavioural description ("return only the documents for a tenant") is not a
# rationale; "named here ... rather than a bare literal scattered through the
# pipeline" is. The module docstring is deliberately *not* consulted — it would
# taint every anchor in the file with one decision's rationale.
RATIONALE_CONNECTIVES = (
    "because",
    "so that",
    "to avoid",
    "to prevent",
    "to ensure",
    "must never",
    "rather than",
    "deliberately",
    "otherwise",
    "fully deterministic",
    "input-order-independent",
)

# Risk-class vocabulary, matched against symbol/file keywords. Mirrors the
# vocabulary the demo seed uses so the dashboard reads consistently.
_RISK_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("persistence", ("tenant", "visible", "scope", "access", "permission", "auth", "isolat")),
    ("ranking", ("rerank", "rank", "score", "threshold", "confidence", "cutoff", "minimum")),
    ("external_api", ("retry", "client", "timeout", "request", "external", "provider")),
    ("retrieval", ("context", "window", "budget", "pack", "excerpt", "char", "dedup",
                   "duplicate", "candidate", "store", "token", "query", "retriev")),
)


@dataclass(frozen=True)
class DecisionAnchor:
    """A concrete code site that encodes a defendable decision."""

    anchor_id: str           # stable, e.g. "retrieval/rerank.py::visible_documents_for_tenant"
    file: str                # repo-relative path
    symbol: str              # qualified name (Class.method or function/CONSTANT)
    kind: str                # "function" | "constant"
    lineno: int
    end_lineno: int
    excerpt: str             # the source span
    docstring: str           # leading docstring/value comment, for honest labels
    signals: tuple[str, ...]  # why it is load-bearing
    risk_class: str
    fingerprint: str         # content hash; a change creates a new revision


@dataclass(frozen=True)
class TrailScan:
    """What Ledger searched for an anchor's reasoning, and what it found."""

    strength: str            # "documented" | "commented" | "mentioned" | "absent"
    searched: tuple[str, ...]  # sources scanned (honest receipt — never a naked claim)
    found: tuple[str, ...]   # where the symbol/rationale matched

    @property
    def untrailed(self) -> bool:
        # The worklist gate: no dedicated record and no co-located rationale.
        return self.strength in {"mentioned", "absent"}


@dataclass(frozen=True)
class Candidate:
    """An anchor bundled with its trail scan, centrality, and gate verdict."""

    anchor: DecisionAnchor
    trail: TrailScan
    caller_count: int
    load_bearing: bool
    untrailed: bool

    @property
    def surfaced(self) -> bool:
        return self.load_bearing and self.untrailed


# --------------------------------------------------------------------------- #
# Source discovery
# --------------------------------------------------------------------------- #

def _is_test_path(relative: Path) -> bool:
    parts = relative.parts
    if "tests" in parts or "test" in parts:
        return True
    name = relative.name
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def iter_source_files(repo_path: Path) -> list[Path]:
    """Repo-relative ``.py`` files that may hold decision anchors (no tests/glue)."""
    root = repo_path.expanduser().resolve()
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if NON_REPO_DIR_PARTS.intersection(relative.parts):
            continue
        if _is_test_path(relative):
            continue
        if relative.name == "__init__.py":
            continue
        files.append(relative)
    return files


# --------------------------------------------------------------------------- #
# Decision-signal analysis
# --------------------------------------------------------------------------- #

class _SignalVisitor(ast.NodeVisitor):
    """Collect decision signals from a function/method body."""

    def __init__(self) -> None:
        self.signals: set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # A nested function's signals belong to it, not to the enclosing one, so
        # a route handler's tenant guard never makes its app factory look like a
        # decision. We never descend into nested defs or classes.
        return

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]
    visit_ClassDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Compare(self, node: ast.Compare) -> None:
        # A comparison against a numeric or named bound is a threshold/boundary
        # decision; an `in`/`not in` membership test is a dedup/containment one.
        ops = {type(op) for op in node.ops}
        if ops & {ast.In, ast.NotIn}:
            self.signals.add("membership")
        if ops & {ast.Lt, ast.LtE, ast.Gt, ast.GtE}:
            self.signals.add("threshold")
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        self.signals.add("branch")
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.signals.add("branch")
        self.generic_visit(node)

    def _comp(self, node: ast.expr, generators: list[ast.comprehension]) -> None:
        if any(gen.ifs for gen in generators):
            self.signals.add("filter")
        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._comp(node, node.generators)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._comp(node, node.generators)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._comp(node, node.generators)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name in {"sorted"} and any(kw.arg == "key" for kw in node.keywords):
            self.signals.add("ordering")
        if name in {"sort"} and any(kw.arg == "key" for kw in node.keywords):
            self.signals.add("ordering")
        self.generic_visit(node)

    def visit_Break(self, node: ast.Break) -> None:
        self.signals.add("bounding")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        # A slice bounded by a named constant (`text[:MAX_EXCERPT]`) is a
        # deliberate windowing decision.
        if isinstance(node.slice, ast.Slice) and (node.slice.lower or node.slice.upper):
            self.signals.add("bounding")
        self.generic_visit(node)


def _function_signals(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    visitor = _SignalVisitor()
    for stmt in node.body:
        visitor.visit(stmt)
    return visitor.signals


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _docstring_of(node: ast.AST) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
        return ast.get_docstring(node) or ""
    return ""


def _risk_class(symbol: str, file: str, signals: set[str]) -> str:
    haystack = f"{symbol} {file}".lower()
    for risk, keywords in _RISK_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return risk
    if "threshold" in signals or "ordering" in signals:
        return "ranking"
    if "filter" in signals or "membership" in signals:
        return "retrieval"
    return "general"


def _fingerprint(excerpt: str) -> str:
    normalized = "\n".join(line.rstrip() for line in excerpt.strip().splitlines())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _span(source_lines: list[str], node: ast.AST) -> tuple[int, int, str]:
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    # Walk upward to absorb a contiguous block of leading comment lines: a
    # comment sitting directly above a constant or function is part of its
    # reasoning trail and belongs in the excerpt the dashboard shows.
    head = start
    while head > 1:
        previous = source_lines[head - 2].strip()
        if previous.startswith("#"):
            head -= 1
        else:
            break
    excerpt = "\n".join(source_lines[head - 1 : end])
    return start, end, excerpt


def _constant_is_decision(node: ast.AST) -> bool:
    if not isinstance(node, ast.Constant):
        return False
    return node.value not in TRIVIAL_CONSTANTS and not isinstance(node.value, bool)


def extract_anchors_from_source(relative: str, source: str) -> list[DecisionAnchor]:
    """Extract decision anchors from one module's source text."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()
    anchors: list[DecisionAnchor] = []

    def add_function(node: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> None:
        if _is_dunder(node.name) or node.name.startswith("_"):
            return
        signals = _function_signals(node)
        if not signals:
            return  # no defendable decision → trivia → cut
        start, end, excerpt = _span(lines, node)
        risk = _risk_class(qualname, relative, signals)
        anchors.append(
            DecisionAnchor(
                anchor_id=f"{relative}::{qualname}",
                file=relative,
                symbol=qualname,
                kind="function",
                lineno=start,
                end_lineno=end,
                excerpt=excerpt,
                docstring=_docstring_of(node),
                signals=tuple(sorted(signals)),
                risk_class=risk,
                fingerprint=_fingerprint(excerpt),
            )
        )

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_function(node, node.name)
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_function(member, f"{node.name}.{member.name}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                name = target.id
                if not name.isupper() or name.startswith("_"):
                    continue
                if not _constant_is_decision(node.value):
                    continue
                start, end, excerpt = _span(lines, node)
                risk = _risk_class(name, relative, {"threshold"})
                anchors.append(
                    DecisionAnchor(
                        anchor_id=f"{relative}::{name}",
                        file=relative,
                        symbol=name,
                        kind="constant",
                        lineno=start,
                        end_lineno=end,
                        excerpt=excerpt,
                        docstring="",
                        signals=("threshold",),
                        risk_class=risk,
                        fingerprint=_fingerprint(excerpt),
                    )
                )
    return anchors


def extract_anchors(repo_path: str | Path) -> list[DecisionAnchor]:
    """Extract every decision anchor in the repository, in file order."""
    root = Path(repo_path).expanduser().resolve()
    anchors: list[DecisionAnchor] = []
    for relative in iter_source_files(root):
        source = (root / relative).read_text(errors="replace")
        anchors.extend(extract_anchors_from_source(str(relative), source))
    return anchors


# --------------------------------------------------------------------------- #
# Trail scanning (the reasoning-trail half of the gate)
# --------------------------------------------------------------------------- #

def _trail_sources(repo_path: Path) -> list[tuple[str, str]]:
    """Return (label, text) pairs for every doc/record source worth searching."""
    sources: list[tuple[str, str]] = []
    adr_dir = repo_path / "docs" / "adr"
    if adr_dir.is_dir():
        for adr in sorted(adr_dir.glob("*.md")):
            sources.append((f"docs/adr/{adr.name}", adr.read_text(errors="replace")))
    for name in ("CONTEXT.md", "README.md", "README.rst", "README"):
        path = repo_path / name
        if path.is_file():
            sources.append((name, path.read_text(errors="replace")))
    return sources


def _humanized_terms(symbol: str) -> list[str]:
    leaf = symbol.split(".")[-1]
    words = [w for w in re.split(r"[_\W]+", leaf) if len(w) > 2]
    return [leaf] + words


def scan_trail(repo_path: str | Path, anchor: DecisionAnchor) -> TrailScan:
    """Search ADRs, CONTEXT, README, and the anchor's own comments for the why."""
    root = Path(repo_path).expanduser().resolve()
    searched: list[str] = []
    found: list[str] = []
    terms = _humanized_terms(anchor.symbol)
    lowered_terms = [t.lower() for t in terms]

    # 1. Dedicated decision records / project docs.
    documented = False
    for label, text in _trail_sources(root):
        searched.append(label)
        lowered = text.lower()
        if any(term in lowered for term in lowered_terms):
            found.append(label)
            if label.startswith("docs/adr/") or label == "CONTEXT.md":
                documented = True

    # 2. Co-located comments / docstring carrying the *why*. Scoped to the
    # anchor's own span + docstring only — never the module docstring, which
    # would taint every anchor in the file with one decision's rationale.
    searched.append(f"{anchor.file} comments")
    rationale_haystack = f"{anchor.excerpt.lower()}\n{anchor.docstring.lower()}"
    has_rationale = any(c in rationale_haystack for c in RATIONALE_CONNECTIVES)
    if has_rationale:
        found.append(f"{anchor.file} comments")

    if documented:
        strength = "documented"
    elif has_rationale:
        strength = "commented"
    elif found:
        strength = "mentioned"
    else:
        strength = "absent"
    return TrailScan(strength=strength, searched=tuple(searched), found=tuple(found))


# --------------------------------------------------------------------------- #
# Centrality (blast radius)
# --------------------------------------------------------------------------- #

def count_callers(repo_path: str | Path, anchor: DecisionAnchor) -> int:
    """Count references to the anchor symbol outside its own definition span.

    A deterministic centrality proxy: more reference sites → wider blast radius.
    """
    root = Path(repo_path).expanduser().resolve()
    leaf = anchor.symbol.split(".")[-1]
    pattern = re.compile(rf"\b{re.escape(leaf)}\b")
    total = 0
    for path in root.rglob("*.py"):
        relative = path.relative_to(root)
        if NON_REPO_DIR_PARTS.intersection(relative.parts):
            continue
        text = path.read_text(errors="replace")
        matches = list(pattern.finditer(text))
        if str(relative) == anchor.file:
            # Discount references inside the anchor's own definition span.
            in_span = sum(
                1
                for m in matches
                if anchor.lineno <= text.count("\n", 0, m.start()) + 1 <= anchor.end_lineno
            )
            total += len(matches) - in_span
        else:
            total += len(matches)
    return total


# --------------------------------------------------------------------------- #
# Top-level: bundle anchors with trail + centrality + gate verdict
# --------------------------------------------------------------------------- #

def extract_candidates(repo_path: str | Path) -> list[Candidate]:
    """Detect anchors, scan their trails, score centrality, and gate them.

    Every anchor here is load-bearing by construction (it carried a signal).
    ``surfaced`` candidates additionally pass the untrailed gate — those are the
    worklist topics. Trailed candidates are returned too, so callers can report
    honestly how many sites were considered and why most were not surfaced.
    """
    candidates: list[Candidate] = []
    for anchor in extract_anchors(repo_path):
        trail = scan_trail(repo_path, anchor)
        callers = count_callers(repo_path, anchor)
        candidates.append(
            Candidate(
                anchor=anchor,
                trail=trail,
                caller_count=callers,
                load_bearing=True,
                untrailed=trail.untrailed,
            )
        )
    return candidates


def resolve_head_sha(repo_path: str | Path) -> str | None:
    """Best-effort current commit SHA; ``None`` when the repo isn't under git."""
    root = Path(repo_path).expanduser().resolve()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return None
    sha = proc.stdout.strip()
    return sha or None


def blast_score(candidate: Candidate) -> int:
    """Deterministic ranking weight: risk class + centrality + signal breadth."""
    risk_weight = {
        "persistence": 50,
        "external_api": 40,
        "ranking": 30,
        "retrieval": 20,
        "general": 10,
    }.get(candidate.anchor.risk_class, 10)
    return risk_weight + candidate.caller_count * 3 + len(candidate.anchor.signals)
