from ledger_backend.coach import ClaudeCoach, CodexCoach, create_coach


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


def test_codex_coach_uses_noninteractive_exec_with_read_only_sandbox():
    coach = CodexCoach(binary="codex")
    command = coach.build_command()

    assert command[:2] == ["codex", "exec"]
    assert command[-1] == "-"
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--ask-for-approval" in command
    assert command[command.index("--ask-for-approval") + 1] == "never"
    assert "--ephemeral" in command


def test_create_coach_accepts_codex_provider():
    assert isinstance(create_coach("codex"), CodexCoach)


def test_create_coach_accepts_explicit_cli_provider_aliases():
    assert isinstance(create_coach("claude-code"), ClaudeCoach)
    assert isinstance(create_coach("claude-print"), ClaudeCoach)
    assert isinstance(create_coach("codex-exec"), CodexCoach)


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
