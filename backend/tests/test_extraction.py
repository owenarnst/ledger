"""Deterministic extraction — the recall index that seeds the analyst."""

from backend.extraction import (
    blast_score,
    extract_anchors,
    extract_candidates,
    scan_trail,
)
from backend.sandbox import HERO_REPO


def _anchors_by_symbol():
    return {a.symbol: a for a in extract_anchors(HERO_REPO)}


def _candidates_by_symbol():
    return {c.anchor.symbol: c for c in extract_candidates(HERO_REPO)}


def test_extracts_tenant_filter_as_load_bearing_decision():
    anchors = _anchors_by_symbol()
    assert "visible_documents_for_tenant" in anchors
    anchor = anchors["visible_documents_for_tenant"]
    assert anchor.kind == "function"
    assert "filter" in anchor.signals
    assert anchor.risk_class == "persistence"
    assert anchor.fingerprint  # content hash present for revision tracking


def test_drops_generic_helpers_and_orchestration_glue():
    symbols = set(_anchors_by_symbol())
    # A regex helper carries no defendable decision; the pipeline `search` is
    # pure composition; the app factory's signal must not leak from its nested
    # route handler.
    assert "tokenize" not in symbols
    assert "search" not in symbols
    assert "create_app" not in symbols
    assert "default_store" not in symbols


def test_detects_constant_thresholds_and_method_anchors():
    symbols = set(_anchors_by_symbol())
    assert "MINIMUM_RERANK_SCORE" in symbols
    assert "DocumentStore.candidates" in symbols  # decision logic inside a class


def test_well_documented_decisions_carry_a_trail_and_are_not_surfaced():
    candidates = _candidates_by_symbol()
    # `rerank` explains its determinism rationale; the threshold names its policy
    # "rather than a bare literal". Both have a trail and must not be flagged.
    assert candidates["rerank"].trail.strength == "commented"
    assert candidates["rerank"].surfaced is False
    assert candidates["MINIMUM_RERANK_SCORE"].surfaced is False


def test_constant_leading_comment_is_captured_as_its_trail():
    candidates = _candidates_by_symbol()
    anchor = candidates["MINIMUM_RERANK_SCORE"].anchor
    # The rationale comment sits above the assignment; the span absorbs it.
    assert "rather than" in anchor.excerpt
    assert candidates["MINIMUM_RERANK_SCORE"].trail.strength == "commented"


def test_untrailed_tenant_decision_surfaces_and_ranks_first():
    ranked = sorted(extract_candidates(HERO_REPO), key=lambda c: -blast_score(c))
    surfaced = [c for c in ranked if c.surfaced]
    assert surfaced, "expected at least one untrailed load-bearing topic"
    assert surfaced[0].anchor.symbol == "visible_documents_for_tenant"
    assert all(c.untrailed for c in surfaced)
    # The gate genuinely discriminates: not everything load-bearing surfaces.
    assert len(surfaced) < len(ranked)


def test_trail_scan_is_a_transparent_search_receipt():
    anchor = _anchors_by_symbol()["visible_documents_for_tenant"]
    trail = scan_trail(HERO_REPO, anchor)
    assert "README.md" in trail.searched
    assert any("comments" in s for s in trail.searched)
    assert trail.strength in {"mentioned", "absent"}
