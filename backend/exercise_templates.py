from __future__ import annotations

from typing import Any


VALID_DIFFICULTIES = {"easy", "medium", "hard"}

DEFAULT_PLAN = {
    "template_id": "tenant-cache-hard",
    "difficulty": "hard",
    "steps": [{"type": "sandbox"}],
    "questions": [],
}

def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    safe = json_deepcopy(plan)
    for question in safe.get("questions", []):
        question.pop("correct_index", None)
        question.pop("rationale", None)
    return safe


def json_deepcopy(payload: dict[str, Any]) -> dict[str, Any]:
    import json

    return json.loads(json.dumps(payload))


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
