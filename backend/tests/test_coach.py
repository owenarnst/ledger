import pytest

from backend.coach import COACH_MODELS, DEFAULT_COACH_MODEL, ClaudeCoach, create_coach


def test_claude_coach_uses_claude_code_with_tools_denied():
    coach = ClaudeCoach(binary="claude")
    command = coach.build_command()

    assert command[:2] == ["claude", "-p"]
    assert "--output-format" in command
    assert "json" in command
    assert "--append-system-prompt" in command
    assert "--disallowedTools" in command
    disallowed = command[command.index("--disallowedTools") + 1]
    assert "Read" in disallowed
    assert "Bash" in disallowed
    assert "Edit" in disallowed


def test_claude_coach_passes_the_selected_model():
    command = ClaudeCoach(binary="claude", model_id="haiku").build_command()
    assert command[command.index("--model") + 1] == "haiku"


def test_claude_prompt_excludes_code_and_diff():
    coach = ClaudeCoach(binary="claude")
    prompt = coach.build_prompt(
        topic_title="Tenant isolation in retrieval cache",
        task="One tenant sees another tenant's result.",
        test_output="FAILED tests/test_rerank.py::test_filters_documents_by_tenant",
        question="What is this code supposed to do?",
    )

    assert "original implementation" not in prompt.lower()
    assert "mutation diff" not in prompt.lower()
    assert "Tenant isolation" in prompt
    assert "FAILED tests/test_rerank.py" in prompt


def test_create_coach_defaults_to_sonnet():
    coach = create_coach()
    assert isinstance(coach, ClaudeCoach)
    assert coach.model_id == DEFAULT_COACH_MODEL == "sonnet"


def test_create_coach_accepts_each_supported_model():
    for model in COACH_MODELS:
        coach = create_coach(model)
        assert isinstance(coach, ClaudeCoach)
        assert coach.model_id == model


def test_create_coach_rejects_an_unknown_model():
    with pytest.raises(ValueError):
        create_coach("gpt-4")


def test_missing_cli_binary_returns_unavailable_message():
    coach = ClaudeCoach(binary="definitely-missing-ledger-coach-cli")

    response = coach.ask(
        topic_title="Tenant isolation in retrieval cache",
        task="Restore tenant isolation.",
        test_output="FAILED tests/test_rerank.py",
        question="Where should I start?",
    )

    assert "Coach unavailable" in response
    assert "definitely-missing-ledger-coach-cli" in response
