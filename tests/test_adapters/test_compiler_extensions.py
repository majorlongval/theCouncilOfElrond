import pytest

from council.domain.agent import AgentDefinition, MemoryConfig, Reply, Trigger
from council.wiring.tools.models import HttpTool, BearerToken, WorkflowTool
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


def test_no_command_agent_gets_negative_filter():
    agent = _agent_with_memory(memory=None)
    workflow = compile_workflow(agent, [])
    if_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.if"]
    assert len(if_nodes) == 1
    assert if_nodes[0]["name"] == "Not a /run command?"
    conditions = if_nodes[0]["parameters"]["conditions"]["conditions"]
    assert conditions[0]["rightValue"] == "/run "
    assert conditions[0]["operator"]["operation"] == "notStartsWith"


def test_no_command_agent_trigger_routes_through_negative_filter():
    agent = _agent_with_memory(memory=None)
    workflow = compile_workflow(agent, [])
    conns = workflow["connections"]
    assert conns["Telegram Trigger"]["main"][0][0]["node"] == "Not a /run command?"
    assert conns["Not a /run command?"]["main"][0][0]["node"] == "Elrond agent"


def test_command_agent_does_not_get_negative_filter():
    agent = _agent_with_memory(
        name="Gimli",
        trigger=Trigger(type="telegram", command="/run gimli"),
        memory=None,
    )
    workflow = compile_workflow(agent, [])
    if_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.if"]
    assert len(if_nodes) == 1
    assert if_nodes[0]["name"] == "Is /run gimli?"


def test_execute_workflow_tool_node_generated():
    agent = _agent_with_memory(memory=None)
    wf_tool = WorkflowTool(name="Execute Gimli", description="Trigger Gimli.", target_agent="Gimli")
    registry = {"Gimli": "wf-123"}
    workflow = compile_workflow(agent, [wf_tool], workflow_registry=registry)
    exec_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.executeWorkflow"]
    assert len(exec_nodes) == 1
    assert exec_nodes[0]["parameters"]["workflowId"] == "wf-123"


def test_execute_workflow_tool_wired_to_agent():
    agent = _agent_with_memory(memory=None)
    wf_tool = WorkflowTool(name="Execute Gimli", description="Trigger Gimli.", target_agent="Gimli")
    registry = {"Gimli": "wf-123"}
    workflow = compile_workflow(agent, [wf_tool], workflow_registry=registry)
    conns = workflow["connections"]
    assert "Execute Gimli" in conns
    assert conns["Execute Gimli"]["ai_tool"][0][0]["node"] == "Elrond agent"


def test_execute_workflow_missing_registry_raises():
    agent = _agent_with_memory(memory=None)
    wf_tool = WorkflowTool(name="Execute Gimli", description="Trigger Gimli.", target_agent="Gimli")
    with pytest.raises(ValueError, match="not found in workflow registry"):
        compile_workflow(agent, [wf_tool], workflow_registry={})


def test_execute_workflow_no_registry_raises():
    agent = _agent_with_memory(memory=None)
    wf_tool = WorkflowTool(name="Execute Gimli", description="Trigger Gimli.", target_agent="Gimli")
    with pytest.raises(ValueError, match="not found in workflow registry"):
        compile_workflow(agent, [wf_tool])


def test_mixed_tools_compile():
    agent = _agent_with_memory(memory=None)
    http_tool = _simple_tool()
    wf_tool = WorkflowTool(name="Execute Gimli", description="Trigger Gimli.", target_agent="Gimli")
    registry = {"Gimli": "wf-456"}
    workflow = compile_workflow(agent, [http_tool, wf_tool], workflow_registry=registry)
    http_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.httpRequestTool"]
    exec_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.executeWorkflow"]
    assert len(http_nodes) == 1
    assert len(exec_nodes) == 1
