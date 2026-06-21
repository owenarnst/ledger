from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol

from .exercise_templates import DEFAULT_PLAN, VALID_DIFFICULTIES


class ExercisePlanGenerator(Protocol):
    provider: str

    def generate_plan(
        self,
        *,
        topic: dict[str, Any],
        revision: dict[str, Any],
        difficulty: str,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CliExercisePlanGenerator:
    provider: str = "claude"
    fallback_provider: str | None = None
    timeout_seconds: int = 45

    def generate_plan(
        self,
        *,
        topic: dict[str, Any],
        revision: dict[str, Any],
        difficulty: str,
    ) -> dict[str, Any]:
        selected = normalize_difficulty(difficulty)
        if selected == "hard":
            return fallback_plan(selected)
        prompt = build_generation_prompt(topic=topic, revision=revision, difficulty=selected)
        last_error: Exception | None = None
        for provider in generation_provider_order(self.provider, self.fallback_provider):
            try:
                response = run_generator_cli(provider, prompt, self.timeout_seconds)
                plan = parse_plan_json(response)
                return normalize_generated_plan(plan, difficulty=selected)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
        raise last_error or ValueError("exercise generator returned no plan")


def normalize_difficulty(difficulty: str | None) -> str:
    selected = (difficulty or "hard").lower()
    if selected not in VALID_DIFFICULTIES:
        raise ValueError(f"unsupported difficulty: {selected}")
    return selected


def fallback_plan(difficulty: str) -> dict[str, Any]:
    if difficulty == "easy":
        return {
            "template_id": "generated-easy-fallback",
            "difficulty": "easy",
            "steps": [
                {"type": "multiple_choice", "question_id": "tenant-filter-purpose"},
                {"type": "multiple_choice", "question_id": "tenant-filter-debug"},
            ],
            "questions": [
                {
                    "id": "tenant-filter-purpose",
                    "kind": "concept",
                    "prompt": "What should this function guarantee before returning documents?",
                    "choices": [
                        "Only requested-tenant documents are returned",
                        "All documents are returned unchanged",
                        "Documents are sorted by score",
                    ],
                    "correct_index": 0,
                    "rationale": "The invariant is tenant isolation.",
                },
                {
                    "id": "tenant-filter-debug",
                    "kind": "debugging",
                    "prompt": "Which complete implementation fixes the behavior?",
                    "choices": [
                        "def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:\n    return [doc for doc in documents if doc.tenant_id == tenant_id]",
                        "def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:\n    return list(documents)",
                        "def visible_documents_for_tenant(documents: list[Document], tenant_id: str) -> list[Document]:\n    return sorted(documents, key=lambda doc: doc.score, reverse=True)",
                    ],
                    "correct_index": 0,
                    "rationale": "The fix filters documents to the requested tenant instead of exposing every tenant.",
                },
            ],
        }
    plan = dict(DEFAULT_PLAN)
    plan["difficulty"] = difficulty
    plan["template_id"] = f"generated-{difficulty}-fallback"
    return plan


def generation_provider_order(primary: str, fallback: str | None) -> list[str]:
    providers = []
    for provider in [primary, fallback]:
        selected = (provider or "").lower()
        if selected and selected not in providers:
            providers.append(selected)
    return providers


def build_generation_prompt(*, topic: dict[str, Any], revision: dict[str, Any], difficulty: str) -> str:
    medium_rule = ""
    if difficulty == "medium":
        medium_rule = (
            "For medium difficulty, include 1-2 multiple_choice questions before the sandbox. "
            "These questions are implementation hints for the final sandbox problem: they may ask the "
            "learner to identify the right implementation approach or choose between complete code options. "
            "The MCQ is not the final answer; after answering, the learner must still write the fix in the sandbox."
        )
    if difficulty == "easy":
        medium_rule = (
            "For easy difficulty, include only multiple_choice steps. At least one question may ask "
            "the learner to choose between code-like options, but every choice must be self-contained."
        )
    return "\n".join(
        [
            "Generate a Ledger ownership exercise plan as strict JSON only.",
            "Schema:",
            '{"template_id": string, "difficulty": "easy|medium|hard", "steps": [{"type": "multiple_choice", "question_id": string} | {"type": "sandbox"}], "questions": [{"id": string, "kind": "concept|debugging", "prompt": string, "choices": [string, string, string], "correct_index": 0-2, "rationale": string}]}',
            "Rules:",
            "- Return only valid JSON, no markdown.",
            "- Every multiple_choice step must reference a question id.",
            "- Every question must have exactly 3 choices.",
            "- Do not include correct_index or rationale in anything user-facing except the JSON fields.",
            medium_rule,
            f"Difficulty: {difficulty}",
            f"Topic title: {topic.get('title', '')}",
            f"Topic summary: {topic.get('summary', '')}",
            f"Invariant: {revision.get('invariant', '')}",
            f"Code path: {revision.get('code_path', '')}",
        ]
    )


def run_generator_cli(provider: str, prompt: str, timeout_seconds: int) -> str:
    selected = (provider or os.environ.get("LEDGER_EXERCISE_PROVIDER") or "claude").lower()
    if selected in {"claude", "claude-code"}:
        command = ["claude", "-p", "--output-format", "json"]
    else:
        raise ValueError(f"unsupported exercise provider: {selected}")
    try:
        proc = subprocess.run(
            command,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    try:
        payload = json.loads(proc.stdout)
        return payload.get("result") or proc.stdout
    except json.JSONDecodeError:
        return proc.stdout


def parse_plan_json(response: str) -> dict[str, Any]:
    if not response.strip():
        raise ValueError("exercise generator returned no plan")
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", response, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def normalize_generated_plan(plan: dict[str, Any], *, difficulty: str) -> dict[str, Any]:
    if plan.get("difficulty") != difficulty:
        plan["difficulty"] = difficulty
    plan.setdefault("template_id", f"generated-{difficulty}")
    questions = plan.get("questions")
    steps = plan.get("steps")
    if not isinstance(questions, list) or not isinstance(steps, list):
        raise ValueError("generated exercise plan missing steps or questions")
    question_ids = {question.get("id") for question in questions}
    for question in questions:
        if question.get("kind") not in {"concept", "debugging"}:
            raise ValueError("generated question kind is invalid")
        choices = question.get("choices")
        if not isinstance(choices, list) or len(choices) != 3:
            raise ValueError("generated question must have exactly three choices")
        correct_index = question.get("correct_index")
        if correct_index not in {0, 1, 2}:
            raise ValueError("generated question correct_index is invalid")
        if not question.get("prompt") or not question.get("rationale"):
            raise ValueError("generated question missing prompt or rationale")
    for step in steps:
        if step.get("type") == "multiple_choice" and step.get("question_id") not in question_ids:
            raise ValueError("generated multiple_choice step references unknown question")
        if step.get("type") not in {"multiple_choice", "sandbox"}:
            raise ValueError("generated step type is invalid")
    if difficulty == "easy" and any(step.get("type") == "sandbox" for step in steps):
        raise ValueError("easy generated plan must not include sandbox")
    if difficulty == "medium" and not any(step.get("type") == "sandbox" for step in steps):
        raise ValueError("medium generated plan must include sandbox")
    return plan
