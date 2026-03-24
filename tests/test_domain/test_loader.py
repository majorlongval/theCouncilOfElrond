from pathlib import Path

import pytest

from council.domain.agent import AgentDefinition
from council.domain.loader import load_agent, load_all_agents


FIXTURES = Path(__file__).parent.parent / "fixtures" / "agents"


def test_load_agent_from_toml():
    agent = load_agent(FIXTURES / "valid_agent.toml")
    assert isinstance(agent, AgentDefinition)
    assert agent.name == "Gimli"
    assert agent.role == "Builder"
    assert agent.brain == "gemini/gemini-flash-latest"
    assert agent.trigger.type == "telegram"
    assert agent.trigger.command == "/run gimli"
    assert agent.reply.type == "telegram"
    assert "github.list_issues" in agent.tools


def test_load_agent_invalid_toml_raises():
    with pytest.raises(ValueError):
        load_agent(FIXTURES / "invalid_agent.toml")


def test_load_all_agents_from_directory():
    agents = load_all_agents(FIXTURES)
    assert len(agents) == 1  # only valid_agent.toml is valid
    assert agents[0].name == "Gimli"


def test_load_agent_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_agent(Path("/nonexistent/agent.toml"))
