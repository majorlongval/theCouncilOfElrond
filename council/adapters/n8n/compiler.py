"""Compiler: AgentDefinition + resolved HttpTools → n8n workflow JSON.

The produced dict matches n8n's workflow import format and can be POSTed
to the n8n REST API or imported via the UI.

Workflow shape:
  Telegram Trigger → [If (optional)] → AI Agent → Reply
                                           |
                                           ├── OpenAI Chat Model (→ LiteLLM)
                                           └── HTTP Request Tool × N
"""

from __future__ import annotations

import re
from typing import Any

from council.domain.agent import AgentDefinition
from council.wiring.tools.models import HttpTool


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_workflow(
    agent: AgentDefinition,
    tools: list[HttpTool],
    litellm_base_url: str = "http://litellm:4000/v1",
) -> dict[str, Any]:
    """Turn an agent definition and its resolved tools into n8n workflow JSON."""
    has_command = agent.trigger.command is not None

    nodes = _build_nodes(agent, tools, litellm_base_url, has_command)
    connections = _build_connections(agent, tools, has_command)

    return {
        "name": f"{agent.name} — {agent.role}",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


# ---------------------------------------------------------------------------
# Node builders — each returns one node dict
# ---------------------------------------------------------------------------

def _build_nodes(
    agent: AgentDefinition,
    tools: list[HttpTool],
    litellm_base_url: str,
    has_command: bool,
) -> list[dict[str, Any]]:
    """Assemble the full node list for this workflow."""
    nodes: list[dict[str, Any]] = [
        _telegram_trigger_node(),
        _ai_agent_node(agent),
        _chat_model_node(agent.brain, litellm_base_url),
        _reply_node(),
    ]

    if has_command:
        nodes.append(_if_node(agent.trigger.command))  # type: ignore[arg-type]

    for tool in tools:
        nodes.append(_tool_node(tool))

    return nodes


def _telegram_trigger_node() -> dict[str, Any]:
    return {
        "name": "Telegram Trigger",
        "type": "n8n-nodes-base.telegramTrigger",
        "typeVersion": 1.2,
        "position": [0, 0],
        "parameters": {
            "updates": ["message"],
        },
    }


def _if_node(command: str) -> dict[str, Any]:
    """Conditional gate — only passes messages that match the slash command."""
    return {
        "name": f"Is {command}?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.3,
        "position": [200, 0],
        "parameters": {
            "conditions": {
                "conditions": [
                    {
                        "leftValue": "={{ $json.message.text }}",
                        "rightValue": command,
                        "operator": {
                            "type": "string",
                            "operation": "startsWith",
                        },
                    }
                ],
            },
        },
    }


def _ai_agent_node(agent: AgentDefinition) -> dict[str, Any]:
    return {
        "name": f"{agent.name} agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 3.1,
        "position": [400, 0],
        "parameters": {
            "options": {
                "systemMessage": agent.prompt,
            },
        },
    }


def _chat_model_node(brain: str, litellm_base_url: str) -> dict[str, Any]:
    """OpenAI-compatible chat model node that routes through LiteLLM."""
    return {
        "name": "Chat Model",
        "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
        "typeVersion": 1.3,
        "position": [400, 200],
        "parameters": {
            "model": {
                "__rl": True,
                "value": brain,
                "mode": "id",
            },
            "options": {
                "baseURL": litellm_base_url,
            },
        },
    }


def _reply_node() -> dict[str, Any]:
    return {
        "name": "Reply",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [600, 0],
        "parameters": {
            "chatId": "={{ $('Telegram Trigger').item.json.message.chat.id }}",
            "text": "={{ $json.output }}",
        },
    }


def _tool_node(tool: HttpTool) -> dict[str, Any]:
    """Build an httpRequestTool node from a resolved HttpTool model."""
    url = _resolve_tool_url(tool)
    params: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
        "url": url,
        "method": tool.method,
        "sendHeaders": False,
        "sendBody": False,
    }

    # -- Headers: auth + any custom headers
    header_list = _build_header_list(tool)
    if header_list:
        params["sendHeaders"] = True
        params["headerParameters"] = {"parameters": header_list}

    # -- Body (POST/PUT/PATCH with a JSON schema)
    if tool.body is not None:
        params["sendBody"] = True
        params["jsonBody"] = (
            "={{ /*n8n-auto-generated-fromAI-override*/ "
            "$fromAI('JSON', ``, 'json') }}"
        )

    return {
        "name": tool.name,
        "type": "n8n-nodes-base.httpRequestTool",
        "typeVersion": 4.4,
        "position": [400, 400],
        "parameters": params,
    }


# ---------------------------------------------------------------------------
# Connection builder
# ---------------------------------------------------------------------------

def _build_connections(
    agent: AgentDefinition,
    tools: list[HttpTool],
    has_command: bool,
) -> dict[str, Any]:
    """Wire every node together.

    Main flow: Trigger → [If] → Agent → Reply
    Sub-connections: ChatModel →(ai_languageModel)→ Agent
                     Tools     →(ai_tool)→ Agent
    """
    agent_name = f"{agent.name} agent"
    conns: dict[str, Any] = {}

    # -- Main flow
    if has_command:
        if_name = f"Is {agent.trigger.command}?"
        conns["Telegram Trigger"] = _main_out(if_name)
        # If node true branch (index 0) → Agent
        conns[if_name] = _main_out(agent_name)
    else:
        conns["Telegram Trigger"] = _main_out(agent_name)

    # Agent → Reply (always present)
    conns[agent_name] = _main_out("Reply")

    # -- Chat Model → Agent (always present)
    conns["Chat Model"] = {
        "ai_languageModel": [[{"node": agent_name, "type": "ai_languageModel", "index": 0}]],
    }

    # -- Tools → Agent
    for tool in tools:
        conns[tool.name] = {
            "ai_tool": [[{"node": agent_name, "type": "ai_tool", "index": 0}]],
        }

    return conns


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _main_out(target_node: str) -> dict[str, Any]:
    """Shorthand for a single main-output connection to the given node."""
    return {
        "main": [[{"node": target_node, "type": "main", "index": 0}]],
    }


def _resolve_tool_url(tool: HttpTool) -> str:
    """Replace {param} placeholders with n8n $fromAI expressions.

    If any replacements happen the URL is prefixed with '=' so n8n evaluates
    it as an expression.
    """
    url = tool.url
    for param_name, param in tool.params.items():
        placeholder = f"{{{param_name}}}"
        from_ai = f"{{{{ $fromAI('{param_name}', '{param.description}', '{param.type}') }}}}"
        url = url.replace(placeholder, from_ai)

    # Prefix with '=' when the URL contains expressions
    if tool.params:
        url = f"={url}"

    return url


def _build_header_list(tool: HttpTool) -> list[dict[str, str]]:
    """Merge auth header and any custom headers into a flat list."""
    headers: list[dict[str, str]] = []

    if tool.auth is not None:
        headers.append({
            "name": "Authorization",
            "value": f"=token {{{{ $env.{tool.auth.env} }}}}",
        })

    for name, value in tool.headers.items():
        headers.append({"name": name, "value": value})

    return headers
