# Council Architecture: Domain-Driven Agent Definitions

## Problem

Agent workflows are hand-crafted n8n JSON. Adding a new agent means manually building a workflow in the n8n UI or copying/editing JSON. The domain logic (what an agent is) is entangled with the execution platform (how it runs on n8n), the LLM provider (which model it uses), and the integrations (which tools it has).

This makes it hard to:
- Add new agents quickly
- Switch LLM providers without rebuilding workflows
- Move to a different execution platform
- Let agents create other agents

## Solution

A four-layer Python architecture where agents are defined in TOML files and compiled into n8n workflows automatically.

## Architecture Layers

### Layer 1: Domain — What agents ARE

Pure business identity. No tech, no providers, no platforms.

Each agent is defined in a TOML file (`agents/<name>.toml`) that declares its name, role, system prompt, capabilities, and expected artifacts. The domain layer reads these files and validates them against a Pydantic model.

```toml
name = "Gimli"
role = "Builder"
brain = "gemini/gemini-flash-latest"

prompt = """
You are Gimli, a builder agent in the Council of Elrond.
You love building things and shipping code...
"""

tools = [
    "github.list_issues",
    "github.read_file",
    "github.create_issue",
]

artifacts = [
    "github.pull_request",
]

[trigger]
type = "telegram"
command = "/run gimli"

[reply]
type = "telegram"
```

Python model:

```python
TriggerType = Literal["telegram", "webhook", "cron"]
ReplyType = Literal["telegram", "webhook"]

class Trigger(BaseModel):
    type: TriggerType
    command: str | None = None  # required for telegram (e.g. "/run gimli")
    path: str | None = None     # required for webhook
    schedule: str | None = None # required for cron

class Reply(BaseModel):
    type: ReplyType

class AgentDefinition(BaseModel):
    name: str
    role: str
    brain: str          # litellm provider/model format (e.g. "gemini/gemini-flash-latest")
    prompt: str
    tools: list[str]    # dotted references to tool catalog (e.g. "github.read_file")
    artifacts: list[str] # declared artifact types; validated but not compiled in MVP
    trigger: Trigger
    reply: Reply
```

Convention: if a TOML file exists in `agents/`, the agent is live. No separate activation config.

### Layer 2: Casting — What BRAIN they use

The `brain` field in each agent definition uses LiteLLM's `provider/model` format (e.g., `gemini/gemini-flash-latest`, `anthropic/claude-sonnet`, `openai/gpt-4o`).

The casting module reads all agent definitions, collects unique brain values, and generates a `litellm_config.yaml`:

```yaml
model_list:
  - model_name: gemini/gemini-flash-latest
    litellm_params:
      model: gemini/gemini-flash-latest
      api_key: os.environ/GEMINI_API_KEY
  - model_name: anthropic/claude-sonnet
    litellm_params:
      model: anthropic/claude-sonnet
      api_key: os.environ/ANTHROPIC_API_KEY
```

Provider API keys come from `.env`. Only keys for providers actually referenced by agents are required.

The $5/day budget constraint is enforced at the LiteLLM level — LiteLLM has built-in spend tracking and budget limits per model/key.

### Layer 3: Wiring — What INTEGRATIONS they use

Tools are defined in Python as typed `HttpTool` instances in a tool catalog:

```python
# council/wiring/tools/models.py

class Param(BaseModel):
    """A parameter the AI agent must provide when calling a tool."""
    description: str
    type: str = "string"  # "string", "number", "json"

class BearerToken(BaseModel):
    """Auth via Bearer token from an environment variable."""
    env: str  # env var name (e.g. "GITHUB_TOKEN")

class JsonBody(BaseModel):
    """Structured JSON body the AI agent must provide."""
    schema: dict[str, str]  # field_name -> type hint for AI

class HttpTool(BaseModel):
    """A tool that an AI agent can invoke. Compiled to an n8n httpRequestTool node."""
    name: str
    description: str        # shown to the AI agent to decide when to use this tool
    url: str                # URL template; {placeholders} for AI params, {owner}/{repo} from project config
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    params: dict[str, Param] = {}   # AI-provided parameters (compiled to $fromAI() in n8n URL)
    auth: BearerToken | None = None
    headers: dict[str, str] = {}
    body: JsonBody | None = None    # for POST/PUT; compiled to $fromAI() JSON body in n8n
```

Example tool definition:

```python
# council/wiring/tools/github.py

read_file = HttpTool(
    name="Read File",
    description="Read a single file from the GitHub repository.",
    url="https://api.github.com/repos/{owner}/{repo}/contents/{filepath}",
    method="GET",
    params={"filepath": Param(description="Path to file, e.g. README.md")},
    auth=BearerToken(env="GITHUB_TOKEN"),
    headers={"Accept": "application/vnd.github.raw+json"},
)
```

**URL placeholders:** `{owner}` and `{repo}` are resolved from a project-level config (`council.toml` at the repo root). AI-provided params (those listed in `params`) are compiled to n8n `$fromAI()` expressions. Non-param placeholders are resolved at compile time.

**Tool reference resolution:** when an agent definition references `"github.read_file"`, the tool registry resolves the dotted string by importing `council.wiring.tools.github` and looking up the `read_file` attribute. The format is always `module_name.variable_name`.

Triggers and reply channels are similarly resolved from type declarations to concrete integration definitions.

### Layer 4: Adapter — HOW it runs on n8n

The adapter compiles a fully resolved agent (definition + tools + trigger + reply) into n8n workflow JSON.

Every agent compiles to the same workflow shape:

```
Trigger Node → AI Agent Node → Reply Node
                   |
                   ├── OpenAI Chat Model (→ LiteLLM)
                   └── HTTP Request Tool × N
```

Key nodes:
- **Trigger**: mapped from `trigger.type` → n8n node (`telegramTrigger`, `webhook`, `scheduleTrigger`)
- **AI Agent**: n8n's `@n8n/n8n-nodes-langchain.agent` node, handles tool-calling loop
- **OpenAI Chat Model**: `@n8n/n8n-nodes-langchain.lmChatOpenAi` pointed at `http://litellm:4000` with the agent's brain as model name. LiteLLM makes every provider OpenAI-compatible.
- **Tool nodes**: one `httpRequestTool` per tool, compiled from the `HttpTool` definitions
- **Reply**: mapped from `reply.type` → n8n node (`telegram`, `respondWebhook`). For Telegram replies, the adapter wires the chat ID from the trigger node's output using an n8n expression: `={{ $('Telegram Trigger').item.json.message.chat.id }}`.

The adapter also handles:
- n8n credential creation (Telegram, etc.) from env vars
- Workflow upsert via n8n REST API
- Workflow activation

Generated workflow JSON is ephemeral — not committed to git. The TOML definitions are the source of truth.

## Build Pipeline

The build is split into two phases to avoid a circular dependency: workflows must not activate before LiteLLM is reachable, but LiteLLM needs a config generated from agent definitions.

**Phase 1 — Config generation** (`python -m council config`):

1. Read `agents/*.toml` → validate → `list[AgentDefinition]`
2. Collect unique `brain` values across all agents
3. Generate `litellm_config.yaml` → write to shared volume
4. Exit

**Phase 2 — Deployment** (`python -m council deploy`):

1. Read `agents/*.toml` → validate → `list[AgentDefinition]`
2. Resolve tools from catalog for each agent
3. Create n8n credentials from env vars (Telegram, etc.)
4. For each agent: compile to n8n workflow JSON → upsert via API → activate
5. Exit

## Docker Compose Topology

```
services:
  n8n            — workflow engine (port 5678)
  litellm        — LLM proxy (port 4000, internal)
  n8n-mcp        — Claude Code access (port 3000)
  seed-config    — python -m council config, generates litellm config, exits
  seed-deploy    — python -m council deploy, deploys workflows, exits
```

Boot sequence:

1. `seed-config` starts → reads TOML, generates `litellm_config.yaml` → exits
2. `litellm` starts (depends: `seed-config` completed) → reads generated config → healthy
3. `n8n` starts → healthy
4. `seed-deploy` starts (depends: `n8n` healthy AND `litellm` healthy) → deploys workflows → exits
5. `n8n-mcp` starts (depends: `n8n` healthy)

This ensures workflows are never active before LiteLLM is reachable.

## File Structure

```
council.toml             # project-level config (owner, repo, etc.)
Dockerfile.council       # Python 3.12-slim + council package + dependencies

council/
  __main__.py            # entry point: "config" and "deploy" subcommands
  domain/
    __init__.py
    agent.py             # AgentDefinition, Trigger, Reply models
    loader.py            # reads agents/*.toml → list[AgentDefinition]
  casting/
    __init__.py
    litellm.py           # generates litellm_config.yaml from agent brains
  wiring/
    __init__.py
    tools/
      __init__.py        # tool registry (dotted name → HttpTool resolution)
      github.py          # GitHub tool definitions
      models.py          # HttpTool, BearerToken, Param, JsonBody models
    triggers.py          # trigger type definitions
    channels.py          # reply channel definitions
  adapters/
    __init__.py
    n8n/
      __init__.py
      compiler.py        # AgentDefinition → n8n workflow JSON
      deployer.py        # upsert via n8n REST API
      credentials.py     # create n8n credentials from env

agents/
  gimli.toml             # first agent

tests/
  test_domain/
  test_casting/
  test_wiring/
  test_adapters/
```

The `seed-config` and `seed-deploy` services both use the same `Dockerfile.council` image, differing only in the command argument (`config` vs `deploy`).

## MVP Scope

The MVP proves the architecture end-to-end with one agent:

1. Gimli defined in `agents/gimli.toml`
2. GitHub tools in the tool catalog (list_issues, read_file, create_issue)
3. LiteLLM config generation
4. n8n workflow compilation and deployment
5. LiteLLM service in docker-compose
6. Seed container runs Python instead of shell script

The existing hand-crafted workflow JSON files become obsolete — replaced by generated output.

## Implementation Approach

TDD throughout. For each module:
1. Write failing tests that define the expected behavior
2. Implement until tests pass
3. Refactor

## Risks and Mitigations

**Risk:** The single workflow shape (trigger → agent → reply) may not fit all agent types.
**Mitigation:** Build for Gimli only. Extend the compiler when a second agent needs a different shape.

**Risk:** `@n8n/n8n-nodes-langchain.lmChatOpenAi` node may not support custom base URLs cleanly.
**Mitigation:** Verify with a manual test before building the compiler. Fall back to raw HTTP Request nodes for LLM calls if needed.

**Risk:** LiteLLM adds latency and a failure point.
**Mitigation:** LiteLLM is on the same Docker network — latency is negligible. Health checks ensure it's up before workflows execute.

## Future Extensions

These are out of MVP scope but have been considered in the architecture. They should require additive changes, not redesigns.

### Conversational agents

An agent that maintains multi-turn context (e.g., a council status agent you chat with directly). Requires:

- A `memory` field in the agent definition (e.g., `memory = "buffer"` or `memory = "window"`).
- The compiler attaches an n8n memory node (`memoryBufferWindow`, etc.) to the AI Agent node.
- The trigger likely has no command filter — the agent responds to all direct messages.

The TOML would look like:

```toml
name = "Elrond"
role = "Council Director"
brain = "anthropic/claude-sonnet"
memory = "window"

[trigger]
type = "telegram"
# no command — responds to all messages
```

### Multiple triggers per agent

An agent that responds to both Telegram commands and GitHub issue events (e.g., Gimli responding to `/run gimli` AND issues tagged `gimli`). Requires:

- Changing `[trigger]` to `[[trigger]]` (TOML array of tables) in the schema.
- The compiler generates either multiple entry points in one workflow or multiple workflows sharing the same agent configuration.

```toml
[[trigger]]
type = "telegram"
command = "/run gimli"

[[trigger]]
type = "webhook"
path = "gimli-github"
```

### Agent-to-agent orchestration

A conversational agent (e.g., Elrond) creating tasks for other agents by writing GitHub issues with specific labels. This needs no architecture change — it's just a tool call (`github.create_issue` with a label convention like `agent:gimli`). The receiving agent picks it up via a webhook trigger on issue creation.

### Budget-aware casting

The casting layer dynamically selects models based on remaining daily budget. An agent might start on an expensive model and fall back to a cheaper one as the $5/day limit approaches. LiteLLM supports fallback chains and budget tracking natively — this would be configured in the generated `litellm_config.yaml`.
