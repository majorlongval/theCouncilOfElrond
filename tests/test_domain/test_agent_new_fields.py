import pytest
from council.domain.agent import AgentDefinition, MemoryConfig, Trigger, Reply


def _base_agent(**overrides) -> AgentDefinition:
    defaults = {
        "name": "TestAgent",
        "role": "Tester",
        "brain": "gemini/gemini-flash-latest",
        "prompt": "You are a test agent.",
        "trigger": Trigger(type="telegram"),
        "reply": Reply(type="telegram"),
    }
    defaults.update(overrides)
    return AgentDefinition(**defaults)


def test_callable_defaults_to_false():
    agent = _base_agent()
    assert agent.callable is False


def test_callable_can_be_set_true():
    agent = _base_agent(callable=True)
    assert agent.callable is True


def test_orchestrator_defaults_to_false():
    agent = _base_agent()
    assert agent.orchestrator is False


def test_orchestrator_can_be_set_true():
    agent = _base_agent(orchestrator=True)
    assert agent.orchestrator is True


def test_memory_defaults_to_none():
    agent = _base_agent()
    assert agent.memory is None


def test_memory_config_parses():
    config = MemoryConfig(type="window_buffer", window_size=15)
    agent = _base_agent(memory=config)
    assert agent.memory is not None
    assert agent.memory.type == "window_buffer"
    assert agent.memory.window_size == 15


def test_memory_config_default_window_size():
    config = MemoryConfig(type="window_buffer")
    assert config.window_size == 10


def test_tools_defaults_to_empty_list():
    agent = _base_agent()
    assert agent.tools == []


def test_artifacts_defaults_to_empty_list():
    agent = _base_agent()
    assert agent.artifacts == []
