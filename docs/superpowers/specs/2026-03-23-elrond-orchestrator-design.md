# Elrond Orchestrator Agent — Design Spec

## Goal

Add Elrond, the Head of the Council — an orchestrator agent that plans work, delegates to builder agents (Gimli), reviews results, and keeps the user informed via Telegram. Elrond has full autonomy to suggest and plan, but always waits for user approval before acting. The Council operates on a $5/day LLM budget.

## Agents and Roles

- **Elrond** — Orchestrator, planner, reviewer (temporary until Galadriel exists). Gemini Pro. Never writes code. Delegates to builders, creates issues, reviews PRs, manages memory.
- **Gimli** — Builder. Gemini Flash. Writes code, creates PRs. Can be triggered by Telegram or by Elrond via Execute Workflow.
- **Galadriel** (future) — Dedicated code reviewer. Not part of this spec.

## Architecture

### Approach: n8n-native orchestration

All agents remain n8n workflows compiled from TOML definitions. Agent-to-agent communication uses n8n's Execute Workflow node. No external orchestration service.

## Elrond's Behavior

### Three modes

1. **Conversational** — User messages Elrond on Telegram, he responds with context from memory. Normal chat.
2. **Suggestive** — Elrond proactively proposes work ("I think Gimli should tackle issue #12"). Always waits for user approval.
3. **Delegating** — After approval, creates a GitHub issue as the work spec, then triggers Gimli's workflow via Execute Workflow.

### Delegation flow

1. Elrond creates a GitHub issue with a well-structured body (what to do, acceptance criteria, context).
2. Elrond triggers Gimli's workflow via Execute Workflow node, passing the issue number and instructions.
3. Gimli works — reads the issue, writes code, creates a PR.
4. Elrond reviews the PR diff via `github.read_pr`.
5. Elrond reports to the user on Telegram: what was done, whether it looks good, any concerns.
6. User approves ("looks good, merge it") or redirects ("change X").
7. Elrond merges the PR or sends Gimli back to fix it.

### Budget awareness

Elrond tracks spending in `memories/budget.md`. The $5/day budget covers all LLM calls across all agents. Elrond factors cost into planning decisions (e.g., preferring Gimli on Flash over doing things himself on Pro).

## Memory System

### Short-term: Window Buffer Memory (n8n)

The n8n AI Agent node gets a `memoryBufferWindow` sub-node wired via the `ai_memory` connection type. This gives Elrond conversational context — the last N messages in the Telegram chat. Configured via a new `[memory]` section in the TOML:

```toml
[memory]
type = "window_buffer"
window_size = 10
```

### Long-term: Git-backed markdown files

A `memories/` directory in the GitHub repo, read and written via GitHub API tools:

```
memories/
  decisions.md      — why things are the way they are
  agents.md         — who exists, what they do, strengths/weaknesses
  project-state.md  — what's done, in flight, planned
  budget.md         — spending log, remaining daily budget
```

Elrond's system prompt instructs him to read relevant memory files before responding and update them after making decisions or completing work.

## Error Handling

MVP error handling — keep it simple, improve later:

- **Gimli's workflow fails:** n8n's Execute Workflow node propagates errors to the caller. Elrond's workflow catches the error (n8n has built-in error handling per node) and reports the failure to the user on Telegram: "Gimli hit an error: [message]. Want me to retry or try a different approach?"
- **GitHub API rejects a call:** The HTTP tool node returns an error response. The AI Agent sees the error in the tool output and can reason about it (e.g., "merge conflict — need to rebase"). Elrond reports to the user.
- **Budget exceeded:** Elrond checks `memories/budget.md` before delegating. If remaining budget is too low, he says so and waits for the next day. This is advisory — there's no hard enforcement at the LiteLLM level in MVP. Hard budget limits via LiteLLM's budget config can be added later.
- **Execute Workflow timeout:** n8n has a default execution timeout. If Gimli takes too long, the Execute Workflow node errors and Elrond reports it.

No custom error nodes or retry logic in MVP. The AI Agent's natural language reasoning handles most error cases by reporting them to the user.

## Telegram Routing

Both Elrond and Gimli share the same Telegram bot. Both workflows receive every message via their Telegram Trigger webhooks.

- **Gimli** has an If node filtering for `/run gimli` — only processes matching messages, drops the rest.
- **Elrond** has no command, so he processes everything. To avoid Elrond also responding to `/run gimli` messages, Elrond gets a negative filter: an If node that checks the message does NOT start with `/run`. This is a new compiler behavior: when `command` is absent but other agents have commands, add a "not a command" filter.

Implementation: The compiler adds an If node to command-less agents that rejects messages starting with `/run `. This is simple and scales — any new `/run X` agent is automatically excluded from Elrond's processing.

## TOML Definitions

### Elrond

```toml
name = "Elrond"
role = "Head of the Council"
brain = "gemini/gemini-2.5-pro-preview-05-06"
orchestrator = true

prompt = """
You are Elrond, Head of the Council. You are wise, strategic, and see the big picture.

You have full control over the Council's agents and a $5/day budget across all of them.
You never write code yourself — you delegate to builders like Gimli.

Before acting, always read your memory files from the memories/ directory.
After making decisions or completing work, update them.

RULES:
- Always propose before acting. Explain what you want to do and wait for approval.
- Create a GitHub issue before delegating work to an agent.
- After an agent completes work, review it and summarize for the user.
- Track spending in memories/budget.md.
- When something doesn't exist yet (an agent, a tool, a workflow), suggest creating it.
"""

tools = [
    "github.list_issues",
    "github.read_file",
    "github.create_issue",
    "github.update_file",
    "github.read_pr",
    "github.merge_pr",
    "n8n.execute_workflow",
]

[trigger]
type = "telegram"

[reply]
type = "telegram"

[memory]
type = "window_buffer"
window_size = 10
```

No `command` on the trigger — Elrond catches all messages that aren't directed at another agent (no `/run` prefix).

### Gimli (changes)

```toml
callable = true
```

Added to the existing `gimli.toml`. Tells the compiler to add an Execute Workflow Trigger node as a second entry point.

## New Tools

### github.update_file

HTTP PUT to `https://api.github.com/repos/{owner}/{repo}/contents/{filepath}`. Requires the file's current SHA and base64-encoded content. Used by Elrond to write memory files and agent TOMLs.

**SHA dependency:** The GitHub Contents API requires the current file SHA for updates. This means the LLM must call `read_file` first to get the SHA, then `update_file` with it. This is a known fragile pattern — the system prompt must explicitly instruct Elrond: "To update a file, first read it to get the SHA, then update with that SHA." The tool's `description` field also includes this instruction. The `sha` parameter is part of the tool's `params` definition.

Alternative considered: a wrapper tool that does read-then-write atomically. Rejected for now — it would require a custom n8n node or a proxy service, adding infrastructure. The prompt-guided two-step is good enough for MVP and can be revisited if it proves unreliable.

### github.read_pr

HTTP GET to `https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}`. Returns PR metadata, diff, and review status. Used by Elrond to review Gimli's work.

### github.merge_pr

HTTP PUT to `https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge`. Merges an approved PR. Used by Elrond after user approval.

### n8n.execute_workflow

Not an HTTP tool — this is a native n8n node (`n8n-nodes-base.executeWorkflow`). Triggers another agent's workflow by ID, passing input data. The workflow ID is resolved at deploy time from the workflow registry.

This requires a new base type in the tool system. The current `HttpTool` model won't work. Introduce a `WorkflowTool` model:

```python
class WorkflowTool(BaseModel):
    """A tool that triggers another agent's n8n workflow."""
    name: str
    description: str
    target_agent: str  # agent name, resolved to workflow ID at deploy time
```

The tool registry's `resolve_tool()` currently returns `HttpTool` and validates with `isinstance(tool, HttpTool)`. Change it to:
- Define `Tool = HttpTool | WorkflowTool` union type in `models.py`.
- `resolve_tool()` returns `Tool` and validates with `isinstance(tool, (HttpTool, WorkflowTool))`.
- `resolve_tools()` returns `list[Tool]`.
- The compiler dispatches based on type: `isinstance(tool, HttpTool)` → `_tool_node()`, `isinstance(tool, WorkflowTool)` → `_execute_workflow_tool_node()`.
- Internal helpers (`_build_nodes`, `_build_connections`) update their type signatures to accept `list[Tool]`.

The `n8n.execute_workflow` module exports a static instance (same pattern as the GitHub tools):

```python
# council/wiring/tools/n8n.py
execute_workflow = WorkflowTool(
    name="Execute Gimli",
    description="Trigger Gimli's workflow to execute a task. Pass instructions as input.",
    target_agent="Gimli",
)
```

For now, hardcode to Gimli. When more callable agents exist, this becomes a parameterized factory or multiple tool instances.

## Compiler Extensions

### 1. Window Buffer Memory node

When `[memory]` is present in the TOML, the compiler adds a `@n8n/n8n-nodes-langchain.memoryBufferWindow` node and wires it to the AI Agent via the `ai_memory` connection type.

```python
{
    "name": "Chat Memory",
    "type": "@n8n/n8n-nodes-langchain.memoryBufferWindow",
    "typeVersion": 1.3,
    "position": [400, 300],
    "parameters": {
        "sessionIdType": "customKey",
        "sessionKey": "={{ $json.chat_id }}",  # from normalized Set node
        "contextWindowLength": 10,  # from window_size
    },
}
```

Note: The `sessionKey` reads from the normalized `$json.chat_id` (set by the dual-path merge pattern for callable agents, or directly from Telegram Trigger for non-callable agents). This assumes Telegram is the only trigger type with memory — true for MVP. If webhook/cron triggers need memory later, the session key source must be generalized.

Connection:
```python
"Chat Memory": {
    "ai_memory": [[{"node": "<agent_name> agent", "type": "ai_memory", "index": 0}]],
}
```

### 2. Execute Workflow Trigger node

When `callable = true`, the compiler adds an `n8n-nodes-base.executeWorkflowTrigger` node as a second entry point.

The AI Agent's `text` expression must handle both trigger sources without erroring. n8n throws a reference error when accessing a node that didn't fire, so we cannot use simple `||` fallthrough. Instead, use n8n's `$execution.mode` or route each trigger through separate paths that converge at the AI Agent:

**Approach: Dual-path merge.** Each trigger gets its own path to a Set node that normalizes the input into a common shape (`instructions` and `chat_id` fields). Both Set nodes connect to the AI Agent. The AI Agent reads `{{ $json.instructions }}` — always present regardless of which trigger fired.

- **Telegram path:** Telegram Trigger → Set node (extracts `message.text`, strips command prefix, sets `chat_id` from `message.chat.id`)
- **Execute Workflow path:** Execute Workflow Trigger → Set node (passes through `instructions` and `chat_id` from caller input)

This also solves the Reply node problem: the Reply node reads `chat_id` from the normalized `$json.chat_id` instead of reaching back to the Telegram Trigger. When Elrond calls Gimli, Elrond passes the user's `chat_id` so Gimli can reply on Telegram. If no `chat_id` is provided (headless execution), the Reply node is skipped via an If guard.

```
Telegram Trigger → Set (normalize) ──┐
                                      ├──→ [If command?] → AI Agent → If chat_id? → Reply
Execute Workflow Trigger → Set (normalize) ┘
```

### 3. Execute Workflow tool node

The `n8n.execute_workflow` tool compiles to an `n8n-nodes-base.executeWorkflow` tool node. Unlike HTTP tools, this is a native n8n node with a `workflowId` parameter resolved at deploy time.

The compiler's `compile_workflow` signature gains an optional parameter:

```python
def compile_workflow(
    agent: AgentDefinition,
    tools: list[HttpTool | WorkflowTool],
    litellm_base_url: str = "http://litellm:4000/v1",
    workflow_registry: dict[str, str] | None = None,
) -> dict[str, Any]:
```

When the compiler encounters a `WorkflowTool`, it calls `_execute_workflow_tool_node()` instead of `_tool_node()`:

```python
def _execute_workflow_tool_node(tool: WorkflowTool, workflow_registry: dict[str, str]) -> dict[str, Any]:
    workflow_id = workflow_registry[tool.target_agent]
    return {
        "name": tool.name,
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1,
        "position": [400, 400],
        "parameters": {
            "workflowId": workflow_id,
        },
    }
```

If `tool.target_agent` is missing from the registry, raise a `ValueError` with a clear message ("Agent 'X' not found in workflow registry — is it deployed?"). This catches typos and ordering bugs at deploy time.

### 4. Default trigger routing and negative command filter

Elrond has no `command`. In the current compiler this means no If node — Telegram Trigger wires directly to the AI Agent. However, with multiple agents on the same Telegram bot, Elrond must NOT process `/run` messages meant for other agents.

The compiler adds a negative-filter If node for agents without a `command`: rejects messages starting with `/run `. This ensures Elrond ignores messages like `/run gimli` that are meant for Gimli.

```python
def _negative_command_filter_node() -> dict[str, Any]:
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
```

Flow: Telegram Trigger → "Not a /run command?" → (true) → AI Agent.

### 5. Dual-path Set nodes for callable agents

When `callable = true`, the compiler adds Set nodes to normalize input from both trigger paths:

**Telegram Set node:**
```python
{
    "name": "Normalize Telegram Input",
    "type": "n8n-nodes-base.set",
    "typeVersion": 3.4,
    "position": [200, 0],
    "parameters": {
        "assignments": {
            "assignments": [
                {"name": "instructions", "value": "={{ $json.message.text.replace('/run gimli', '').trim() }}", "type": "string"},
                {"name": "chat_id", "value": "={{ $json.message.chat.id }}", "type": "string"},
            ]
        }
    },
}
```

**Execute Workflow Set node:**
```python
{
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
```

Both Set nodes connect to the downstream flow (If node or AI Agent). The AI Agent reads `{{ $json.instructions }}` and the Reply node reads `{{ $json.chat_id }}`.

## Domain Model Changes

### AgentDefinition

```python
class AgentDefinition(BaseModel):
    name: str
    role: str
    brain: str
    prompt: str
    tools: list[str] = []          # changed from required to optional ([] default)
    artifacts: list[str] = []      # changed from required to optional ([] default)
    trigger: Trigger
    reply: Reply
    callable: bool = False          # new
    orchestrator: bool = False      # new
    memory: MemoryConfig | None = None  # new
```

Note: `tools` and `artifacts` change from required to optional with empty list defaults. This is intentional — an orchestrator like Elrond always has tools, but future agents might not. The existing Gimli TOML already provides both fields so no breakage.

### MemoryConfig

```python
class MemoryConfig(BaseModel):
    type: Literal["window_buffer"]
    window_size: int = 10
```

## Deploy Order

Two-pass deployment to resolve workflow ID dependencies:

1. **Pass 1** — Deploy all agents where `orchestrator = False`. Collect `{agent_name: workflow_id}` registry.
2. **Pass 2** — Deploy all agents where `orchestrator = True`. The compiler receives the workflow registry so Execute Workflow nodes get the correct target IDs.

The `run_deploy()` function in `__main__.py` sorts agents into two groups and deploys in order.

## New Files

- `council/wiring/tools/github_write.py` — `update_file` tool definition
- `council/wiring/tools/github_pr.py` — `read_pr`, `merge_pr` tool definitions
- `council/wiring/tools/n8n.py` — `execute_workflow` tool definition (`WorkflowTool` type)
- `council/wiring/tools/models.py` — add `WorkflowTool` model, `Tool` union type
- `agents/elrond.toml` — Elrond agent definition
- `memories/decisions.md` — initial empty memory file
- `memories/agents.md` — initial agent registry
- `memories/project-state.md` — initial project state
- `memories/budget.md` — initial budget tracker

## Modified Files

- `council/domain/agent.py` — add `callable`, `orchestrator`, `MemoryConfig`, `memory` fields
- `council/adapters/n8n/compiler.py` — add memory node builder, execute workflow trigger, execute workflow tool node, conditional input expression
- `council/adapters/n8n/deployer.py` — no changes needed (already returns workflow IDs)
- `council/__main__.py` — two-pass deployment, workflow registry
- `council/wiring/tools/__init__.py` — register new tool modules
- `agents/gimli.toml` — add `callable = true`

## Testing

- Domain model tests: new fields parse correctly, defaults work
- Loader tests: TOML with `callable`, `orchestrator`, `[memory]` sections load correctly
- Compiler tests: memory node generated and wired, dual triggers, execute workflow node, conditional input expression
- Tool catalog tests: new tools resolve correctly
- Deploy order tests: orchestrators deploy after non-orchestrators, workflow registry passed correctly
