from __future__ import annotations

from copy import deepcopy
from typing import Any


VALID_DIFFICULTIES = {"easy", "medium", "hard"}

DEFAULT_PLAN = {
    "template_id": "tenant-cache-hard",
    "difficulty": "hard",
    "steps": [{"type": "sandbox"}],
    "questions": [],
}

HERO_TEMPLATES: dict[str, dict[str, Any]] = {
    "easy": {
        "template_id": "tenant-cache-easy",
        "difficulty": "easy",
        "steps": [
            {"type": "multiple_choice", "question_id": "tenant-filter-purpose"},
            {"type": "multiple_choice", "question_id": "tenant-filter-debug"},
        ],
        "questions": [
            {
                "id": "tenant-filter-purpose",
                "kind": "concept",
                "prompt": "What should this function guarantee before ranking or returning documents?",
                "choices": [
                    "Only documents for the requested tenant are returned.",
                    "All documents are returned so the caller has more context.",
                    "Documents are grouped by score before tenant filtering.",
                ],
                "correct_index": 0,
                "rationale": "The invariant is tenant isolation: documents from other tenants must not be visible.",
            },
            {
                "id": "tenant-filter-debug",
                "kind": "debugging",
                "prompt": "Which solution best fixes the failing behavior?",
                "choices": [
                    "Return only documents whose tenant_id matches the requested tenant_id.",
                    "Return all documents and rely on a later caller to filter.",
                    "Sort documents by score and return the highest scoring documents.",
                ],
                "correct_index": 0,
                "rationale": "The failing test proves the function must filter by tenant before returning results.",
            },
        ],
    },
    "medium": {
        "template_id": "tenant-cache-medium",
        "difficulty": "medium",
        "steps": [
            {"type": "multiple_choice", "question_id": "tenant-filter-purpose"},
            {"type": "sandbox"},
        ],
        "questions": [
            {
                "id": "tenant-filter-purpose",
                "kind": "concept",
                "prompt": "What property should you preserve while fixing the failing test?",
                "choices": [
                    "Tenant isolation: only the requested tenant's documents should be returned.",
                    "Score ordering: every document should be returned in descending score order.",
                    "Object identity: the returned list should contain the original input list object.",
                ],
                "correct_index": 0,
                "rationale": "The check is about tenant isolation, not ranking or object identity.",
            }
        ],
    },
    "hard": DEFAULT_PLAN,
}


def template_for(topic_id: str, difficulty: str | None) -> dict[str, Any]:
    selected = (difficulty or "hard").lower()
    if selected not in VALID_DIFFICULTIES:
        raise ValueError(f"unsupported difficulty: {selected}")
    if topic_id != "tenant-cache-isolation":
        selected = "hard"
    return deepcopy(HERO_TEMPLATES[selected])


def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    safe = deepcopy(plan)
    for question in safe.get("questions", []):
        question.pop("correct_index", None)
        question.pop("rationale", None)
    return safe


def validate_answers(plan: dict[str, Any], answers: dict[str, int]) -> dict[str, Any]:
    results = []
    questions = {question["id"]: question for question in plan.get("questions", [])}
    for question_id, selected_index in answers.items():
        question = questions.get(question_id)
        if question is None:
            results.append(
                {
                    "question_id": question_id,
                    "selected_index": selected_index,
                    "correct": False,
                    "rationale": "This question is not part of the current check.",
                }
            )
            continue
        correct = selected_index == question["correct_index"]
        results.append(
            {
                "question_id": question_id,
                "selected_index": selected_index,
                "correct": correct,
                "rationale": question["rationale"],
            }
        )

    expected_ids = {question["id"] for question in plan.get("questions", [])}
    for question_id in sorted(expected_ids - set(answers)):
        question = questions[question_id]
        results.append(
            {
                "question_id": question_id,
                "selected_index": None,
                "correct": False,
                "rationale": question["rationale"],
            }
        )
    return {"passed": bool(results) and all(item["correct"] for item in results), "results": results}
