from pathlib import Path

from council.domain.loader import load_agent


def test_load_elrond_toml():
    agent = load_agent(Path("agents/elrond.toml"))
    assert agent.name == "Elrond"
    assert agent.orchestrator is True
    assert agent.memory is not None
    assert agent.memory.type == "window_buffer"
    assert agent.trigger.command is None


def test_load_gimli_callable():
    agent = load_agent(Path("agents/gimli.toml"))
    assert agent.callable is True
