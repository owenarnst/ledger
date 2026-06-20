from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


DEFAULT_PROVIDER = "claude_code"
SUPPORTED_PROVIDERS = {DEFAULT_PROVIDER, "codex", "git"}


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
        if not cwd:
            return None
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
                "link_confidence": "heuristic",
            },
        )

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


class ClaudeCodeAdapter(BaseProviderAdapter):
    def __init__(self) -> None:
        super().__init__(DEFAULT_PROVIDER)


class CodexAdapter(BaseProviderAdapter):
    def __init__(self) -> None:
        super().__init__("codex")


class GitAdapter(BaseProviderAdapter):
    def __init__(self) -> None:
        super().__init__("git")


def adapter_for(provider: str | None) -> ProviderAdapter:
    selected = provider or DEFAULT_PROVIDER
    if selected == DEFAULT_PROVIDER:
        return ClaudeCodeAdapter()
    if selected == "codex":
        return CodexAdapter()
    if selected == "git":
        return GitAdapter()
    raise ValueError(f"unsupported provider: {selected}")
