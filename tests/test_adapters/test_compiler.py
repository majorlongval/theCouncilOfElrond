import json

import pytest

from council.domain.agent import AgentDefinition, Reply, Trigger
from council.wiring.tools.models import BearerToken, HttpTool, JsonBody, Param
from council.adapters.n8n.compiler import compile_workflow


@pytest.fixture
def gimli_agent() -> AgentDefinition:
    return AgentDefinition(
        name="Gimli",
        role="Builder",
        brain="gemini/gemini-flash-latest",
        prompt="You are Gimli, a builder agent.",
        tools=["github.list_issues", "github.read_file", "github.create_issue"],
        artifacts=["github.pull_request"],
        trigger=Trigger(type="telegram", command="/run gimli"),
        reply=Reply(type="telegram"),
    )


@pytest.fixture
def resolved_tools() -> list[HttpTool]:
    return [
        HttpTool(
            name="List Issues",
            description="List open issues.",
            url="https://api.github.com/repos/majorlongval/theCouncilOfElrond/issues?state=open",
            auth=BearerToken(env="GITHUB_TOKEN"),
        ),
        HttpTool(
            name="Read File",
            description="Read a file.",
            url="https://api.github.com/repos/majorlongval/theCouncilOfElrond/contents/{filepath}",
            params={"filepath": Param(description="Path to file")},
            auth=BearerToken(env="GITHUB_TOKEN"),
            headers={"Accept": "application/vnd.github.raw+json"},
        ),
        HttpTool(
            name="Create Issue",
            description="Create an issue.",
            url="https://api.github.com/repos/majorlongval/theCouncilOfElrond/issues",
            method="POST",
            body=JsonBody(schema={"title": "string", "body": "string"}),
            auth=BearerToken(env="GITHUB_TOKEN"),
        ),
    ]


def test_workflow_has_correct_name(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    assert workflow["name"] == "Gimli — Builder"


def test_workflow_has_required_keys(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    assert "name" in workflow
    assert "nodes" in workflow
    assert "connections" in workflow
    assert "settings" in workflow


def test_workflow_has_correct_node_count(gimli_agent, resolved_tools):
    """Trigger + If (command present) + Agent + ChatModel + Reply + 3 tools = 8 nodes."""
    workflow = compile_workflow(gimli_agent, resolved_tools)
    assert len(workflow["nodes"]) == 8


def test_workflow_without_command_has_negative_filter(resolved_tools):
    """When trigger has no command, negative /run filter is added."""
    agent = AgentDefinition(
        name="Elrond",
        role="Director",
        brain="anthropic/claude-sonnet",
        prompt="You are Elrond.",
        tools=["github.list_issues"],
        artifacts=[],
        trigger=Trigger(type="telegram"),
        reply=Reply(type="telegram"),
    )
    workflow = compile_workflow(agent, resolved_tools)
    if_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.if"]
    assert len(if_nodes) == 1
    assert if_nodes[0]["name"] == "Not a /run command?"
    conns = workflow["connections"]
    assert conns["Telegram Trigger"]["main"][0][0]["node"] == "Not a /run command?"
    assert conns["Not a /run command?"]["main"][0][0]["node"] == "Elrond agent"


def test_workflow_has_telegram_trigger(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    trigger_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.telegramTrigger"]
    assert len(trigger_nodes) == 1


def test_workflow_has_if_node_with_command(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    if_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.if"]
    assert len(if_nodes) == 1
    conditions = if_nodes[0]["parameters"]["conditions"]["conditions"]
    assert conditions[0]["rightValue"] == "/run gimli"


def test_workflow_has_ai_agent_node(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    agent_nodes = [n for n in workflow["nodes"] if n["type"] == "@n8n/n8n-nodes-langchain.agent"]
    assert len(agent_nodes) == 1
    agent = agent_nodes[0]
    assert agent["parameters"]["options"]["systemMessage"] == gimli_agent.prompt


def test_workflow_has_openai_chat_model(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    model_nodes = [n for n in workflow["nodes"] if n["type"] == "@n8n/n8n-nodes-langchain.lmChatOpenAi"]
    assert len(model_nodes) == 1
    model = model_nodes[0]
    assert model["parameters"]["model"]["value"] == "gemini/gemini-flash-latest"
    assert model["parameters"]["options"]["baseURL"] == "http://litellm:4000/v1"


def test_workflow_has_tool_nodes(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    tool_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.httpRequestTool"]
    assert len(tool_nodes) == 3
    tool_names = {n["name"] for n in tool_nodes}
    assert tool_names == {"List Issues", "Read File", "Create Issue"}


def test_workflow_has_telegram_reply(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    reply_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.telegram"]
    assert len(reply_nodes) == 1
    reply = reply_nodes[0]
    assert "Telegram Trigger" in reply["parameters"]["chatId"]


def test_workflow_connections_main_flow(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    conns = workflow["connections"]
    # Trigger -> If
    assert conns["Telegram Trigger"]["main"][0][0]["node"] == "Is /run gimli?"
    # If -> Agent
    assert conns["Is /run gimli?"]["main"][0][0]["node"] == "Gimli agent"
    # Agent -> Reply
    assert conns["Gimli agent"]["main"][0][0]["node"] == "Reply"


def test_workflow_connections_tools_to_agent(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    conns = workflow["connections"]
    for tool_name in ["List Issues", "Read File", "Create Issue"]:
        assert conns[tool_name]["ai_tool"][0][0]["node"] == "Gimli agent"
        assert conns[tool_name]["ai_tool"][0][0]["type"] == "ai_tool"


def test_workflow_connections_model_to_agent(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    conns = workflow["connections"]
    assert conns["Chat Model"]["ai_languageModel"][0][0]["node"] == "Gimli agent"
    assert conns["Chat Model"]["ai_languageModel"][0][0]["type"] == "ai_languageModel"


def test_tool_with_params_uses_from_ai(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    read_file_node = next(n for n in workflow["nodes"] if n["name"] == "Read File")
    assert "$fromAI" in read_file_node["parameters"]["url"]
    assert read_file_node["parameters"]["url"].startswith("=")


def test_tool_with_body_uses_from_ai(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    create_node = next(n for n in workflow["nodes"] if n["name"] == "Create Issue")
    assert create_node["parameters"]["sendBody"] is True
    assert "$fromAI" in create_node["parameters"]["jsonBody"]


def test_tool_auth_header(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    list_node = next(n for n in workflow["nodes"] if n["name"] == "List Issues")
    assert list_node["parameters"]["sendHeaders"] is True
    headers = list_node["parameters"]["headerParameters"]["parameters"]
    auth_header = next(h for h in headers if h["name"] == "Authorization")
    assert "GITHUB_TOKEN" in auth_header["value"]
    assert auth_header["value"].startswith("=")


def test_workflow_is_valid_json(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    json_str = json.dumps(workflow)
    reparsed = json.loads(json_str)
    assert reparsed["name"] == workflow["name"]
