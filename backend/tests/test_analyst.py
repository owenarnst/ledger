"""Topic Analyst — agentic discovery (ADR-0002, #21).

The deterministic analyst is the CI default and the honest fallback; the Claude
analyst rides ``claude -p`` with the *inverse* of the Coach/Labeler tool boundary
(read-only investigation allowed, mutation/shell/web denied).
"""

import io
import json

import pytest

from backend.analyst import (
    AnalystIndex,
    ClaudeAnalyst,
    CodeAnchorCitation,
    DeterministicAnalyst,
    TopicProposal,
    TraceLocator,
    create_analyst,
    parse_proposals,
)
from backend.ingestion import TraceSegment
from backend.sandbox import HERO_REPO


def _trace_locator():
    segments = (
        TraceSegment(id="seg0", kind="prompt", text="scope candidates to the tenant before rerank"),
        TraceSegment(id="seg1", kind="tool_call", tool="Edit", target="retrieval/rerank.py"),
        TraceSegment(id="seg2", kind="tool_call", tool="Bash", target="python -m pytest"),
    )
    return TraceLocator(
        provider="claude_code", session_id="s1", source_path="x.jsonl", segments=segments
    )


def _index():
    return AnalystIndex.from_repo(HERO_REPO)


def test_deterministic_analyst_proposes_ordered_grounded_worklist():
    discovery = DeterministicAnalyst().discover(HERO_REPO, _index())
    assert discovery.model_id == "deterministic"
    proposals = discovery.proposals
    assert proposals, "expected at least one surfaced topic on the hero repo"

    top = proposals[0]
    assert "tenant isolation" in top.title.lower()  # durable obligation, not a raw symbol
    assert top.impact_level == "high"  # persistence path
    assert top.code_anchors and top.code_anchors[0].path == "retrieval/rerank.py"

    # Every proposal satisfies the Minimum Topic proposal contract.
    for p in proposals:
        assert p.title and p.maintenance_obligation and p.invariant
        assert p.impact_level in ("high", "medium", "low")
        assert p.impact_consequence and p.priority_rationale
        assert p.code_anchors  # grounded in at least one real locator


def test_deterministic_analyst_is_the_recall_gate_not_the_repo_layer():
    # The analyst — not the repository — now decides membership: it returns fewer
    # proposals than there are candidate anchors (the gate genuinely discriminates).
    index = _index()
    proposals = DeterministicAnalyst().discover(HERO_REPO, index).proposals
    assert 0 < len(proposals) < len(index.candidates)


def test_claude_analyst_allows_scoped_readonly_tools_and_denies_the_rest():
    cmd = ClaudeAnalyst().build_command()
    assert "-p" in cmd and "--output-format" in cmd
    assert cmd[cmd.index("--model") + 1] == "opus"
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in cmd

    allowed = cmd[cmd.index("--allowedTools") + 1]
    assert set(allowed.split(",")) == {"Read", "Grep", "Glob"}

    disallowed = cmd[cmd.index("--disallowedTools") + 1]
    for denied in ("Edit", "Write", "Bash", "WebFetch", "mcp__*"):
        assert denied in disallowed
    # Investigation IS the analyst's purpose — this is the inverse of the Coach.
    for tool in ("Read", "Grep", "Glob"):
        assert tool not in disallowed.split(",")


def test_claude_analyst_falls_back_to_deterministic_when_cli_absent():
    index = _index()
    analyst = ClaudeAnalyst(binary="definitely-not-a-real-binary-xyz")
    discovery = analyst.discover(HERO_REPO, index)
    # Discovery never breaks: it degrades to the honest deterministic worklist,
    # and reports itself as deterministic — never heuristics dressed as Claude.
    assert discovery.model_id == "deterministic"
    deterministic = DeterministicAnalyst().discover(HERO_REPO, index).proposals
    assert [p.title for p in discovery.proposals] == [p.title for p in deterministic]
    assert discovery.proposals
    assert "could not start" in (discovery.fallback_reason or "").lower()


def test_claude_analyst_streams_safe_progress_and_parses_final_result(monkeypatch):
    proposal = {
        "title": "Tenant isolation in retrieval",
        "maintenance_obligation": "Scope candidates to the requesting tenant.",
        "invariant": "Filter by tenant before ranking.",
        "impact_level": "high",
        "impact_consequence": "Cross-tenant document leak.",
        "priority_rationale": "Highest blast radius.",
        "code_anchors": [
            {"path": "retrieval/rerank.py", "lineno": 10, "end_lineno": 12, "relevance": "filter"}
        ],
        "development_traces": [],
    }
    events = [
        {"type": "system", "subtype": "init", "model": "claude-opus-test"},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": str(HERO_REPO / "retrieval/rerank.py")},
                    },
                    {"type": "text", "text": "private model reasoning must not be emitted"},
                ]
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "num_turns": 3,
            "result": json.dumps([proposal]),
        },
    ]

    class FakeStdin:
        def __init__(self):
            self.value = ""

        def write(self, value):
            self.value += value

        def close(self):
            pass

    class FakePopen:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = io.StringIO("".join(json.dumps(event) + "\n" for event in events))
            self.stderr = io.StringIO("")
            self.returncode = 0

        def wait(self):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

    fake = FakePopen()
    monkeypatch.setattr("backend.analyst.subprocess.Popen", lambda *args, **kwargs: fake)
    progress: list[str] = []

    discovery = ClaudeAnalyst().discover(HERO_REPO, _index(), progress=progress.append)

    assert discovery.model_id == "claude-opus-test"
    assert discovery.proposals[0].title == "Tenant isolation in retrieval"
    assert "Reading retrieval/rerank.py" in progress
    assert all("private model reasoning" not in message for message in progress)
    assert "Candidate decision anchors" in fake.stdin.value


def test_claude_analyst_prompt_seeds_the_recall_index():
    index = _index()
    prompt = ClaudeAnalyst().build_prompt(HERO_REPO, index)
    assert "retrieval/rerank.py" in prompt
    assert "Candidate decision anchors" in prompt


def test_digest_lists_trace_segments_with_their_ids():
    index = AnalystIndex.from_repo(HERO_REPO, traces=(_trace_locator(),))
    digest = index.digest()
    # The analyst sees each segment with the id it must cite.
    assert "seg0 PROMPT" in digest
    assert "scope candidates to the tenant before rerank" in digest
    assert "seg1 TOOL Edit retrieval/rerank.py" in digest
    assert "segment_ids" in digest  # the citing instruction


def test_deterministic_analyst_file_scopes_trace_segments_as_fallback():
    index = AnalystIndex.from_repo(HERO_REPO, traces=(_trace_locator(),))
    proposals = DeterministicAnalyst().discover(HERO_REPO, index).proposals

    cited = [p for p in proposals if p.development_traces]
    assert cited, "expected the rerank.py topic to pick up the file-scoped trace"
    trace = cited[0].development_traces[0]
    assert trace.provider == "claude_code"
    assert trace.link_confidence == "heuristic"
    # Only the tool calls touching the anchor file are cited — not the prompt
    # (prompts have no file association) nor the unrelated `pytest` Bash call.
    assert trace.segment_ids == ("seg1",)


def test_parse_proposals_reads_a_result_enveloped_json_array():
    inner = json.dumps(
        [
            {
                "title": "Tenant isolation in retrieval",
                "maintenance_obligation": "Scope candidates to the requesting tenant.",
                "invariant": "Filter by tenant before ranking.",
                "impact_level": "high",
                "impact_consequence": "Cross-tenant document leak.",
                "priority_rationale": "Highest blast radius, no decision record.",
                "code_anchors": [
                    {"path": "retrieval/rerank.py", "lineno": 10, "end_lineno": 12, "relevance": "the filter"}
                ],
                "development_traces": [
                    {"provider": "claude_code", "locator": "x.jsonl:4", "relevance": "edited here", "link_confidence": "hand_verified"}
                ],
            }
        ]
    )
    proposals = parse_proposals(json.dumps({"result": inner}))
    assert len(proposals) == 1
    p = proposals[0]
    assert p.title == "Tenant isolation in retrieval"
    assert p.impact_level == "high"
    assert p.code_anchors[0].lineno == 10
    assert p.development_traces[0].link_confidence == "hand_verified"


def test_parse_proposals_reads_cited_trace_segment_ids():
    inner = json.dumps(
        [
            {
                "title": "Tenant isolation in retrieval",
                "invariant": "Filter by tenant before ranking.",
                "impact_level": "high",
                "code_anchors": [{"path": "retrieval/rerank.py", "lineno": 10}],
                "development_traces": [
                    {
                        "provider": "claude_code",
                        "locator": "x.jsonl:4",
                        "relevance": "authored the filter",
                        "link_confidence": "hand_verified",
                        "segment_ids": ["seg0", "seg2"],
                    }
                ],
            }
        ]
    )
    proposals = parse_proposals(json.dumps({"result": inner}))
    assert proposals[0].development_traces[0].segment_ids == ("seg0", "seg2")


def test_parse_proposals_drops_items_without_title_or_anchor():
    inner = json.dumps(
        [
            {"title": "", "code_anchors": [{"path": "x.py", "lineno": 1}]},  # no title
            {"title": "No anchor", "code_anchors": []},  # no verifiable anchor
        ]
    )
    assert parse_proposals(json.dumps({"result": inner})) == []


def test_parse_proposals_handles_garbage():
    assert parse_proposals("not json at all") == []
    assert parse_proposals(json.dumps({"result": "no array in here"})) == []
    assert parse_proposals(json.dumps({"result": "[}"})) == []


def test_parse_proposals_normalizes_bad_impact_and_confidence():
    inner = json.dumps(
        [
            {
                "title": "Something",
                "invariant": "hold this",
                "impact_level": "catastrophic",  # not a valid level
                "code_anchors": [{"path": "x.py", "lineno": 1}],
                "development_traces": [{"provider": "claude_code", "locator": "y.jsonl:2", "link_confidence": "vibes"}],
            }
        ]
    )
    proposals = parse_proposals(json.dumps({"result": inner}))
    assert proposals[0].impact_level == "medium"  # normalized
    assert proposals[0].development_traces[0].link_confidence == "heuristic"  # normalized


def test_create_analyst_defaults_to_deterministic(monkeypatch):
    monkeypatch.delenv("LEDGER_ANALYST", raising=False)
    assert isinstance(create_analyst(), DeterministicAnalyst)


def test_create_analyst_selects_claude(monkeypatch):
    assert isinstance(create_analyst("claude"), ClaudeAnalyst)
    monkeypatch.setenv("LEDGER_ANALYST", "claude-code")
    assert isinstance(create_analyst(), ClaudeAnalyst)


def test_create_analyst_rejects_unknown_provider():
    with pytest.raises(ValueError):
        create_analyst("gpt-9")
