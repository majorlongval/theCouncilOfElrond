import pytest

from council.domain.agent import AgentDefinition, MemoryConfig, Reply, Trigger
from council.wiring.tools.models import HttpTool, BearerToken
from council.adapters.n8n.compiler import compile_workflow


def _agent_with_memory(**overrides) -> AgentDefinition:
    defaults = {
        "name": "Elrond",
        "role": "Director",
        "brain": "gemini/gemini-pro",
        "prompt": "You are Elrond.",
        "tools": [],
        "trigger": Trigger(type="telegram"),
        "reply": Reply(type="telegram"),
        "memory": MemoryConfig(type="window_buffer", window_size=10),
    }
    defaults.update(overrides)
    return AgentDefinition(**defaults)


def _simple_tool() -> HttpTool:
    return HttpTool(
        name="List Issues",
        description="List issues.",
        url="https://api.github.com/repos/owner/repo/issues",
        auth=BearerToken(env="GITHUB_TOKEN"),
    )


def test_memory_node_present_when_memory_configured():
    agent = _agent_with_memory()
    workflow = compile_workflow(agent, [])
    memory_nodes = [n for n in workflow["nodes"] if "memoryBufferWindow" in n["type"]]
    assert len(memory_nodes) == 1


def test_memory_node_has_correct_window_size():
    agent = _agent_with_memory(memory=MemoryConfig(type="window_buffer", window_size=20))
    workflow = compile_workflow(agent, [])
    memory_node = next(n for n in workflow["nodes"] if "memoryBufferWindow" in n["type"])
    assert memory_node["parameters"]["contextWindowLength"] == 20


def test_memory_node_wired_to_agent():
    agent = _agent_with_memory()
    workflow = compile_workflow(agent, [])
    conns = workflow["connections"]
    assert "Chat Memory" in conns
    assert "ai_memory" in conns["Chat Memory"]
    assert conns["Chat Memory"]["ai_memory"][0][0]["node"] == "Elrond agent"


def test_no_memory_node_when_memory_not_configured():
    agent = _agent_with_memory(memory=None)
    workflow = compile_workflow(agent, [])
    memory_nodes = [n for n in workflow["nodes"] if "memoryBufferWindow" in n["type"]]
    assert len(memory_nodes) == 0
