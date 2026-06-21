"""Agentic worklist discovery — the Topic Analyst (ADR-0002).

Discovery and verification are separate. This module owns *discovery*: turning a
deterministically-indexed repository into an ordered worklist of Topic proposals.
The Claude Code Topic Analyst does the discovering; deterministic code
(:mod:`backend.verifier`) resolves every cited locator before a proposal becomes a
persisted fact. Nothing here mints checks, mutants, or evidence — it only proposes.

Two analysts implement one contract:

- :class:`DeterministicAnalyst` — no network, the CI default and the honest
  fallback. It reuses the recall index (:mod:`backend.extraction`) to gate and
  order candidates and cites each anchor's own location. It is a *heuristic*
  analyst: its audit ``model_id`` is ``"deterministic"`` and the repository tags
  its worklist accordingly, so it is never presented as equivalent agent analysis.
- :class:`ClaudeAnalyst` — rides the user's own ``claude -p``, mirroring the
  Coach/Labeler subprocess pattern, but with scoped read-only ``Read``/``Grep``/
  ``Glob`` *allowed* (and edit/write, arbitrary ``Bash``, web, and unrelated
  ``mcp__*`` denied) because investigating the repository is its purpose. It is
  scoped to the enrolled repo by running with ``cwd=repo_path``. It falls back to
  the deterministic analyst on any failure so discovery never breaks.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, TextIO

from .extraction import Candidate, blast_score, extract_candidates
from .ingestion import TraceSegment


# --------------------------------------------------------------------------- #
# Minimum Topic proposal contract (ADR-0002)
# --------------------------------------------------------------------------- #

VALID_IMPACT_LEVELS = ("high", "medium", "low")
VALID_LINK_CONFIDENCE = ("exact", "heuristic", "hand_verified")

# Prompt/contract version recorded with every analysis run for auditability.
ANALYSIS_SCHEMA_VERSION = "topic-proposal-v1"

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class CodeAnchorCitation:
    """A cited code locator the verifier must resolve before it is trusted."""

    path: str                 # repo-relative
    lineno: int
    end_lineno: int | None
    relevance: str            # short, grounded relevance statement


@dataclass(frozen=True)
class TraceCitation:
    """A cited development-trace locator (provider-labeled)."""

    provider: str
    locator: str              # session source_path ("x.jsonl:42") or session id
    relevance: str
    link_confidence: str      # "exact" | "heuristic" | "hand_verified"
    # The specific prompt/tool-call segment ids the analyst judged relevant (the
    # Receipt L2 "prompt + tool-call hunk"). Verified against the session before
    # they are persisted; unsupported ids are dropped.
    segment_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TopicProposal:
    """One analyst-proposed worklist item. List order == priority."""

    title: str                       # durable obligation, never a raw symbol
    maintenance_obligation: str
    invariant: str
    impact_level: str                # high | medium | low
    impact_consequence: str          # grounded failure-consequence
    priority_rationale: str          # grounded internal ordering rationale
    code_anchors: tuple[CodeAnchorCitation, ...]
    development_traces: tuple[TraceCitation, ...] = ()


@dataclass(frozen=True)
class DiscoveryResult:
    """An analyst's worklist plus the model that *actually* produced it.

    The effective ``model_id`` propagates honestly: when :class:`ClaudeAnalyst`
    falls back, this reports ``"deterministic"`` rather than relabeling heuristic
    candidates as agent analysis (ADR-0002 fallback guarantee).
    """

    proposals: list[TopicProposal]
    model_id: str
    raw_output: str = ""  # the analyst's raw stdout, recorded for audit (empty for deterministic)
    fallback_reason: str | None = None


@dataclass(frozen=True)
class TraceLocator:
    """An available development trace the analyst may cite (recall material).

    Carries the session's addressable prompt/tool-call segments so the analyst can
    cite the specific ones relevant to a Topic, and the verifier can resolve them.
    """

    provider: str
    session_id: str
    source_path: str | None
    summary: str = ""
    segments: tuple[TraceSegment, ...] = ()


@dataclass(frozen=True)
class AnalystIndex:
    """Deterministically-indexed recall material handed to the analyst.

    Candidate anchors are recall-oriented seeds, **not** a worklist gate — the
    analyst decides membership and order. Traces are the development-trace
    locators the analyst is allowed to cite.
    """

    candidates: tuple[Candidate, ...] = ()
    traces: tuple[TraceLocator, ...] = ()

    @classmethod
    def from_repo(
        cls, repo_path: str | Path, traces: tuple[TraceLocator, ...] = ()
    ) -> "AnalystIndex":
        return cls(candidates=tuple(extract_candidates(repo_path)), traces=tuple(traces))

    def digest(self) -> str:
        """A compact text seed describing the recall index for the LLM prompt."""
        lines = ["Candidate decision anchors (recall seeds — you decide which matter):"]
        for c in self.candidates:
            a = c.anchor
            lines.append(
                f"- {a.file}:{a.lineno}-{a.end_lineno} {a.symbol} "
                f"[{a.risk_class}; signals={','.join(a.signals) or 'none'}; "
                f"callers={c.caller_count}; trail={c.trail.strength}]"
            )
        if self.traces:
            lines.append("")
            lines.append(
                "Available development traces (cite the locator + the relevant segment_ids):"
            )
            for t in self.traces:
                where = t.source_path or t.session_id
                lines.append(f"- [{t.provider}] {where} (session {t.session_id}) {t.summary}".rstrip())
                for s in t.segments:
                    if s.kind == "prompt":
                        lines.append(f'    {s.id} PROMPT "{s.text}"')
                    else:
                        target = f" {s.target}" if s.target else ""
                        lines.append(f"    {s.id} TOOL {s.tool}{target}")
        return "\n".join(lines)


class Analyst(Protocol):
    model_id: str

    def discover(
        self,
        repo_path: str | Path,
        index: AnalystIndex,
        progress: ProgressCallback | None = None,
    ) -> DiscoveryResult: ...


# --------------------------------------------------------------------------- #
# Deterministic text synthesis (folded in from the retired labeler)
# --------------------------------------------------------------------------- #

# Coarse, defendable concept categories derived from (risk_class, signals). These
# name a *kind* of decision, not a fabricated domain claim, and always travel next
# to the grounded symbol so the mapping is auditable.
def _concept(risk: str, signals: tuple[str, ...]) -> str:
    s = set(signals)
    if risk == "persistence":
        return "Tenant isolation"
    if risk == "external_api":
        return "External-call policy"
    if "ordering" in s:
        return "Deterministic ordering"
    if "membership" in s:
        return "Duplicate resolution"
    if "bounding" in s:
        return "Bounded window"
    if "threshold" in s:
        return "Confidence threshold"
    if "filter" in s:
        return "Candidate selection"
    if "branch" in s:
        return "Control-flow decision"
    return "Decision"


def _first_sentence(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        return ""
    match = re.search(r"(.+?[.!?])(\s|$)", text)
    return match.group(1) if match else text


# Risk class -> categorical impact. Persistence/auth and external calls are the
# irreversible/high-blast paths; ranking/retrieval are medium; the rest are low.
_IMPACT_BY_RISK = {
    "persistence": "high",
    "external_api": "high",
    "ranking": "medium",
    "retrieval": "medium",
    "general": "low",
}


def _impact_for(risk_class: str) -> str:
    return _IMPACT_BY_RISK.get(risk_class, "low")


def _consequence_for(risk_class: str, concept: str) -> str:
    if risk_class == "persistence":
        return "If this decision regresses, one tenant's data can leak to another."
    if risk_class == "external_api":
        return "If this decision regresses, external calls can hang, retry wrongly, or fail unsafely."
    if risk_class == "ranking":
        return "If this decision regresses, ranked results change order or quality silently."
    if risk_class == "retrieval":
        return "If this decision regresses, retrieved context is wrong, truncated, or duplicated."
    return f"If this {concept.lower()} decision regresses, downstream behaviour changes silently."


def _trail_phrase(strength: str) -> str:
    if strength == "absent":
        return "no mention in ADRs, CONTEXT, README, or comments"
    if strength == "mentioned":
        return "named in the docs but no decision record explains the choice"
    if strength == "commented":
        return "explained only in a co-located comment"
    return "recorded in a decision document"


def _target_matches(target: str | None, anchor_file: str) -> bool:
    """A tool-call target references the anchor file (abs or repo-relative path)."""
    if not target:
        return False
    target = target.replace("\\", "/")
    return target == anchor_file or target.endswith("/" + anchor_file)


def _file_scoped_traces(
    anchor_file: str, traces: tuple[TraceLocator, ...]
) -> tuple[TraceCitation, ...]:
    """Deterministic, file-grounded trace selection (the honest fallback).

    The Claude analyst selects relevant prompts/tool-calls by judgement; with no
    network the fallback still surfaces the tool-call segments whose target is the
    Topic's anchor file, so the Agent trace degrades gracefully instead of vanishing.
    """
    citations: list[TraceCitation] = []
    for trace in traces:
        ids = [
            s.id
            for s in trace.segments
            if s.kind == "tool_call" and _target_matches(s.target, anchor_file)
        ]
        if ids:
            citations.append(
                TraceCitation(
                    provider=trace.provider,
                    locator=trace.source_path or trace.session_id,
                    relevance=f"Session touched {anchor_file}.",
                    link_confidence="heuristic",
                    segment_ids=tuple(ids),
                )
            )
    return tuple(citations)


# --------------------------------------------------------------------------- #
# DeterministicAnalyst — CI default and honest fallback
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class DeterministicAnalyst:
    """Heuristic worklist proposer. Reproducible, no network.

    Applies the load-bearing-and-untrailed gate and blast-radius ordering that
    used to live in the repository layer, then emits contract-valid proposals
    whose only citation is each anchor's own location (which always verifies).
    """

    model_id: str = "deterministic"

    def discover(
        self,
        repo_path: str | Path,
        index: AnalystIndex,
        progress: ProgressCallback | None = None,
    ) -> DiscoveryResult:
        surfaced = sorted(
            (c for c in index.candidates if c.surfaced), key=lambda c: -blast_score(c)
        )
        return DiscoveryResult(
            [self._proposal(c, index.traces) for c in surfaced], self.model_id
        )

    @staticmethod
    def _proposal(candidate: Candidate, traces: tuple[TraceLocator, ...] = ()) -> TopicProposal:
        anchor = candidate.anchor
        concept = _concept(anchor.risk_class, anchor.signals)
        leaf = anchor.symbol.split(".")[-1]
        doc_sentence = _first_sentence(anchor.docstring)

        obligation = doc_sentence or (
            f"{anchor.kind.capitalize()} `{anchor.symbol}` in {anchor.file} "
            f"encodes a {concept.lower()} decision that must be preserved."
        )
        invariant = doc_sentence or (
            f"The behaviour {anchor.symbol} encodes must be preserved across changes."
        )
        callers = f"{candidate.caller_count} site{'s' if candidate.caller_count != 1 else ''}"
        rationale = (
            f"On the {anchor.risk_class.replace('_', ' ')} path, referenced by {callers}; "
            f"{_trail_phrase(candidate.trail.strength)}."
        )
        relevance = f"Encodes the {concept.lower()} decision at {anchor.symbol}."
        return TopicProposal(
            title=f"{concept} — {leaf}",
            maintenance_obligation=obligation,
            invariant=invariant,
            impact_level=_impact_for(anchor.risk_class),
            impact_consequence=_consequence_for(anchor.risk_class, concept),
            priority_rationale=rationale,
            code_anchors=(
                CodeAnchorCitation(
                    path=anchor.file,
                    lineno=anchor.lineno,
                    end_lineno=anchor.end_lineno,
                    relevance=relevance,
                ),
            ),
            development_traces=_file_scoped_traces(anchor.file, traces),
        )


# --------------------------------------------------------------------------- #
# ClaudeAnalyst — agentic discovery via `claude -p`
# --------------------------------------------------------------------------- #

ANALYST_POLICY = """You are Ledger's Topic Analyst.
Investigate this repository with the read-only tools you are given (Read, Grep,
Glob) to find durable maintenance obligations a future maintainer must preserve.
Combine related decision anchors into one durable Topic, discard syntactic
trivia, and order the worklist by priority (most important first).

Ground every claim in real sources. Cite code_anchors by repo-relative path and
line number that actually exist. Cite development_traces ONLY using the trace
locators provided to you, and in segment_ids list ONLY the seg ids shown under
that trace — the specific prompts and tool calls that drove this Topic's
decision. Never invent a citation. You may report that you found no rationale in
your searched scope, but never assert an uncited fact.

Respond with ONLY a JSON array of Topic proposals, each:
{"title","maintenance_obligation","invariant","impact_level","impact_consequence",
 "priority_rationale","code_anchors":[{"path","lineno","end_lineno","relevance"}],
 "development_traces":[{"provider","locator","relevance","link_confidence","segment_ids":["seg1"]}]}
impact_level is "high"|"medium"|"low"; link_confidence is "exact"|"heuristic"|"hand_verified".
Never include code blocks, patches, or replacement lines.
"""

# Scoped read-only investigation is the analyst's purpose (ADR-0002). This is the
# inverse of the Coach/Labeler boundary: Read/Grep/Glob are allowed here, while
# mutation, arbitrary shell, web, and unrelated MCP access stay denied.
ALLOWED_TOOLS = "Read,Grep,Glob"
DISALLOWED_TOOLS = "Edit,Write,Bash,WebFetch,NotebookEdit,mcp__*"


@dataclass(frozen=True)
class ClaudeAnalyst:
    """Agentic analyst: rides ``claude -p`` with scoped read-only tools.

    Falls back to the deterministic analyst on any failure so discovery never
    breaks the extraction pipeline. There is no short wall-clock deadline:
    stream activity resets an inactivity watchdog, allowing long investigations
    to finish while still recovering from a genuinely stalled CLI process.
    """

    binary: str = "claude"
    inactivity_timeout_seconds: float = 600
    model_id: str = "opus"
    effort: str = "high"
    fallback: DeterministicAnalyst = field(default_factory=DeterministicAnalyst)

    def build_command(self) -> list[str]:
        return [
            self.binary,
            "-p",
            "--model",
            self.model_id,
            "--effort",
            self.effort,
            "--output-format",
            "stream-json",
            "--verbose",
            "--append-system-prompt",
            ANALYST_POLICY,
            "--allowedTools",
            ALLOWED_TOOLS,
            "--disallowedTools",
            DISALLOWED_TOOLS,
        ]

    def build_prompt(self, repo_path: str | Path, index: AnalystIndex) -> str:
        return "\n".join(
            [
                ANALYST_POLICY,
                f"Repository root: {repo_path}",
                "",
                index.digest(),
                "",
                "Return the ordered worklist as a JSON array now.",
            ]
        )

    def discover(
        self,
        repo_path: str | Path,
        index: AnalystIndex,
        progress: ProgressCallback | None = None,
    ) -> DiscoveryResult:
        repo_path = Path(repo_path)
        _emit(progress, f"Starting Claude Topic Analyst ({self.model_id}, {self.effort} effort)")
        try:
            proc = subprocess.Popen(
                self.build_command(),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                cwd=str(repo_path),  # scope Read/Grep/Glob to the enrolled repo
                bufsize=1,
            )
        except (FileNotFoundError, OSError) as exc:
            return self._fallback(repo_path, index, f"Claude CLI could not start: {exc}", progress)

        try:
            assert proc.stdin is not None
            proc.stdin.write(self.build_prompt(repo_path, index))
            proc.stdin.close()
            final_event, effective_model, stderr = self._consume_stream(
                proc, repo_path=repo_path, progress=progress
            )
        except KeyboardInterrupt:
            proc.terminate()
            proc.wait()
            raise
        except (BrokenPipeError, OSError) as exc:
            proc.kill()
            proc.wait()
            return self._fallback(
                repo_path, index, f"Claude stream failed: {exc}", progress
            )

        if final_event is None:
            reason = _last_nonempty_line(stderr) or "Claude returned no final result event"
            return self._fallback(repo_path, index, reason, progress)
        if proc.returncode != 0 or final_event.get("is_error"):
            reason = str(final_event.get("result") or _last_nonempty_line(stderr) or "Claude failed")
            return self._fallback(repo_path, index, reason, progress)

        final_output = json.dumps(final_event)
        proposals = parse_proposals(final_output)
        if not proposals:
            return self._fallback(
                repo_path, index, "Claude returned no valid Topic proposals", progress
            )
        _emit(progress, f"Claude proposed {len(proposals)} grounded Topic(s)")
        return DiscoveryResult(proposals, effective_model, raw_output=final_output)

    def _consume_stream(
        self,
        proc: subprocess.Popen[str],
        *,
        repo_path: Path,
        progress: ProgressCallback | None,
    ) -> tuple[dict[str, object] | None, str, str]:
        """Consume Claude stream-json without exposing reasoning or source contents."""
        assert proc.stdout is not None and proc.stderr is not None
        messages: queue.Queue[tuple[str, str | None]] = queue.Queue()
        for source, stream in (("stdout", proc.stdout), ("stderr", proc.stderr)):
            threading.Thread(
                target=_read_lines,
                args=(source, stream, messages),
                daemon=True,
            ).start()

        open_streams = {"stdout", "stderr"}
        final_event: dict[str, object] | None = None
        effective_model = self.model_id
        stderr_lines: list[str] = []
        last_activity = time.monotonic()
        emitted: set[str] = set()

        while open_streams:
            remaining = self.inactivity_timeout_seconds - (time.monotonic() - last_activity)
            if remaining <= 0:
                proc.kill()
                proc.wait()
                message = (
                    "Claude produced no output for "
                    f"{self.inactivity_timeout_seconds:g} seconds"
                )
                _emit(progress, message)
                return None, effective_model, message
            try:
                source, line = messages.get(timeout=remaining)
            except queue.Empty:
                proc.kill()
                proc.wait()
                message = (
                    "Claude produced no output for "
                    f"{self.inactivity_timeout_seconds:g} seconds"
                )
                _emit(progress, message)
                return None, effective_model, message

            if line is None:
                open_streams.discard(source)
                continue
            last_activity = time.monotonic()
            if source == "stderr":
                stderr_lines.append(line.rstrip())
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "system" and event.get("model"):
                effective_model = str(event["model"])
            for message in _progress_messages(event, repo_path):
                if message not in emitted:
                    emitted.add(message)
                    _emit(progress, message)
            if event.get("type") == "result":
                final_event = event

        proc.wait()
        return final_event, effective_model, "\n".join(stderr_lines)

    def _fallback(
        self,
        repo_path: Path,
        index: AnalystIndex,
        reason: str,
        progress: ProgressCallback | None,
    ) -> DiscoveryResult:
        # Honest fallback: report the deterministic model, never relabel
        # heuristic candidates as agent analysis (ADR-0002).
        clean_reason = " ".join(reason.split()) or "unknown Claude failure"
        _emit(progress, f"Falling back to deterministic analysis: {clean_reason}")
        result = self.fallback.discover(repo_path, index, progress=progress)
        return DiscoveryResult(
            result.proposals,
            result.model_id,
            raw_output=json.dumps({"fallback_reason": clean_reason}),
            fallback_reason=clean_reason,
        )


def _read_lines(
    source: str,
    stream: TextIO,
    messages: queue.Queue[tuple[str, str | None]],
) -> None:
    try:
        for line in stream:
            messages.put((source, line))
    finally:
        messages.put((source, None))


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _last_nonempty_line(value: str) -> str:
    return next((line.strip() for line in reversed(value.splitlines()) if line.strip()), "")


def _progress_messages(event: dict[str, object], repo_path: Path) -> list[str]:
    """Return safe activity summaries; never emit model reasoning or file contents."""
    if event.get("type") == "system" and event.get("subtype") == "init":
        model = event.get("model")
        return [f"Claude session initialized ({model})" if model else "Claude session initialized"]
    if event.get("type") == "result":
        turns = event.get("num_turns")
        return [f"Claude analysis finished ({turns} turn(s))" if turns else "Claude analysis finished"]
    if event.get("type") != "assistant":
        return []
    message = event.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    summaries: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        tool = str(block.get("name") or "")
        inputs = block.get("input")
        inputs = inputs if isinstance(inputs, dict) else {}
        if tool == "Read":
            summaries.append(f"Reading {_display_path(inputs.get('file_path'), repo_path)}")
        elif tool == "Grep":
            summaries.append(f"Searching {_display_path(inputs.get('path'), repo_path)} with Grep")
        elif tool == "Glob":
            summaries.append(f"Scanning {_display_path(inputs.get('path'), repo_path)} with Glob")
    return summaries


def _display_path(value: object, repo_path: Path) -> str:
    if not value:
        return "repository"
    path = Path(str(value))
    try:
        return str(path.resolve().relative_to(repo_path.resolve()))
    except ValueError:
        return path.name or "repository"


def parse_proposals(stdout: str) -> list[TopicProposal]:
    """Defensively parse a ``claude -p --output-format json`` worklist.

    Returns an empty list on any malformed payload (caller falls back). Mirrors
    the labeler's defensive extraction: unwrap the ``result`` envelope, then pull
    the JSON array out of the text.
    """
    try:
        outer = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return []
    payload = outer.get("result", outer) if isinstance(outer, dict) else outer
    if isinstance(payload, str):
        match = re.search(r"\[.*\]", payload, re.DOTALL)
        if not match:
            return []
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(payload, list):
        return []

    proposals: list[TopicProposal] = []
    for item in payload:
        proposal = _coerce_proposal(item)
        if proposal is not None:
            proposals.append(proposal)
    return proposals


def _coerce_proposal(item: object) -> TopicProposal | None:
    if not isinstance(item, dict):
        return None
    title = str(item.get("title") or "").strip()
    anchors = _coerce_anchors(item.get("code_anchors"))
    if not title or not anchors:
        # A proposal with no title or no code anchor cannot become a verified Topic.
        return None
    impact = str(item.get("impact_level") or "medium").lower()
    if impact not in VALID_IMPACT_LEVELS:
        impact = "medium"
    obligation = str(item.get("maintenance_obligation") or item.get("invariant") or title)
    invariant = str(item.get("invariant") or obligation)
    return TopicProposal(
        title=title,
        maintenance_obligation=obligation,
        invariant=invariant,
        impact_level=impact,
        impact_consequence=str(item.get("impact_consequence") or ""),
        priority_rationale=str(item.get("priority_rationale") or ""),
        code_anchors=anchors,
        development_traces=_coerce_traces(item.get("development_traces")),
    )


def _coerce_anchors(raw: object) -> tuple[CodeAnchorCitation, ...]:
    if not isinstance(raw, list):
        return ()
    anchors: list[CodeAnchorCitation] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        lineno = _coerce_int(entry.get("lineno"))
        if not path or lineno is None:
            continue
        anchors.append(
            CodeAnchorCitation(
                path=path,
                lineno=lineno,
                end_lineno=_coerce_int(entry.get("end_lineno")),
                relevance=str(entry.get("relevance") or ""),
            )
        )
    return tuple(anchors)


def _coerce_traces(raw: object) -> tuple[TraceCitation, ...]:
    if not isinstance(raw, list):
        return ()
    traces: list[TraceCitation] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        locator = str(entry.get("locator") or "").strip()
        if not locator:
            continue
        confidence = str(entry.get("link_confidence") or "heuristic").lower()
        if confidence not in VALID_LINK_CONFIDENCE:
            confidence = "heuristic"
        raw_ids = entry.get("segment_ids")
        segment_ids = (
            tuple(str(s).strip() for s in raw_ids if str(s).strip())
            if isinstance(raw_ids, list)
            else ()
        )
        traces.append(
            TraceCitation(
                provider=str(entry.get("provider") or "claude_code"),
                locator=locator,
                relevance=str(entry.get("relevance") or ""),
                link_confidence=confidence,
                segment_ids=segment_ids,
            )
        )
    return tuple(traces)


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def create_analyst(provider: str | None = None) -> Analyst:
    selected = (provider or os.environ.get("LEDGER_ANALYST") or "deterministic").lower()
    if selected in {"deterministic", "none", "off"}:
        return DeterministicAnalyst()
    if selected in {"claude", "claude-code", "claude-print"}:
        return ClaudeAnalyst()
    raise ValueError(f"unsupported analyst: {selected}")
