from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Protocol


COACH_POLICY = """You are Ledger's ownership coach.
Help the developer understand the concept and debug path without giving the patch.
Return a concise answer with conceptual explanation, one diagnostic question, and one suggested observation.
Never include code blocks, diffs, file edits, replacement lines, or direct patch instructions.
"""

DISALLOWED_TOOLS = "Bash,Read,Edit,Write,WebFetch,Grep,Glob,NotebookEdit,mcp__*"

# Coach is Claude-only (ADR-0004): the defining property is enforced withholding
# via `--disallowedTools`. The only choice the user makes is which Claude model
# answers — a cost/quality dial, never a provider switch.
COACH_MODELS = ("haiku", "sonnet", "opus")
DEFAULT_COACH_MODEL = "sonnet"


class Coach(Protocol):
    def build_prompt(
        self,
        *,
        topic_title: str,
        task: str,
        test_output: str,
        question: str,
    ) -> str: ...

    def ask(self, *, topic_title: str, task: str, test_output: str, question: str) -> str: ...


@dataclass(frozen=True)
class BaseCliCoach:
    timeout_seconds: int = 45

    def build_command(self) -> list[str]:
        raise NotImplementedError

    def build_prompt(
        self,
        *,
        topic_title: str,
        task: str,
        test_output: str,
        question: str,
    ) -> str:
        return "\n".join(
            [
                COACH_POLICY,
                f"Topic: {topic_title}",
                f"Task: {task}",
                "Observed failing test output:",
                test_output[-4000:],
                f"Developer question: {question}",
                "Answer using only conceptual guidance, a diagnostic question, and a suggested observation.",
            ]
        )

    def extract_result(self, stdout: str) -> str:
        return stdout

    def ask(self, *, topic_title: str, task: str, test_output: str, question: str) -> str:
        command = self.build_command()
        try:
            proc = subprocess.run(
                command,
                input=self.build_prompt(
                    topic_title=topic_title,
                    task=task,
                    test_output=test_output,
                    question=question,
                ),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError:
            return f"Coach unavailable: `{command[0]}` is not installed or is not on PATH."
        if proc.returncode != 0:
            return f"Coach unavailable: {proc.stderr.strip() or proc.stdout.strip()}"
        result = self.extract_result(proc.stdout)
        if "```" in result:
            return "I can explain the concept and ask diagnostic questions, but I cannot provide code or a patch."
        return result.strip()


@dataclass(frozen=True)
class ClaudeCoach(BaseCliCoach):
    binary: str = "claude"
    model_id: str = DEFAULT_COACH_MODEL
    timeout_seconds: int = 45

    def build_command(self) -> list[str]:
        return [
            self.binary,
            "-p",
            "--model",
            self.model_id,
            "--output-format",
            "json",
            "--append-system-prompt",
            COACH_POLICY,
            "--disallowedTools",
            DISALLOWED_TOOLS,
        ]

    def extract_result(self, stdout: str) -> str:
        try:
            payload = json.loads(stdout)
            return payload.get("result") or stdout
        except json.JSONDecodeError:
            return stdout


def create_coach(model: str | None = None) -> Coach:
    selected = (model or os.environ.get("LEDGER_COACH_MODEL") or DEFAULT_COACH_MODEL).lower()
    if selected not in COACH_MODELS:
        raise ValueError(f"unsupported coach model: {selected!r} (choose one of {', '.join(COACH_MODELS)})")
    return ClaudeCoach(model_id=selected)
