"""Provider-adapter ingestion — transcript -> normalized session + trace segments.

The Claude Code adapter turns a `.jsonl` transcript into addressable prompt and
tool-call segments (the Agent trace's recall material). Prompts + tool calls only:
assistant thinking/text, tool results, and command output stay out.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.ingestion import ClaudeCodeAdapter, TraceSegment, claude_transcripts_dir


def test_claude_transcripts_dir_encodes_the_repo_path():
    # Claude Code names a repo's transcript folder by replacing every "/" and "." with "-".
    got = claude_transcripts_dir("/Users/x/Projects/docs-search-api")
    assert got == Path.home() / ".claude" / "projects" / "-Users-x-Projects-docs-search-api"
    # Dotted segments (e.g. a ".worktrees" dir) also collapse to dashes.
    assert claude_transcripts_dir("/a/.wt/b").name == "-a--wt-b"


def _write_transcript(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    return path


def test_segments_extract_prompts_and_tool_calls_in_order(tmp_path):
    transcript = _write_transcript(
        tmp_path,
        [
            {
                "type": "user",
                "sessionId": "s1",
                "cwd": "/repo",
                "message": {"role": "user", "content": "Filter candidates by tenant before rerank."},
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "should be skipped"},
                        {"type": "text", "text": "also skipped"},
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "retrieval/rerank.py"}},
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "retrieval/rerank.py"}},
                        {"type": "tool_use", "name": "Bash", "input": {"command": "python -m pytest"}},
                    ],
                },
            },
            # A tool_result-only user turn is NOT a prompt.
            {
                "type": "user",
                "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
            },
        ],
    )

    event = ClaudeCodeAdapter()._read_jsonl_session(transcript)
    segments = [TraceSegment.from_dict(s) for s in event.payload["segments"]]

    kinds = [(s.kind, s.tool, s.target) for s in segments]
    assert kinds == [
        ("prompt", None, None),
        ("tool_call", "Read", "retrieval/rerank.py"),
        ("tool_call", "Edit", "retrieval/rerank.py"),
        ("tool_call", "Bash", "python -m pytest"),
    ]
    # Stable, transcript-order ids so a citation resolves to exactly one segment.
    assert [s.id for s in segments] == ["seg0", "seg1", "seg2", "seg3"]
    assert segments[0].text == "Filter candidates by tenant before rerank."


def test_meta_user_strings_and_oversized_prompts_are_filtered(tmp_path):
    long_prompt = "x" * 400
    transcript = _write_transcript(
        tmp_path,
        [
            {"type": "user", "cwd": "/repo", "message": {"role": "user", "content": "<command-name>/foo</command-name>"}},
            {"type": "user", "message": {"role": "user", "content": long_prompt}},
        ],
    )

    event = ClaudeCodeAdapter()._read_jsonl_session(transcript)
    segments = [TraceSegment.from_dict(s) for s in event.payload["segments"]]

    # The meta `<...>` string is dropped; the long prompt is kept but truncated.
    assert len(segments) == 1
    assert segments[0].kind == "prompt"
    assert len(segments[0].text) <= 280
    assert segments[0].text.endswith("…")
