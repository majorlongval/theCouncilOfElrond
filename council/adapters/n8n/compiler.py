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

import uuid
from typing import Any

from council.domain.agent import AgentDefinition, MemoryConfig
from council.wiring.tools.models import HttpTool, Tool, WorkflowTool


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_workflow(
    agent: AgentDefinition,
    tools: list[Tool],
    litellm_base_url: str = "http://litellm:4000/v1",
    workflow_registry: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Turn an agent definition and its resolved tools into n8n workflow JSON."""
    has_command = agent.trigger.command is not None

    nodes = _build_nodes(agent, tools, litellm_base_url, has_command, workflow_registry)
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
    tools: list[Tool],
    litellm_base_url: str,
    has_command: bool,
    workflow_registry: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Assemble the full node list for this workflow."""
    is_callable = agent.callable
    is_workflow_only = agent.trigger.type == "workflow"

    nodes: list[dict[str, Any]] = [
        _ai_agent_node(agent, callable=is_callable or is_workflow_only),
        _chat_model_node(agent.brain, litellm_base_url),
    ]

    if is_workflow_only:
        # Workflow-only agents have no Telegram Trigger — only Execute Workflow
        nodes.append(_execute_workflow_trigger_node())
        nodes.append(_normalize_workflow_set_node())
        nodes.append(_reply_if_guard_node())
        nodes.append(_reply_node(callable=True))
    elif is_callable:
        # Callable agents have both Telegram and Execute Workflow entry points
        nodes.append(_telegram_trigger_node())
        nodes.append(_reply_node(callable=True))
        nodes.append(_execute_workflow_trigger_node())
        nodes.append(_normalize_telegram_set_node(agent.trigger.command))
        nodes.append(_normalize_workflow_set_node())
        nodes.append(_reply_if_guard_node())
        if has_command:
            nodes.append(_if_node(agent.trigger.command))  # type: ignore[arg-type]
        else:
            nodes.append(_negative_command_filter_node())
    else:
        # Standard agents — Telegram only
        nodes.append(_telegram_trigger_node())
        nodes.append(_reply_node(callable=False))
        if has_command:
            nodes.append(_if_node(agent.trigger.command))  # type: ignore[arg-type]
        else:
            nodes.append(_negative_command_filter_node())

    for tool in tools:
        if isinstance(tool, WorkflowTool):
            nodes.append(_execute_workflow_tool_node(tool, workflow_registry or {}))
        else:
            nodes.append(_tool_node(tool))

    if agent.memory is not None:
        nodes.append(_memory_node(agent.memory, callable=is_callable))

    return nodes


def _telegram_trigger_node() -> dict[str, Any]:
    return {
        "name": "Telegram Trigger",
        "type": "n8n-nodes-base.telegramTrigger",
        "typeVersion": 1.2,
        "position": [0, 0],
        "webhookId": str(uuid.uuid4()),
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


def _negative_command_filter_node() -> dict[str, Any]:
    """Rejects messages starting with /run — prevents command-less agents from
    processing messages meant for specific agents like '/run gimli'."""
    return {
        "name": "Not a /run command?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.3,
        "position": [200, 0],
        "parameters": {
            "conditions": {
                "conditions": [
                    {
                        "leftValue": "={{ $json.message.text }}",
                        "rightValue": "/run ",
                        "operator": {
                            "type": "string",
                            "operation": "notStartsWith",
                        },
                    }
                ],
            },
        },
    }


def _ai_agent_node(agent: AgentDefinition, *, callable: bool = False) -> dict[str, Any]:
    """AI Agent node.

    When callable, input comes from the normalized Set nodes ($json.instructions).
    Otherwise, it reads directly from the Telegram Trigger.
    """
    if callable:
        text = "={{ $json.instructions || 'Check the open issues and decide what to work on.' }}"
    else:
        command = agent.trigger.command or ""
        text = (
            f"={{{{ $('Telegram Trigger').item.json.message.text"
            f".replace('{command}', '').trim() "
            f"|| 'Check the open issues and decide what to work on.' }}}}"
        )
    return {
        "name": f"{agent.name} agent",
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 3.1,
        "position": [400, 0],
        "parameters": {
            "promptType": "define",
            "text": text,
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


def _reply_node(*, callable: bool = False) -> dict[str, Any]:
    """Reply node sends the agent's output back via Telegram.

    When callable, the chat_id comes from the normalized Set node rather than
    directly from the Telegram Trigger — this allows headless invocations to
    skip replying when no chat_id is provided.
    """
    chat_id = (
        "={{ $json.chat_id }}"
        if callable
        else "={{ $('Telegram Trigger').item.json.message.chat.id }}"
    )
    return {
        "name": "Reply",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [600, 0],
        "parameters": {
            "chatId": chat_id,
            "text": "={{ $json.output.slice(0, 4000) }}",
        },
    }


def _execute_workflow_trigger_node() -> dict[str, Any]:
    """Second entry point — allows other n8n workflows to invoke this agent.

    Uses 'passthrough' input mode so any JSON payload is accepted without
    requiring a predefined schema. Our downstream Set nodes handle
    normalization into the expected {instructions, chat_id} shape.
    """
    return {
        "name": "Execute Workflow Trigger",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 200],
        "parameters": {
            "inputSource": "passthrough",
        },
    }


def _normalize_telegram_set_node(command: str | None) -> dict[str, Any]:
    """Extract instructions and chat_id from the Telegram message payload.

    Strips the slash command prefix (if any) so downstream nodes receive
    clean user text in a uniform shape.
    """
    strip_expr = f".replace('{command}', '').trim()" if command else ".trim()"
    return {
        "name": "Normalize Telegram Input",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [200, 0],
        "parameters": {
            "assignments": {
                "assignments": [
                    {"name": "instructions", "value": f"={{{{ $json.message.text{strip_expr} }}}}", "type": "string"},
                    {"name": "chat_id", "value": "={{ $json.message.chat.id }}", "type": "string"},
                ]
            }
        },
    }


def _normalize_workflow_set_node() -> dict[str, Any]:
    """Pass-through normalization for Execute Workflow inputs.

    The calling workflow is expected to provide `instructions` and optionally
    `chat_id`. This Set node ensures the fields exist with consistent names.
    """
    return {
        "name": "Normalize Workflow Input",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [200, 200],
        "parameters": {
            "assignments": {
                "assignments": [
                    {"name": "instructions", "value": "={{ $json.instructions }}", "type": "string"},
                    {"name": "chat_id", "value": "={{ $json.chat_id }}", "type": "string"},
                ]
            }
        },
    }


def _reply_if_guard_node() -> dict[str, Any]:
    """Gate before the Reply node — skips sending when there is no chat_id.

    Headless (workflow-triggered) executions may not have a chat_id, so
    we must not attempt to send a Telegram message in that case.
    """
    return {
        "name": "Has chat_id?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.3,
        "position": [600, 0],
        "parameters": {
            "conditions": {
                "conditions": [
                    {
                        "leftValue": "={{ $json.chat_id }}",
                        "rightValue": "",
                        "operator": {"type": "string", "operation": "exists"},
                    }
                ],
            },
        },
    }


def _memory_node(memory: MemoryConfig, callable: bool) -> dict[str, Any]:
    """Window buffer memory — gives the agent short-term conversation context.

    The session key identifies which conversation's history to load. For
    non-callable agents the chat_id comes directly from the Telegram trigger;
    callable agents receive it via a Set node (Task 9 wires that path).
    """
    session_key = (
        "={{ $json.chat_id }}"
        if callable
        else "={{ $('Telegram Trigger').item.json.message.chat.id }}"
    )
    return {
        "name": "Chat Memory",
        "type": "@n8n/n8n-nodes-langchain.memoryBufferWindow",
        "typeVersion": 1.3,
        "position": [400, 300],
        "parameters": {
            "sessionIdType": "customKey",
            "sessionKey": session_key,
            "contextWindowLength": memory.window_size,
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
        params["specifyBody"] = "json"
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


def _execute_workflow_tool_node(
    tool: WorkflowTool,
    workflow_registry: dict[str, str],
) -> dict[str, Any]:
    """Build a Sub-Workflow Tool node from a WorkflowTool model.

    Uses the langchain toolWorkflow node so it can be connected as an ai_tool
    to the AI Agent. The regular executeWorkflow node lacks the supplyData
    interface that the agent requires.
    """
    if tool.target_agent not in workflow_registry:
        raise ValueError(
            f"Agent '{tool.target_agent}' not found in workflow registry — is it deployed?"
        )
    return {
        "name": tool.name,
        "type": "@n8n/n8n-nodes-langchain.toolWorkflow",
        "typeVersion": 2.2,
        "position": [400, 400],
        "parameters": {
            "description": tool.description,
            "source": "database",
            "workflowId": {
                "__rl": True,
                "value": workflow_registry[tool.target_agent],
                "mode": "id",
            },
            "workflowInputs": {
                "mappingMode": "defineBelow",
                "value": {
                    "instructions": "={{ $fromAI('instructions', 'The task instructions to pass to the sub-workflow', 'string') }}",
                    "chat_id": "={{ $json.chat_id }}",
                },
                "schema": [
                    {
                        "id": "instructions",
                        "type": "string",
                        "display": True,
                        "required": True,
                        "displayName": "instructions",
                        "defaultMatch": False,
                        "canBeUsedToMatch": True,
                    },
                    {
                        "id": "chat_id",
                        "type": "string",
                        "display": True,
                        "required": False,
                        "displayName": "chat_id",
                        "defaultMatch": False,
                        "canBeUsedToMatch": True,
                    },
                ],
                "matchingColumns": [],
                "attemptToConvertTypes": False,
                "convertFieldsToString": False,
            },
        },
    }


# ---------------------------------------------------------------------------
# Connection builder
# ---------------------------------------------------------------------------

def _build_connections(
    agent: AgentDefinition,
    tools: list[Tool],
    has_command: bool,
) -> dict[str, Any]:
    """Wire every node together.

    Non-callable flow: Trigger → [If] → Agent → Reply
    Callable flow:     Trigger → Normalize Telegram → [If] → Agent → Has chat_id? → Reply
                       Execute Workflow Trigger → Normalize Workflow → [If] → Agent → Has chat_id? → Reply

    Sub-connections: ChatModel →(ai_languageModel)→ Agent
                     Tools     →(ai_tool)→ Agent
    """
    agent_name = f"{agent.name} agent"
    is_callable = agent.callable
    is_workflow_only = agent.trigger.type == "workflow"
    conns: dict[str, Any] = {}

    if is_workflow_only:
        # -- Workflow-only: single entry via Execute Workflow Trigger
        conns["Execute Workflow Trigger"] = _main_out("Normalize Workflow Input")
        conns["Normalize Workflow Input"] = _main_out(agent_name)
        conns[agent_name] = _main_out("Has chat_id?")
        conns["Has chat_id?"] = _main_out("Reply")
    elif is_callable:
        # -- Callable: both triggers feed through normalization Set nodes
        conns["Telegram Trigger"] = _main_out("Normalize Telegram Input")
        conns["Execute Workflow Trigger"] = _main_out("Normalize Workflow Input")

        # The target after normalization is either the If command gate or the Agent directly
        if has_command:
            if_name = f"Is {agent.trigger.command}?"
            normalize_target = if_name
            conns[if_name] = _main_out(agent_name)
        else:
            normalize_target = "Not a /run command?"
            conns["Not a /run command?"] = _main_out(agent_name)

        conns["Normalize Telegram Input"] = _main_out(normalize_target)
        conns["Normalize Workflow Input"] = _main_out(normalize_target)

        # Agent → Has chat_id? → Reply (guard against headless calls)
        conns[agent_name] = _main_out("Has chat_id?")
        conns["Has chat_id?"] = _main_out("Reply")
    else:
        # -- Non-callable: original direct wiring
        if has_command:
            if_name = f"Is {agent.trigger.command}?"
            conns["Telegram Trigger"] = _main_out(if_name)
            conns[if_name] = _main_out(agent_name)
        else:
            conns["Telegram Trigger"] = _main_out("Not a /run command?")
            conns["Not a /run command?"] = _main_out(agent_name)

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

    # -- Memory → Agent (optional)
    if agent.memory is not None:
        conns["Chat Memory"] = {
            "ai_memory": [[{"node": agent_name, "type": "ai_memory", "index": 0}]],
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
