import pytest
from council.domain.agent import AgentDefinition, Trigger, Reply


def test_valid_agent_definition():
    agent = AgentDefinition(
        name="Gimli",
        role="Builder",
        brain="gemini/gemini-flash-latest",
        prompt="You are Gimli.",
        tools=["github.list_issues", "github.read_file"],
        artifacts=["github.pull_request"],
        trigger=Trigger(type="telegram", command="/run gimli"),
        reply=Reply(type="telegram"),
    )
    assert agent.name == "Gimli"
    assert agent.brain == "gemini/gemini-flash-latest"
    assert len(agent.tools) == 2


def test_trigger_type_must_be_valid():
    with pytest.raises(ValueError):
        Trigger(type="invalid")


def test_reply_type_must_be_valid():
    with pytest.raises(ValueError):
        Reply(type="invalid")


def test_trigger_telegram_allows_command():
    trigger = Trigger(type="telegram", command="/run gimli")
    assert trigger.command == "/run gimli"


def test_trigger_webhook_allows_path():
    trigger = Trigger(type="webhook", path="my-webhook")
    assert trigger.path == "my-webhook"


def test_trigger_cron_allows_schedule():
    trigger = Trigger(type="cron", schedule="0 * * * *")
    assert trigger.schedule == "0 * * * *"


def test_agent_requires_all_fields():
    with pytest.raises(ValueError):
        AgentDefinition(
            name="Gimli",
            role="Builder",
            # missing brain, prompt, tools, artifacts, trigger, reply
        )
