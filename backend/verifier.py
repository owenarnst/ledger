"""Deterministic citation verification (ADR-0002, #22).

The analyst's worklist is a Claude-generated *interpretation*. Before a proposal
becomes a persisted fact, deterministic code resolves every cited locator against
the indexed sources, **rejects unsupported or stale citations**, and hashes the
accepted excerpts. A proposal joins the worklist only when at least one of its
code anchors verifies; unsupported trace citations are dropped (never persisted)
and recorded for audit. Checkability and pass/fail stay empirical and are not
touched here.

Discovery (:mod:`backend.analyst`) may interpret; verification may not. This
module never calls an LLM and never invents a citation.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path

from .analyst import AnalystIndex, CodeAnchorCitation, TopicProposal, TraceCitation, TraceLocator


def fingerprint(excerpt: str) -> str:
    """Stable content hash of an accepted excerpt (matches extraction's scheme)."""
    normalized = "\n".join(line.rstrip() for line in excerpt.strip().splitlines())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class VerifiedAnchor:
    path: str
    lineno: int
    symbol: str
    excerpt: str
    excerpt_sha: str
    risk_class: str
    caller_count: int
    relevance: str

    @property
    def source_locator(self) -> str:
        return f"{self.path}:{self.lineno}"


@dataclass(frozen=True)
class VerifiedTrace:
    provider: str
    session_id: str | None
    source_path: str | None
    relevance: str
    link_confidence: str

    @property
    def source_locator(self) -> str | None:
        return self.source_path or self.session_id


@dataclass(frozen=True)
class VerifiedTopic:
    proposal: TopicProposal
    anchors: tuple[VerifiedAnchor, ...]
    traces: tuple[VerifiedTrace, ...]

    @property
    def primary(self) -> VerifiedAnchor:
        return self.anchors[0]

    @property
    def fingerprint(self) -> str:
        # Revision identity rides the primary anchor's accepted excerpt.
        return self.primary.excerpt_sha


@dataclass(frozen=True)
class Rejection:
    """One rejected citation or dropped proposal, recorded for auditability."""

    title: str
    reason: str


@dataclass(frozen=True)
class VerificationResult:
    verified: tuple[VerifiedTopic, ...]
    rejected: tuple[Rejection, ...]


def verify_proposals(
    proposals: list[TopicProposal],
    *,
    repo_root: str | Path,
    index: AnalystIndex,
    available_traces: tuple[TraceLocator, ...] = (),
) -> VerificationResult:
    """Resolve every cited locator; accept only what the sources support."""
    repo_root = Path(repo_root)
    trace_lookup = _trace_lookup(available_traces)
    verified: list[VerifiedTopic] = []
    rejected: list[Rejection] = []

    for proposal in proposals:
        anchors: list[VerifiedAnchor] = []
        for citation in proposal.code_anchors:
            anchor = _verify_anchor(repo_root, index, citation)
            if anchor is None:
                rejected.append(
                    Rejection(proposal.title, f"unresolved code anchor {citation.path}:{citation.lineno}")
                )
            else:
                anchors.append(anchor)

        if not anchors:
            if not proposal.code_anchors:
                rejected.append(Rejection(proposal.title, "no code anchors cited"))
            # A proposal with no verifiable code grounding never joins the worklist.
            continue

        traces: list[VerifiedTrace] = []
        for citation in proposal.development_traces:
            trace = _verify_trace(trace_lookup, citation)
            if trace is None:
                rejected.append(
                    Rejection(proposal.title, f"unsupported trace citation {citation.locator}")
                )
            else:
                traces.append(trace)

        verified.append(VerifiedTopic(proposal, tuple(anchors), tuple(traces)))

    return VerificationResult(tuple(verified), tuple(rejected))


def _verify_anchor(
    repo_root: Path, index: AnalystIndex, citation: CodeAnchorCitation
) -> VerifiedAnchor | None:
    """Resolve a code locator against the recall index, then the live file.

    A match to an indexed candidate carries that anchor's symbol/risk/centrality.
    Otherwise the file is read at the cited span; a locator that points past the
    file (missing path or out-of-range line) is **stale/unsupported** -> ``None``.
    """
    for candidate in index.candidates:
        anchor = candidate.anchor
        if anchor.file == citation.path and anchor.lineno <= citation.lineno <= anchor.end_lineno:
            return VerifiedAnchor(
                path=anchor.file,
                lineno=anchor.lineno,
                symbol=anchor.symbol,
                excerpt=anchor.excerpt,
                excerpt_sha=fingerprint(anchor.excerpt),
                risk_class=anchor.risk_class,
                caller_count=candidate.caller_count,
                relevance=citation.relevance,
            )

    excerpt = _read_span(repo_root, citation.path, citation.lineno, citation.end_lineno)
    if excerpt is None:
        return None
    symbol = _enclosing_symbol(repo_root, citation.path, citation.lineno) or Path(citation.path).stem
    return VerifiedAnchor(
        path=citation.path,
        lineno=citation.lineno,
        symbol=symbol,
        excerpt=excerpt,
        excerpt_sha=fingerprint(excerpt),
        risk_class="general",
        caller_count=0,
        relevance=citation.relevance,
    )


def _verify_trace(lookup: dict[str, TraceLocator], citation: TraceCitation) -> VerifiedTrace | None:
    located = lookup.get(citation.locator)
    if located is None:
        # Tolerate a "source_path:line" locator against a stored bare source_path.
        located = lookup.get(citation.locator.rsplit(":", 1)[0])
    if located is None:
        return None
    return VerifiedTrace(
        provider=located.provider,
        session_id=located.session_id,
        source_path=located.source_path,
        relevance=citation.relevance,
        link_confidence=citation.link_confidence,
    )


def _trace_lookup(traces: tuple[TraceLocator, ...]) -> dict[str, TraceLocator]:
    lookup: dict[str, TraceLocator] = {}
    for trace in traces:
        if trace.source_path:
            lookup[trace.source_path] = trace
        if trace.session_id:
            lookup[trace.session_id] = trace
    return lookup


def _read_span(repo_root: Path, path: str, lineno: int, end_lineno: int | None) -> str | None:
    file_path = repo_root / path
    if not file_path.is_file():
        return None
    lines = file_path.read_text(errors="replace").splitlines()
    if lineno < 1 or lineno > len(lines):
        return None
    end = min(max(end_lineno or lineno, lineno), len(lines))
    return "\n".join(lines[lineno - 1 : end])


def _enclosing_symbol(repo_root: Path, path: str, lineno: int) -> str | None:
    try:
        tree = ast.parse((repo_root / path).read_text(errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return None
    matches: list[tuple[int, str]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = child.lineno
                end = getattr(child, "end_lineno", start) or start
                qual = f"{prefix}{child.name}"
                if start <= lineno <= end:
                    matches.append((end - start, qual))
                visit(child, f"{qual}.")

    visit(tree, "")
    return min(matches, key=lambda m: m[0])[1] if matches else None
