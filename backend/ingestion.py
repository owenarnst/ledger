from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


DEFAULT_PROVIDER = "claude_code"
SUPPORTED_PROVIDERS = {DEFAULT_PROVIDER, "git"}

# Bound the per-session segment list and prompt length so the Agent trace stays a
# "hunk" (Receipt L2), not a transcript dump, and the analyst prompt stays small.
MAX_SEGMENTS_PER_SESSION = 200
MAX_PROMPT_CHARS = 280


@dataclass(frozen=True)
class TraceSegment:
    """One addressable unit of an agent session: a user prompt or a tool call.

    The unit the Topic Analyst cites and the expanded "Agent trace" renders. Ids
    are stable within a session (``seg0``, ``seg1`` ...) so a citation resolves
    back to exactly one segment. Prompts + tool calls only — never tool results,
    command output, or file contents.
    """

    id: str
    kind: str               # "prompt" | "tool_call"
    text: str = ""          # prompt text (trimmed); empty for tool calls
    tool: str | None = None  # tool name for tool calls
    target: str | None = None  # file path, short command, or pattern
    line: int = 0           # 1-based source line in the transcript

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "tool": self.tool,
            "target": self.target,
            "line": self.line,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TraceSegment":
        return cls(
            id=str(raw.get("id") or ""),
            kind=str(raw.get("kind") or ""),
            text=str(raw.get("text") or ""),
            tool=raw.get("tool"),
            target=raw.get("target"),
            line=int(raw.get("line") or 0),
        )


@dataclass(frozen=True)
class IngestionEvent:
    provider: str
    event_type: str
    cwd: str
    branch: str | None = None
    head_sha: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(Protocol):
    provider: str

    def normalize(self, raw: dict[str, Any]) -> IngestionEvent: ...
    def read_sessions(self, root: str | Path) -> list[IngestionEvent]: ...


@dataclass(frozen=True)
class BaseProviderAdapter:
    provider: str

    def normalize(self, raw: dict[str, Any]) -> IngestionEvent:
        return IngestionEvent(
            provider=self.provider,
            event_type=str(raw["event_type"]),
            cwd=str(raw["cwd"]),
            branch=raw.get("branch"),
            head_sha=raw.get("head_sha"),
            payload={
                "changed_files": list(raw.get("changed_files") or []),
                "source": raw.get("source"),
                "session_id": raw.get("session_id"),
                "source_path": raw.get("source_path"),
                "tool_sequence": list(raw.get("tool_sequence") or []),
                "segments": list(raw.get("segments") or []),
                "link_confidence": raw.get("link_confidence"),
            },
        )

    def read_sessions(self, root: str | Path) -> list[IngestionEvent]:
        root_path = Path(root).expanduser()
        paths = [root_path] if root_path.is_file() else sorted(root_path.rglob("*.jsonl"))
        events: list[IngestionEvent] = []
        for path in paths:
            event = self._read_jsonl_session(path)
            if event:
                events.append(event)
        return events

    def _read_jsonl_session(self, path: Path) -> IngestionEvent | None:
        session_id: str | None = None
        cwd: str | None = None
        changed_files: list[str] = []
        tool_sequence: list[str] = []
        raw_segments: list[dict[str, Any]] = []
        source_line = 0
        with path.open(errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_id = session_id or self._session_id_from_record(record)
                cwd = cwd or record.get("cwd") or record.get("workspace") or record.get("repo_path")
                tools = self._tool_calls_from_record(record)
                if tools:
                    source_line = line_number
                for name, file_path in tools:
                    tool_sequence.append(f"{name} {file_path}")
                    if file_path not in changed_files:
                        changed_files.append(file_path)
                raw_segments.extend(self._segments_from_record(record, line_number))
        if not cwd:
            return None
        # Stable ids assigned in transcript order so a cited locator resolves to
        # exactly one segment.
        segments = [
            TraceSegment(
                id=f"seg{index}",
                kind=raw["kind"],
                text=raw.get("text", ""),
                tool=raw.get("tool"),
                target=raw.get("target"),
                line=raw.get("line", 0),
            ).as_dict()
            for index, raw in enumerate(raw_segments[:MAX_SEGMENTS_PER_SESSION])
        ]
        return IngestionEvent(
            provider=self.provider,
            event_type="SessionTranscript",
            cwd=str(cwd),
            payload={
                "changed_files": changed_files,
                "source": "jsonl",
                "session_id": session_id or path.stem,
                "source_path": f"{path}:{source_line or 1}",
                "tool_sequence": tool_sequence,
                "segments": segments,
                "link_confidence": "heuristic",
            },
        )

    def _segments_from_record(self, record: dict[str, Any], line: int) -> list[dict[str, Any]]:
        """Extract prompt + tool-call segments from one transcript record.

        Prompts + tool calls only: assistant ``thinking``/``text`` blocks, user
        ``tool_result`` payloads, and command/tool output are deliberately skipped.
        """
        segments: list[dict[str, Any]] = []
        message = record.get("message")
        role = record.get("type") or record.get("role")
        if isinstance(message, dict):
            role = role or message.get("role")
            content = message.get("content")
            if isinstance(content, str):
                text = _clean_prompt(content)
                if text and role in ("user", None):
                    segments.append({"kind": "prompt", "text": text, "line": line})
            elif isinstance(content, list):
                for item in content:
                    segment = self._tool_call_segment(item, line)
                    if segment:
                        segments.append(segment)
        for call in record.get("tool_calls") or record.get("tools") or []:
            segment = self._tool_call_segment(call, line)
            if segment:
                segments.append(segment)
        return segments

    @staticmethod
    def _tool_call_segment(item: Any, line: int) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        name = item.get("name") or item.get("tool")
        if not name:
            # tool_result / text / thinking blocks carry no tool name -> skip.
            return None
        item_type = item.get("type")
        if item_type is not None and item_type not in ("tool_use", "function_call", "tool"):
            return None
        payload = item.get("input") if isinstance(item.get("input"), dict) else item
        target = _tool_target(str(name), payload)
        return {"kind": "tool_call", "tool": str(name), "target": target, "line": line}

    def _session_id_from_record(self, record: dict[str, Any]) -> str | None:
        value = record.get("session_id") or record.get("sessionId") or record.get("conversation_id")
        return str(value) if value else None

    def _tool_calls_from_record(self, record: dict[str, Any]) -> list[tuple[str, str]]:
        calls: list[tuple[str, str]] = []
        for call in record.get("tool_calls") or record.get("tools") or []:
            extracted = self._tool_call_tuple(call)
            if extracted:
                calls.append(extracted)
        message = record.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    extracted = self._tool_call_tuple(item)
                    if extracted:
                        calls.append(extracted)
        return calls

    @staticmethod
    def _tool_call_tuple(call: Any) -> tuple[str, str] | None:
        if not isinstance(call, dict):
            return None
        name = call.get("name") or call.get("tool") or call.get("type")
        if not name:
            return None
        payload = call.get("input") if isinstance(call.get("input"), dict) else call
        file_path = payload.get("file_path") or payload.get("path") or payload.get("filepath")
        if not file_path:
            return None
        return str(name), str(file_path)


# Strings that arrive as "user" content but are harness/meta noise, not prompts.
_META_PROMPT_PREFIXES = ("<", "[Request interrupted", "Caveat:")


def _clean_prompt(content: str) -> str:
    text = " ".join(content.split())
    if not text or text.startswith(_META_PROMPT_PREFIXES):
        return ""
    if len(text) > MAX_PROMPT_CHARS:
        text = text[: MAX_PROMPT_CHARS - 1].rstrip() + "…"
    return text


def _tool_target(name: str, payload: dict[str, Any]) -> str | None:
    """A short, content-free descriptor: the file touched, command, or pattern."""
    file_path = payload.get("file_path") or payload.get("path") or payload.get("filepath")
    if file_path:
        return str(file_path)
    if name in ("Bash", "BashOutput"):
        return _short_command(str(payload.get("command") or ""))
    pattern = payload.get("pattern") or payload.get("query")
    if pattern:
        return str(pattern)[:60]
    return None


def _short_command(command: str) -> str | None:
    text = " ".join(command.split())
    if not text:
        return None
    return text[:79] + "…" if len(text) > 80 else text


def claude_transcripts_dir(repo_path: str | Path) -> Path:
    """The ``~/.claude/projects`` directory Claude Code writes a repo's transcripts to.

    Claude Code derives the folder name from the working directory by replacing every
    ``/`` and ``.`` with ``-`` — e.g. ``/Users/x/Projects/docs-search-api`` lands in
    ``~/.claude/projects/-Users-x-Projects-docs-search-api/``. The Agent trace reads
    these real session transcripts directly; there is no committed transcript fixture.
    """
    encoded = str(Path(repo_path).expanduser().resolve()).replace("/", "-").replace(".", "-")
    return Path.home() / ".claude" / "projects" / encoded


class ClaudeCodeAdapter(BaseProviderAdapter):
    def __init__(self) -> None:
        super().__init__(DEFAULT_PROVIDER)


class GitAdapter(BaseProviderAdapter):
    def __init__(self) -> None:
        super().__init__("git")


def adapter_for(provider: str | None) -> ProviderAdapter:
    selected = provider or DEFAULT_PROVIDER
    if selected == DEFAULT_PROVIDER:
        return ClaudeCodeAdapter()
    if selected == "git":
        return GitAdapter()
    raise ValueError(f"unsupported provider: {selected}")
