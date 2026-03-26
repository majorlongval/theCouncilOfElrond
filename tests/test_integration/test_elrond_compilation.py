"""End-to-end: Elrond TOML → compiled n8n workflow with all extensions."""
import json
from pathlib import Path

from council.domain.loader import load_agent
from council.wiring.tools import resolve_tools
from council.wiring.resolver import resolve_tool_urls
from council.config import load_project_config
from council.adapters.n8n.compiler import compile_workflow


def test_elrond_workflow_compiles():
    agent = load_agent(Path("agents/elrond.toml"))
    config = load_project_config(Path("council.toml"))
    tools = resolve_tools(agent.tools)
    tools = resolve_tool_urls(tools, config)

    registry = {"Gimli": "mock-gimli-wf-id"}
    workflow = compile_workflow(agent, tools, workflow_registry=registry)

    assert workflow["name"] == "Elrond — Head of the Council"
    assert "nodes" in workflow
    assert "connections" in workflow

    node_types = [n["type"] for n in workflow["nodes"]]
    assert "n8n-nodes-base.telegramTrigger" in node_types
    assert "n8n-nodes-base.if" in node_types  # negative /run filter
    assert "@n8n/n8n-nodes-langchain.agent" in node_types
    assert "@n8n/n8n-nodes-langchain.lmChatOpenAi" in node_types
    assert "n8n-nodes-base.telegram" in node_types  # Reply
    assert "@n8n/n8n-nodes-langchain.memoryBufferWindow" in node_types
    assert "@n8n/n8n-nodes-langchain.toolWorkflow" in node_types

    json_str = json.dumps(workflow)
    assert json.loads(json_str) == workflow


def test_gimli_callable_workflow_compiles():
    agent = load_agent(Path("agents/gimli.toml"))
    config = load_project_config(Path("council.toml"))
    tools = resolve_tools(agent.tools)
    tools = resolve_tool_urls(tools, config)

    workflow = compile_workflow(agent, tools)

    node_types = [n["type"] for n in workflow["nodes"]]
    # Workflow-only trigger — no Telegram Trigger
    assert "n8n-nodes-base.telegramTrigger" not in node_types
    assert "n8n-nodes-base.executeWorkflowTrigger" in node_types
    set_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.set"]
    assert len(set_nodes) == 1  # Only Normalize Workflow Input
