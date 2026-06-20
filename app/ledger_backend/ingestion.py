from __future__ import annotations

from dataclasses import dataclass, field
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
            },
        )


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
