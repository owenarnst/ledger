"""Deterministic citation verification (ADR-0002, #22).

The verifier resolves the analyst's cited locators against the indexed sources,
rejects unsupported/stale citations, hashes accepted excerpts, and drops a
proposal that has no verifiable code grounding.
"""

from backend.analyst import (
    AnalystIndex,
    CodeAnchorCitation,
    DeterministicAnalyst,
    TopicProposal,
    TraceCitation,
    TraceLocator,
)
from backend.ingestion import TraceSegment
from backend.sandbox import HERO_REPO
from backend.verifier import fingerprint, verify_proposals


def _index():
    return AnalystIndex.from_repo(HERO_REPO)


def _real_anchor_citation(index):
    # A citation the deterministic analyst itself produced — guaranteed real.
    return DeterministicAnalyst().discover(HERO_REPO, index).proposals[0].code_anchors[0]


def _proposal(anchors, traces=()):
    return TopicProposal(
        title="T",
        maintenance_obligation="obligation",
        invariant="invariant",
        impact_level="high",
        impact_consequence="consequence",
        priority_rationale="why",
        code_anchors=tuple(anchors),
        development_traces=tuple(traces),
    )


def test_verify_resolves_real_anchor_to_excerpt_and_deterministic_hash():
    index = _index()
    citation = _real_anchor_citation(index)

    result = verify_proposals([_proposal([citation])], repo_root=HERO_REPO, index=index)

    assert len(result.verified) == 1
    anchor = result.verified[0].primary
    assert anchor.path == "retrieval/rerank.py"
    assert "tenant_id" in anchor.excerpt
    # The accepted excerpt is hashed deterministically.
    assert anchor.excerpt_sha == fingerprint(anchor.excerpt)
    assert result.verified[0].fingerprint == anchor.excerpt_sha
    assert result.rejected == ()


def test_verify_rejects_stale_or_missing_citations():
    index = _index()
    out_of_range = CodeAnchorCitation("retrieval/rerank.py", 99999, None, "ghost line")
    missing_file = CodeAnchorCitation("nope/does_not_exist.py", 1, None, "ghost file")

    result = verify_proposals(
        [_proposal([out_of_range]), _proposal([missing_file])],
        repo_root=HERO_REPO,
        index=index,
    )

    assert result.verified == ()
    assert len(result.rejected) >= 2
    assert all("unresolved" in r.reason for r in result.rejected)


def test_verify_rejects_topic_with_no_code_anchors():
    result = verify_proposals([_proposal([])], repo_root=HERO_REPO, index=_index())
    assert result.verified == ()
    assert any("no code anchors" in r.reason for r in result.rejected)


def test_verify_accepts_supported_trace_and_rejects_unsupported():
    index = _index()
    citation = _real_anchor_citation(index)
    available = (TraceLocator(provider="claude_code", session_id="s1", source_path="x.jsonl"),)
    supported = TraceCitation("claude_code", "x.jsonl", "edited here", "hand_verified")
    unsupported = TraceCitation("claude_code", "ghost.jsonl", "nope", "heuristic")

    result = verify_proposals(
        [_proposal([citation], traces=[supported, unsupported])],
        repo_root=HERO_REPO,
        index=index,
        available_traces=available,
    )

    # The topic still verifies on its code anchor; only the bad trace is dropped.
    assert len(result.verified) == 1
    verified = result.verified[0]
    assert len(verified.traces) == 1
    assert verified.traces[0].source_path == "x.jsonl"
    assert verified.traces[0].link_confidence == "hand_verified"
    assert any("unsupported trace" in r.reason for r in result.rejected)


def test_verify_resolves_cited_segments_and_drops_unknown_ids():
    index = _index()
    citation = _real_anchor_citation(index)
    segments = (
        TraceSegment(id="seg0", kind="prompt", text="filter by tenant before rerank"),
        TraceSegment(id="seg1", kind="tool_call", tool="Edit", target="retrieval/rerank.py"),
    )
    available = (
        TraceLocator(provider="claude_code", session_id="s1", source_path="x.jsonl", segments=segments),
    )
    # The analyst cites two real segment ids plus one the session never had.
    cited = TraceCitation(
        "claude_code", "x.jsonl", "authored the filter", "hand_verified",
        segment_ids=("seg0", "seg1", "ghost"),
    )

    result = verify_proposals(
        [_proposal([citation], traces=[cited])],
        repo_root=HERO_REPO,
        index=index,
        available_traces=available,
    )

    verified_trace = result.verified[0].traces[0]
    # Only the two segments the session actually contains survive, in order.
    assert [s.id for s in verified_trace.segments] == ["seg0", "seg1"]
    assert verified_trace.segments[0].kind == "prompt"
    assert verified_trace.segments[1].target == "retrieval/rerank.py"


def test_verify_tolerates_trace_locator_with_line_suffix():
    index = _index()
    citation = _real_anchor_citation(index)
    # Provider is incidental here; a non-default value proves verification echoes
    # whatever provider the trace carries rather than hardcoding one.
    available = (TraceLocator(provider="other", session_id="s2", source_path="y.jsonl"),)
    cited = TraceCitation("other", "y.jsonl:42", "touched", "exact")

    result = verify_proposals(
        [_proposal([citation], traces=[cited])],
        repo_root=HERO_REPO,
        index=index,
        available_traces=available,
    )

    assert len(result.verified[0].traces) == 1
    assert result.verified[0].traces[0].provider == "other"
