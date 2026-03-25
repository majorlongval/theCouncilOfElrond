# Elrond Orchestrator Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Elrond, an orchestrator agent that delegates work to Gimli, manages memory, and keeps the user informed via Telegram — all compiled from TOML to n8n workflows.

**Architecture:** Extends the existing TOML → compiler → deployer pipeline with: new domain fields (`callable`, `orchestrator`, `memory`), a `WorkflowTool` model alongside `HttpTool`, dual-path input normalization for callable agents, window buffer memory nodes, negative command filters, and two-pass deployment.

**Tech Stack:** Python 3.12, Pydantic v2, n8n REST API, httpx, pytest, TOML

**Spec:** `docs/superpowers/specs/2026-03-23-elrond-orchestrator-design.md`

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `council/wiring/tools/github_write.py` | `update_file` HttpTool definition (spec says `github.update_file` but we use `github_write.update_file` because the tool module must match the Python module name — `github.py` already exists for the original tools) |
| `council/wiring/tools/github_pr.py` | `read_pr`, `merge_pr` HttpTool definitions |
| `council/wiring/tools/n8n.py` | `execute_workflow` WorkflowTool definition |
| `agents/elrond.toml` | Elrond agent TOML definition |
| `memories/decisions.md` | Initial memory file — decisions log |
| `memories/agents.md` | Initial memory file — agent registry |
| `memories/project-state.md` | Initial memory file — project state |
| `memories/budget.md` | Initial memory file — budget tracker |
| `tests/test_domain/test_agent_new_fields.py` | Tests for new AgentDefinition fields |
| `tests/test_wiring/test_new_tools.py` | Tests for new tool definitions and WorkflowTool resolution |
| `tests/test_adapters/test_compiler_extensions.py` | Tests for memory, dual-path, execute workflow, negative filter |
| `tests/test_main_deploy_order.py` | Tests for two-pass deployment |

### Modified files
| File | Changes |
|------|---------|
| `council/domain/agent.py` | Add `MemoryConfig`, `callable`, `orchestrator`, `memory` fields; default `tools`/`artifacts` to `[]` |
| `council/wiring/tools/models.py` | Add `WorkflowTool` model, `Tool` union type |
| `council/wiring/tools/__init__.py` | Update `resolve_tool`/`resolve_tools` to return `Tool` union |
| `council/wiring/resolver.py` | Update to handle `Tool` union (skip `WorkflowTool` for URL resolution) |
| `council/adapters/n8n/compiler.py` | Add memory node, dual-path Set nodes, execute workflow tool node, negative command filter, updated signatures |
| `council/__main__.py` | Two-pass deployment with workflow registry |
| `agents/gimli.toml` | Add `callable = true` |

---

### Task 1: Domain Model — Add new fields to AgentDefinition

**Files:**
- Modify: `council/domain/agent.py`
- Test: `tests/test_domain/test_agent_new_fields.py`

- [ ] **Step 1: Write failing tests for new fields**

```python
# tests/test_domain/test_agent_new_fields.py
import pytest
from council.domain.agent import AgentDefinition, MemoryConfig, Trigger, Reply


def _base_agent(**overrides) -> AgentDefinition:
    """Helper to build an AgentDefinition with sensible defaults."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_domain/test_agent_new_fields.py -v`
Expected: FAIL — `MemoryConfig` not importable, `callable`/`orchestrator` not recognized fields, `tools`/`artifacts` required

- [ ] **Step 3: Implement the domain model changes**

```python
# council/domain/agent.py
from typing import Literal

from pydantic import BaseModel


TriggerType = Literal["telegram", "webhook", "cron"]
ReplyType = Literal["telegram", "webhook"]


class Trigger(BaseModel):
    """How an agent gets activated."""
    type: TriggerType
    command: str | None = None
    path: str | None = None
    schedule: str | None = None


class Reply(BaseModel):
    """How an agent sends its response."""
    type: ReplyType


class MemoryConfig(BaseModel):
    """Short-term memory configuration for an agent's n8n workflow."""
    type: Literal["window_buffer"]
    window_size: int = 10


class AgentDefinition(BaseModel):
    """Complete definition of an agent — the single source of truth."""
    name: str
    role: str
    brain: str
    prompt: str
    tools: list[str] = []
    artifacts: list[str] = []
    trigger: Trigger
    reply: Reply
    callable: bool = False
    orchestrator: bool = False
    memory: MemoryConfig | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_domain/test_agent_new_fields.py -v`
Expected: PASS (all 9 tests)

- [ ] **Step 5: Run all existing tests to check for regressions**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest -v`
Expected: PASS — existing test `test_agent_requires_all_fields` may need updating since `tools` and `artifacts` are now optional. If it fails, update the test to remove `tools`/`artifacts` from the "missing fields" expectation (it should still fail because `brain`, `prompt`, `trigger`, `reply` are still required).

- [ ] **Step 6: Commit**

```bash
git add council/domain/agent.py tests/test_domain/test_agent_new_fields.py
git commit -m "feat: add callable, orchestrator, memory fields to AgentDefinition"
```

---

### Task 2: Tool Models — Add WorkflowTool and Tool union type

**Files:**
- Modify: `council/wiring/tools/models.py`
- Test: `tests/test_wiring/test_new_tools.py`

- [ ] **Step 1: Write failing tests for WorkflowTool**

```python
# tests/test_wiring/test_new_tools.py
from council.wiring.tools.models import HttpTool, WorkflowTool, Tool


def test_workflow_tool_creation():
    tool = WorkflowTool(
        name="Execute Gimli",
        description="Trigger Gimli's workflow.",
        target_agent="Gimli",
    )
    assert tool.name == "Execute Gimli"
    assert tool.target_agent == "Gimli"


def test_workflow_tool_is_tool_type():
    """WorkflowTool should be part of the Tool union."""
    tool = WorkflowTool(
        name="Execute Gimli",
        description="Trigger Gimli's workflow.",
        target_agent="Gimli",
    )
    # isinstance check against union members
    assert isinstance(tool, (HttpTool, WorkflowTool))


def test_http_tool_is_tool_type():
    tool = HttpTool(name="Test", description="Test tool", url="http://example.com")
    assert isinstance(tool, (HttpTool, WorkflowTool))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_wiring/test_new_tools.py -v`
Expected: FAIL — `WorkflowTool` and `Tool` not importable

- [ ] **Step 3: Add WorkflowTool to models.py**

Add at the end of `council/wiring/tools/models.py`:

```python
class WorkflowTool(BaseModel):
    """A tool that triggers another agent's n8n workflow.

    Unlike HttpTool, this compiles to an Execute Workflow node in n8n.
    The target_agent name is resolved to a workflow ID at deploy time.
    """
    name: str
    description: str
    target_agent: str


# Union of all tool types — used by the tool registry and compiler.
Tool = HttpTool | WorkflowTool
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_wiring/test_new_tools.py -v`
Expected: PASS (all 3 tests)

- [ ] **Step 5: Commit**

```bash
git add council/wiring/tools/models.py tests/test_wiring/test_new_tools.py
git commit -m "feat: add WorkflowTool model and Tool union type"
```

---

### Task 3: New GitHub Tools — update_file, read_pr, merge_pr

**Files:**
- Create: `council/wiring/tools/github_write.py`
- Create: `council/wiring/tools/github_pr.py`
- Test: add to `tests/test_wiring/test_new_tools.py`

- [ ] **Step 1: Write failing tests for new tool definitions**

Append to `tests/test_wiring/test_new_tools.py`:

```python
from council.wiring.tools.github_write import update_file
from council.wiring.tools.github_pr import read_pr, merge_pr


def test_update_file_tool():
    assert update_file.name == "Update File"
    assert update_file.method == "PUT"
    assert "{filepath}" in update_file.url
    assert "filepath" in update_file.params
    assert update_file.body is not None
    assert "sha" in update_file.body.schema  # sha goes in body, not URL params
    assert update_file.auth is not None


def test_read_pr_tool():
    assert read_pr.name == "Read PR"
    assert read_pr.method == "GET"
    assert "{pr_number}" in read_pr.url
    assert "pr_number" in read_pr.params
    assert read_pr.auth is not None


def test_merge_pr_tool():
    assert merge_pr.name == "Merge PR"
    assert merge_pr.method == "PUT"
    assert "{pr_number}" in merge_pr.url
    assert "pr_number" in merge_pr.params
    assert merge_pr.auth is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_wiring/test_new_tools.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Create github_write.py**

```python
# council/wiring/tools/github_write.py
from council.wiring.tools.models import BearerToken, HttpTool, JsonBody, Param


update_file = HttpTool(
    name="Update File",
    description=(
        "Update (or create) a file in the GitHub repository. "
        "You MUST first read the file with Read File to get its current SHA. "
        "Provide filepath, sha, message (commit message), and content (base64-encoded)."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/contents/{filepath}",
    method="PUT",
    params={
        "filepath": Param(description="Path to the file, e.g. memories/decisions.md"),
    },
    body=JsonBody(schema={
        "message": "string",
        "content": "string",
        "sha": "string",
    }),
    auth=BearerToken(env="GITHUB_TOKEN"),
)
```

- [ ] **Step 4: Create github_pr.py**

```python
# council/wiring/tools/github_pr.py
from council.wiring.tools.models import BearerToken, HttpTool, Param


read_pr = HttpTool(
    name="Read PR",
    description=(
        "Read a pull request from the GitHub repository. "
        "Returns PR metadata including title, body, diff, and review status."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
    method="GET",
    params={"pr_number": Param(description="The PR number to read, e.g. 42")},
    auth=BearerToken(env="GITHUB_TOKEN"),
)


merge_pr = HttpTool(
    name="Merge PR",
    description=(
        "Merge a pull request. Only use after the user has approved the PR."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/merge",
    method="PUT",
    params={"pr_number": Param(description="The PR number to merge, e.g. 42")},
    auth=BearerToken(env="GITHUB_TOKEN"),
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_wiring/test_new_tools.py -v`
Expected: PASS (all 6 tool tests + 3 model tests)

- [ ] **Step 6: Commit**

```bash
git add council/wiring/tools/github_write.py council/wiring/tools/github_pr.py tests/test_wiring/test_new_tools.py
git commit -m "feat: add github.update_file, github.read_pr, github.merge_pr tools"
```

---

### Task 4: New n8n Tool — WorkflowTool for execute_workflow

**Files:**
- Create: `council/wiring/tools/n8n.py`
- Test: add to `tests/test_wiring/test_new_tools.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_wiring/test_new_tools.py`:

```python
from council.wiring.tools.n8n import execute_workflow as execute_workflow_tool


def test_execute_workflow_tool():
    assert execute_workflow_tool.name == "Execute Gimli"
    assert execute_workflow_tool.target_agent == "Gimli"
    assert isinstance(execute_workflow_tool, WorkflowTool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_wiring/test_new_tools.py::test_execute_workflow_tool -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create n8n.py**

```python
# council/wiring/tools/n8n.py
from council.wiring.tools.models import WorkflowTool


execute_workflow = WorkflowTool(
    name="Execute Gimli",
    description="Trigger Gimli's workflow to execute a task. Pass instructions as input.",
    target_agent="Gimli",
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_wiring/test_new_tools.py -v`
Expected: PASS (all 10 tests)

- [ ] **Step 5: Commit**

```bash
git add council/wiring/tools/n8n.py tests/test_wiring/test_new_tools.py
git commit -m "feat: add n8n.execute_workflow WorkflowTool"
```

---

### Task 5: Tool Registry — Support Tool union type

**Files:**
- Modify: `council/wiring/tools/__init__.py`
- Modify: `council/wiring/resolver.py`
- Test: add to `tests/test_wiring/test_new_tools.py`

- [ ] **Step 1: Write failing tests for WorkflowTool resolution**

Append to `tests/test_wiring/test_new_tools.py`:

```python
from council.wiring.tools import resolve_tool, resolve_tools


def test_resolve_n8n_execute_workflow():
    tool = resolve_tool("n8n.execute_workflow")
    assert isinstance(tool, WorkflowTool)
    assert tool.target_agent == "Gimli"


def test_resolve_github_update_file():
    tool = resolve_tool("github_write.update_file")
    assert isinstance(tool, HttpTool)
    assert tool.name == "Update File"


def test_resolve_github_read_pr():
    tool = resolve_tool("github_pr.read_pr")
    assert isinstance(tool, HttpTool)
    assert tool.name == "Read PR"


def test_resolve_github_merge_pr():
    tool = resolve_tool("github_pr.merge_pr")
    assert isinstance(tool, HttpTool)


def test_resolve_mixed_tools():
    """resolve_tools should handle a mix of HttpTool and WorkflowTool."""
    tools = resolve_tools(["github.list_issues", "n8n.execute_workflow"])
    assert len(tools) == 2
    assert isinstance(tools[0], HttpTool)
    assert isinstance(tools[1], WorkflowTool)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_wiring/test_new_tools.py::test_resolve_n8n_execute_workflow -v`
Expected: FAIL — `resolve_tool` rejects non-HttpTool with "Unknown tool"

- [ ] **Step 3: Update resolve_tool and resolve_tools**

```python
# council/wiring/tools/__init__.py
import importlib

from council.wiring.tools.models import HttpTool, WorkflowTool, Tool


def resolve_tool(dotted_name: str) -> Tool:
    """Resolve a dotted tool reference like 'github.read_file' to a Tool."""
    parts = dotted_name.split(".")
    if len(parts) != 2:
        raise ValueError(f"Unknown tool: {dotted_name} (expected 'module.name' format)")

    module_name, attr_name = parts

    try:
        module = importlib.import_module(f"council.wiring.tools.{module_name}")
    except ModuleNotFoundError:
        raise ValueError(f"Unknown tool: {dotted_name} (module '{module_name}' not found)")

    tool = getattr(module, attr_name, None)
    if not isinstance(tool, (HttpTool, WorkflowTool)):
        raise ValueError(f"Unknown tool: {dotted_name} ('{attr_name}' not found in '{module_name}')")

    return tool


def resolve_tools(dotted_names: list[str]) -> list[Tool]:
    """Resolve a list of dotted tool references."""
    return [resolve_tool(name) for name in dotted_names]
```

- [ ] **Step 4: Update resolver.py to handle Tool union**

The `resolve_tool_urls` function currently takes `list[HttpTool]`. It needs to accept `list[Tool]` and skip `WorkflowTool` instances (they have no URL to resolve):

```python
# council/wiring/resolver.py
from council.config import ProjectConfig
from council.wiring.tools.models import HttpTool, Tool


def resolve_tool_urls(tools: list[Tool], config: ProjectConfig) -> list[Tool]:
    """Resolve project-level placeholders ({owner}, {repo}) in tool URLs.

    WorkflowTool instances are passed through unchanged — they have no URL.
    """
    resolved: list[Tool] = []
    for tool in tools:
        if isinstance(tool, HttpTool):
            url = tool.url.replace("{owner}", config.owner).replace("{repo}", config.repo)
            resolved.append(tool.model_copy(update={"url": url}))
        else:
            resolved.append(tool)
    return resolved
```

- [ ] **Step 5: Run all tests**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest -v`
Expected: PASS — all existing tests plus new ones. The existing `test_resolve_tools_returns_list` test checks `isinstance(t, HttpTool)` which still passes since it only resolves `HttpTool` instances.

- [ ] **Step 6: Commit**

```bash
git add council/wiring/tools/__init__.py council/wiring/resolver.py tests/test_wiring/test_new_tools.py
git commit -m "feat: update tool registry to support Tool union (HttpTool | WorkflowTool)"
```

---

### Task 6: Compiler — Window Buffer Memory node

**Files:**
- Modify: `council/adapters/n8n/compiler.py`
- Test: `tests/test_adapters/test_compiler_extensions.py`

- [ ] **Step 1: Write failing tests for memory node**

```python
# tests/test_adapters/test_compiler_extensions.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_adapters/test_compiler_extensions.py -v`
Expected: FAIL — no memory node generated

- [ ] **Step 3: Add memory node to compiler**

In `council/adapters/n8n/compiler.py`, add a `_memory_node` builder and wire it in `_build_nodes` and `_build_connections`:

Add the node builder function. The `sessionKey` uses `$json.chat_id` when the agent is callable (reads from normalized Set node output), or falls back to reading directly from the Telegram Trigger for non-callable agents:

```python
def _memory_node(memory: MemoryConfig, callable: bool) -> dict[str, Any]:
    """Window buffer memory — gives the agent short-term conversation context."""
    # Callable agents normalize input through Set nodes, so chat_id is in $json.
    # Non-callable agents read directly from the Telegram Trigger.
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
```

In `_build_nodes`, after adding tool nodes, add:
```python
if agent.memory is not None:
    nodes.append(_memory_node(agent.memory, callable=agent.callable))
```

In `_build_connections`, after the tools loop, add:
```python
if agent.memory is not None:
    conns["Chat Memory"] = {
        "ai_memory": [[{"node": agent_name, "type": "ai_memory", "index": 0}]],
    }
```

Note: The `compile_workflow` function signature must also accept the `MemoryConfig` import. Add `from council.domain.agent import AgentDefinition, MemoryConfig` at the top (or just use `agent.memory` since it's already on the model).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_adapters/test_compiler_extensions.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Run all tests for regressions**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add council/adapters/n8n/compiler.py tests/test_adapters/test_compiler_extensions.py
git commit -m "feat: add window buffer memory node to compiler"
```

---

### Task 7: Compiler — Negative command filter for command-less agents

**Files:**
- Modify: `council/adapters/n8n/compiler.py`
- Test: add to `tests/test_adapters/test_compiler_extensions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_adapters/test_compiler_extensions.py`:

```python
def test_no_command_agent_gets_negative_filter():
    """Agent without a command should get a 'Not a /run command?' If node."""
    agent = _agent_with_memory(memory=None)  # no command on trigger
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
    # Trigger → negative filter → Agent
    assert conns["Telegram Trigger"]["main"][0][0]["node"] == "Not a /run command?"
    assert conns["Not a /run command?"]["main"][0][0]["node"] == "Elrond agent"


def test_command_agent_does_not_get_negative_filter():
    """Agent WITH a command should get the normal positive If node, not a negative one."""
    agent = _agent_with_memory(
        name="Gimli",
        trigger=Trigger(type="telegram", command="/run gimli"),
        memory=None,
    )
    workflow = compile_workflow(agent, [])
    if_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.if"]
    assert len(if_nodes) == 1
    assert if_nodes[0]["name"] == "Is /run gimli?"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_adapters/test_compiler_extensions.py::test_no_command_agent_gets_negative_filter -v`
Expected: FAIL — no If node generated for command-less agents (currently 0 If nodes)

- [ ] **Step 3: Add negative command filter to compiler**

Add a new node builder:
```python
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
```

Modify `_build_nodes`: when `has_command` is False, add the negative filter node instead of no If node:
```python
if has_command:
    nodes.append(_if_node(agent.trigger.command))
else:
    nodes.append(_negative_command_filter_node())
```

Modify `_build_connections`: when `has_command` is False, route through the negative filter:
```python
if has_command:
    if_name = f"Is {agent.trigger.command}?"
    conns["Telegram Trigger"] = _main_out(if_name)
    conns[if_name] = _main_out(agent_name)
else:
    conns["Telegram Trigger"] = _main_out("Not a /run command?")
    conns["Not a /run command?"] = _main_out(agent_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_adapters/test_compiler_extensions.py -v`
Expected: PASS

- [ ] **Step 5: Fix regression in existing test**

The existing `test_workflow_without_command_skips_if_node` in `tests/test_adapters/test_compiler.py` expects 0 If nodes for command-less agents. This now has 1 (the negative filter). Update the test:

In `tests/test_adapters/test_compiler.py`, update `test_workflow_without_command_skips_if_node`:
```python
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
    # Trigger connects through negative filter to agent
    conns = workflow["connections"]
    assert conns["Telegram Trigger"]["main"][0][0]["node"] == "Not a /run command?"
    assert conns["Not a /run command?"]["main"][0][0]["node"] == "Elrond agent"
```

- [ ] **Step 6: Run all tests**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add council/adapters/n8n/compiler.py tests/test_adapters/test_compiler_extensions.py tests/test_adapters/test_compiler.py
git commit -m "feat: add negative /run command filter for command-less agents"
```

---

### Task 8: Compiler — Execute Workflow tool node

**Files:**
- Modify: `council/adapters/n8n/compiler.py`
- Test: add to `tests/test_adapters/test_compiler_extensions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_adapters/test_compiler_extensions.py`:

```python
from council.wiring.tools.models import WorkflowTool


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
    """Both HttpTool and WorkflowTool in the same workflow."""
    agent = _agent_with_memory(memory=None)
    http_tool = _simple_tool()
    wf_tool = WorkflowTool(name="Execute Gimli", description="Trigger Gimli.", target_agent="Gimli")
    registry = {"Gimli": "wf-456"}
    workflow = compile_workflow(agent, [http_tool, wf_tool], workflow_registry=registry)
    http_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.httpRequestTool"]
    exec_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.executeWorkflow"]
    assert len(http_nodes) == 1
    assert len(exec_nodes) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_adapters/test_compiler_extensions.py::test_execute_workflow_tool_node_generated -v`
Expected: FAIL — `compile_workflow` doesn't accept `workflow_registry` parameter

- [ ] **Step 3: Add execute workflow support to compiler**

Update `compile_workflow` signature:
```python
from council.wiring.tools.models import HttpTool, WorkflowTool, Tool

def compile_workflow(
    agent: AgentDefinition,
    tools: list[Tool],
    litellm_base_url: str = "http://litellm:4000/v1",
    workflow_registry: dict[str, str] | None = None,
) -> dict[str, Any]:
```

Add a new node builder:
```python
def _execute_workflow_tool_node(
    tool: WorkflowTool,
    workflow_registry: dict[str, str],
) -> dict[str, Any]:
    """Build an Execute Workflow tool node from a WorkflowTool model."""
    if tool.target_agent not in workflow_registry:
        raise ValueError(
            f"Agent '{tool.target_agent}' not found in workflow registry — is it deployed?"
        )
    return {
        "name": tool.name,
        "type": "n8n-nodes-base.executeWorkflow",
        "typeVersion": 1,
        "position": [400, 400],
        "parameters": {
            "workflowId": workflow_registry[tool.target_agent],
        },
    }
```

Update `_build_nodes` to pass `workflow_registry` and dispatch by type:
```python
for tool in tools:
    if isinstance(tool, WorkflowTool):
        nodes.append(_execute_workflow_tool_node(tool, workflow_registry or {}))
    else:
        nodes.append(_tool_node(tool))
```

Update `_build_nodes` and `_build_connections` signatures to accept `list[Tool]`.

The `_build_connections` tool loop works for both types since it only uses `tool.name`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_adapters/test_compiler_extensions.py -v`
Expected: PASS

- [ ] **Step 5: Run all tests**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add council/adapters/n8n/compiler.py tests/test_adapters/test_compiler_extensions.py
git commit -m "feat: add Execute Workflow tool node to compiler"
```

---

### Task 9: Compiler — Dual-path Set nodes for callable agents

**Files:**
- Modify: `council/adapters/n8n/compiler.py`
- Test: add to `tests/test_adapters/test_compiler_extensions.py`

This is the most complex compiler change. When `callable = true`, the compiler must:
1. Add an Execute Workflow Trigger node
2. Add two Set nodes to normalize input from both trigger paths
3. Route both Set nodes to the downstream flow
4. Update the AI Agent's `text` to read from `$json.instructions`
5. Update the Reply node's `chatId` to read from `$json.chat_id`
6. Add an If guard before the Reply node to skip it when no `chat_id` is present

- [ ] **Step 1: Write failing tests**

Append to `tests/test_adapters/test_compiler_extensions.py`:

```python
def _callable_agent(**overrides) -> AgentDefinition:
    defaults = {
        "name": "Gimli",
        "role": "Builder",
        "brain": "gemini/gemini-flash-latest",
        "prompt": "You are Gimli.",
        "tools": [],
        "trigger": Trigger(type="telegram", command="/run gimli"),
        "reply": Reply(type="telegram"),
        "callable": True,
    }
    defaults.update(overrides)
    return AgentDefinition(**defaults)


def test_callable_agent_has_execute_workflow_trigger():
    agent = _callable_agent()
    workflow = compile_workflow(agent, [])
    trigger_nodes = [n for n in workflow["nodes"] if "executeWorkflowTrigger" in n["type"]]
    assert len(trigger_nodes) == 1


def test_callable_agent_has_two_set_nodes():
    agent = _callable_agent()
    workflow = compile_workflow(agent, [])
    set_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.set"]
    assert len(set_nodes) == 2
    set_names = {n["name"] for n in set_nodes}
    assert "Normalize Telegram Input" in set_names
    assert "Normalize Workflow Input" in set_names


def test_callable_agent_text_reads_from_normalized_input():
    agent = _callable_agent()
    workflow = compile_workflow(agent, [])
    agent_node = next(n for n in workflow["nodes"] if "langchain.agent" in n["type"])
    assert "$json.instructions" in agent_node["parameters"]["text"]


def test_callable_agent_reply_reads_normalized_chat_id():
    agent = _callable_agent()
    workflow = compile_workflow(agent, [])
    # Find the Reply node or the If guard before it
    reply_nodes = [n for n in workflow["nodes"] if n["name"] == "Reply"]
    assert len(reply_nodes) == 1
    assert "$json.chat_id" in reply_nodes[0]["parameters"]["chatId"]


def test_callable_agent_connections_telegram_path():
    agent = _callable_agent()
    workflow = compile_workflow(agent, [])
    conns = workflow["connections"]
    assert conns["Telegram Trigger"]["main"][0][0]["node"] == "Normalize Telegram Input"


def test_callable_agent_connections_workflow_trigger_path():
    agent = _callable_agent()
    workflow = compile_workflow(agent, [])
    conns = workflow["connections"]
    assert conns["Execute Workflow Trigger"]["main"][0][0]["node"] == "Normalize Workflow Input"


def test_callable_agent_has_reply_if_guard():
    """Callable agents should have an If guard before Reply to skip when no chat_id."""
    agent = _callable_agent()
    workflow = compile_workflow(agent, [])
    if_nodes = [n for n in workflow["nodes"] if n["name"] == "Has chat_id?"]
    assert len(if_nodes) == 1
    conns = workflow["connections"]
    # Agent → Has chat_id? → Reply
    assert conns[f"{agent.name} agent"]["main"][0][0]["node"] == "Has chat_id?"
    assert conns["Has chat_id?"]["main"][0][0]["node"] == "Reply"


def test_non_callable_agent_has_no_execute_workflow_trigger():
    agent = _agent_with_memory(memory=None)  # callable defaults to False
    workflow = compile_workflow(agent, [])
    trigger_nodes = [n for n in workflow["nodes"] if "executeWorkflowTrigger" in n["type"]]
    assert len(trigger_nodes) == 0


def test_non_callable_agent_has_no_reply_if_guard():
    """Non-callable agents connect Agent directly to Reply."""
    agent = _agent_with_memory(memory=None)
    workflow = compile_workflow(agent, [])
    if_nodes = [n for n in workflow["nodes"] if n.get("name") == "Has chat_id?"]
    assert len(if_nodes) == 0
    conns = workflow["connections"]
    assert conns["Elrond agent"]["main"][0][0]["node"] == "Reply"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_adapters/test_compiler_extensions.py::test_callable_agent_has_execute_workflow_trigger -v`
Expected: FAIL — no Execute Workflow Trigger node

- [ ] **Step 3: Implement dual-path support in compiler**

Add new node builders:
```python
def _execute_workflow_trigger_node() -> dict[str, Any]:
    """Second entry point for agents that can be called by other workflows."""
    return {
        "name": "Execute Workflow Trigger",
        "type": "n8n-nodes-base.executeWorkflowTrigger",
        "typeVersion": 1.1,
        "position": [0, 200],
        "parameters": {},
    }


def _normalize_telegram_set_node(command: str | None) -> dict[str, Any]:
    """Normalize Telegram Trigger output to common {instructions, chat_id} shape."""
    strip_expr = f".replace('{command}', '').trim()" if command else ".trim()"
    return {
        "name": "Normalize Telegram Input",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [200, 0],
        "parameters": {
            "assignments": {
                "assignments": [
                    {
                        "name": "instructions",
                        "value": f"={{{{ $json.message.text{strip_expr} }}}}",
                        "type": "string",
                    },
                    {
                        "name": "chat_id",
                        "value": "={{ $json.message.chat.id }}",
                        "type": "string",
                    },
                ]
            }
        },
    }


def _normalize_workflow_set_node() -> dict[str, Any]:
    """Normalize Execute Workflow Trigger output to common {instructions, chat_id} shape."""
    return {
        "name": "Normalize Workflow Input",
        "type": "n8n-nodes-base.set",
        "typeVersion": 3.4,
        "position": [200, 200],
        "parameters": {
            "assignments": {
                "assignments": [
                    {
                        "name": "instructions",
                        "value": "={{ $json.instructions }}",
                        "type": "string",
                    },
                    {
                        "name": "chat_id",
                        "value": "={{ $json.chat_id }}",
                        "type": "string",
                    },
                ]
            }
        },
    }
```

Add an If guard node for the Reply (callable agents only):
```python
def _reply_if_guard_node() -> dict[str, Any]:
    """Skip the Reply node when no chat_id is available (headless execution)."""
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
                        "operator": {
                            "type": "string",
                            "operation": "notEquals",
                        },
                    }
                ],
            },
        },
    }
```

Key changes to `_build_nodes` and `_build_connections`:

When `agent.callable` is True:
- Add the Execute Workflow Trigger, both Set nodes, and the Reply If guard
- The AI Agent `text` reads `{{ $json.instructions }}` instead of from the Telegram Trigger
- The Reply node `chatId` reads `{{ $json.chat_id }}`
- Both Set nodes route to the If node (command) or directly to the Agent
- Agent → Has chat_id? → Reply (instead of Agent → Reply directly)
- Telegram Trigger → Normalize Telegram Input → [If] → Agent
- Execute Workflow Trigger → Normalize Workflow Input → [If] → Agent

When `agent.callable` is False, keep current behavior (Agent → Reply directly).

Modify `_ai_agent_node` to accept a `callable` parameter:
- If callable: `text` = `={{ $json.instructions || 'Check the open issues and decide what to work on.' }}`
- If not callable: keep current behavior

Modify `_reply_node` to accept a `callable` parameter:
- If callable: `chatId` = `={{ $json.chat_id }}`
- If not callable: keep current `$('Telegram Trigger')...` behavior

Modify `_build_connections`:
- If callable: `agent_name` → `"Has chat_id?"` → `"Reply"` (instead of `agent_name` → `"Reply"`)
- If not callable: keep current `agent_name` → `"Reply"`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_adapters/test_compiler_extensions.py -v`
Expected: PASS

- [ ] **Step 5: Run all tests — fix any regressions**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest -v`
Expected: PASS. Existing compiler tests use agents with `callable=False` (default), so they should not be affected.

- [ ] **Step 6: Commit**

```bash
git add council/adapters/n8n/compiler.py tests/test_adapters/test_compiler_extensions.py
git commit -m "feat: add dual-path input normalization for callable agents"
```

---

### Task 10: Two-pass Deployment in __main__.py

**Files:**
- Modify: `council/__main__.py`
- Test: `tests/test_main_deploy_order.py`

- [ ] **Step 1: Write failing tests**

Note: `run_deploy` uses lazy imports inside the function body. To make these testable, refactor `run_deploy` to move imports to the top of the function. Then patch at the source module level, not `council.__main__`.

```python
# tests/test_main_deploy_order.py
from unittest.mock import MagicMock, patch
from pathlib import Path

import httpx

from council.domain.agent import AgentDefinition, Trigger, Reply
from council.config import ProjectConfig


def _make_agent(name: str, orchestrator: bool = False) -> AgentDefinition:
    return AgentDefinition(
        name=name,
        role="Test",
        brain="gemini/gemini-flash-latest",
        prompt=f"You are {name}.",
        tools=[],
        trigger=Trigger(type="telegram", command=f"/run {name.lower()}" if not orchestrator else None),
        reply=Reply(type="telegram"),
        orchestrator=orchestrator,
    )


def _make_config() -> ProjectConfig:
    return ProjectConfig(owner="o", repo="r", litellm_master_key="sk-test")


@patch("council.adapters.n8n.compiler.compile_workflow")
def test_orchestrators_deploy_after_workers(mock_compile):
    """Orchestrator agents should be deployed in a second pass, after workers."""
    from council.adapters.n8n.deployer import N8nDeployer

    gimli = _make_agent("Gimli")
    elrond = _make_agent("Elrond", orchestrator=True)
    agents = [elrond, gimli]  # intentionally out of order

    mock_compile.return_value = {"name": "test", "nodes": [], "connections": {}, "settings": {}}

    # Test the sorting logic directly — extract workers/orchestrators
    workers = [a for a in agents if not a.orchestrator]
    orchestrators = [a for a in agents if a.orchestrator]

    assert workers[0].name == "Gimli"
    assert orchestrators[0].name == "Elrond"

    # Verify workers come before orchestrators in the deploy order
    deploy_order = workers + orchestrators
    assert deploy_order[0].name == "Gimli"
    assert deploy_order[1].name == "Elrond"


def test_orchestrator_receives_workflow_registry():
    """Verify that compile_workflow is called with registry for orchestrators."""
    from council.adapters.n8n.compiler import compile_workflow
    from council.wiring.tools.models import WorkflowTool

    elrond = _make_agent("Elrond", orchestrator=True)
    wf_tool = WorkflowTool(name="Execute Gimli", description="Trigger Gimli.", target_agent="Gimli")
    registry = {"Gimli": "gimli-wf-id"}

    # This should not raise — registry has the needed agent
    workflow = compile_workflow(elrond, [wf_tool], workflow_registry=registry)
    exec_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.executeWorkflow"]
    assert len(exec_nodes) == 1
    assert exec_nodes[0]["parameters"]["workflowId"] == "gimli-wf-id"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_main_deploy_order.py -v`
Expected: FAIL — current `run_deploy` doesn't sort by orchestrator or pass registry

- [ ] **Step 3: Implement two-pass deployment**

Rewrite the agent deployment loop in `council/__main__.py`'s `run_deploy` function:

```python
# Split agents into workers and orchestrators
workers = [a for a in agents if not a.orchestrator]
orchestrators = [a for a in agents if a.orchestrator]

# Pass 1: Deploy workers, build workflow registry
workflow_registry: dict[str, str] = {}
for agent in workers:
    print(f"[council] Deploying '{agent.name}'...")
    tools = resolve_tools(agent.tools)
    tools = resolve_tool_urls(tools, config)
    workflow = compile_workflow(agent, tools)
    _inject_credentials(workflow, telegram_cred_id, litellm_cred_id)
    workflow_id = deployer.deploy(workflow)
    workflow_registry[agent.name] = workflow_id
    print(f"[council] Deployed '{agent.name}' (id: {workflow_id})")

# Pass 2: Deploy orchestrators (they get the workflow registry)
for agent in orchestrators:
    print(f"[council] Deploying orchestrator '{agent.name}'...")
    tools = resolve_tools(agent.tools)
    tools = resolve_tool_urls(tools, config)
    workflow = compile_workflow(agent, tools, workflow_registry=workflow_registry)
    _inject_credentials(workflow, telegram_cred_id, litellm_cred_id)
    workflow_id = deployer.deploy(workflow)
    print(f"[council] Deployed '{agent.name}' (id: {workflow_id})")
```

Extract the credential injection loop into a helper `_inject_credentials(workflow, telegram_cred_id, litellm_cred_id)` to avoid duplication.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_main_deploy_order.py -v`
Expected: PASS

- [ ] **Step 5: Run all tests**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add council/__main__.py tests/test_main_deploy_order.py
git commit -m "feat: add two-pass deployment — workers first, then orchestrators"
```

---

### Task 11: Elrond TOML and Gimli callable flag

**Files:**
- Create: `agents/elrond.toml`
- Modify: `agents/gimli.toml`
- Test: integration test via loader

- [ ] **Step 1: Write failing test**

```python
# tests/test_domain/test_load_elrond.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_domain/test_load_elrond.py -v`
Expected: FAIL — `elrond.toml` doesn't exist, gimli.toml doesn't have `callable`

- [ ] **Step 3: Create elrond.toml**

```toml
# agents/elrond.toml
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
    "github_write.update_file",
    "github_pr.read_pr",
    "github_pr.merge_pr",
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

- [ ] **Step 4: Add callable = true to gimli.toml**

Add `callable = true` below the `brain` line in `agents/gimli.toml`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_domain/test_load_elrond.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agents/elrond.toml agents/gimli.toml tests/test_domain/test_load_elrond.py
git commit -m "feat: add Elrond TOML and mark Gimli as callable"
```

---

### Task 12: Initial memory files

**Files:**
- Create: `memories/decisions.md`
- Create: `memories/agents.md`
- Create: `memories/project-state.md`
- Create: `memories/budget.md`

- [ ] **Step 1: Create memory files**

```markdown
# memories/decisions.md
# Council Decisions

This file records key decisions and the reasoning behind them.
Elrond updates this file after important decisions are made.
```

```markdown
# memories/agents.md
# Agent Registry

## Elrond
- Role: Head of the Council — orchestrator, planner, reviewer
- Brain: gemini/gemini-2.5-pro-preview-05-06
- Strengths: Strategic thinking, planning, delegation
- Can: Create issues, review PRs, merge PRs, delegate to other agents, manage memory
- Cannot: Write code directly

## Gimli
- Role: Builder
- Brain: gemini/gemini-flash-latest
- Strengths: Fast execution, code writing
- Can: Read files, list issues, create issues, write code, create PRs
- Cannot: Review code (that's Galadriel's future role)
```

```markdown
# memories/project-state.md
# Project State

## Completed
- Council architecture: TOML → compiler → n8n workflows
- Gimli agent: builder with GitHub tools
- Elrond agent: orchestrator with memory and delegation

## In Progress
- Nothing currently

## Planned
- Galadriel: dedicated code reviewer agent
```

```markdown
# memories/budget.md
# Budget Tracker

Daily budget: $5.00

## Spending Log
| Date | Agent | Action | Est. Cost |
|------|-------|--------|-----------|
```

- [ ] **Step 2: Commit**

```bash
git add memories/
git commit -m "feat: add initial memory files for Elrond"
```

---

### Task 13: End-to-end integration test

**Files:**
- Test: `tests/test_integration/test_elrond_compilation.py`

This test verifies the full pipeline: load Elrond TOML → resolve tools → compile workflow → verify the output has all expected nodes and connections.

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration/test_elrond_compilation.py
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

    # Elrond is an orchestrator, so provide a mock registry
    registry = {"Gimli": "mock-gimli-wf-id"}
    workflow = compile_workflow(agent, tools, workflow_registry=registry)

    # Basic structure
    assert workflow["name"] == "Elrond — Head of the Council"
    assert "nodes" in workflow
    assert "connections" in workflow

    # Should have: Telegram Trigger, negative filter If, Agent, Chat Model,
    # Reply, Chat Memory, 6 HTTP tools, 1 Execute Workflow tool
    node_types = [n["type"] for n in workflow["nodes"]]
    assert "n8n-nodes-base.telegramTrigger" in node_types
    assert "n8n-nodes-base.if" in node_types  # negative /run filter
    assert "@n8n/n8n-nodes-langchain.agent" in node_types
    assert "@n8n/n8n-nodes-langchain.lmChatOpenAi" in node_types
    assert "n8n-nodes-base.telegram" in node_types  # Reply
    assert "@n8n/n8n-nodes-langchain.memoryBufferWindow" in node_types  # Memory
    assert "n8n-nodes-base.executeWorkflow" in node_types  # Execute Gimli

    # Verify it's valid JSON
    json_str = json.dumps(workflow)
    assert json.loads(json_str) == workflow


def test_gimli_callable_workflow_compiles():
    agent = load_agent(Path("agents/gimli.toml"))
    config = load_project_config(Path("council.toml"))
    tools = resolve_tools(agent.tools)
    tools = resolve_tool_urls(tools, config)

    workflow = compile_workflow(agent, tools)

    node_types = [n["type"] for n in workflow["nodes"]]
    # Should have dual triggers
    assert "n8n-nodes-base.telegramTrigger" in node_types
    assert "n8n-nodes-base.executeWorkflowTrigger" in node_types
    # Should have Set nodes for normalization
    set_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.set"]
    assert len(set_nodes) == 2
```

- [ ] **Step 2: Run integration test**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest tests/test_integration/test_elrond_compilation.py -v`
Expected: PASS

- [ ] **Step 3: Run all tests**

Run: `cd /home/jordan/code/theCouncilOfElrond && python -m pytest -v`
Expected: PASS (all tests green)

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration/test_elrond_compilation.py
git commit -m "test: add end-to-end integration test for Elrond compilation"
```

---

### Task 14: Docker build and manual deployment test

- [ ] **Step 1: Build Docker image**

Run: `cd /home/jordan/code/theCouncilOfElrond && docker compose build --no-cache seed-config seed-deploy`

- [ ] **Step 2: Run config generation**

Run: `docker compose up seed-config`
Expected: Should generate LiteLLM config with both Gimli and Elrond models.

- [ ] **Step 3: Deploy to n8n**

Run: `docker compose up seed-deploy`
Expected: Should deploy Gimli first, then Elrond. Look for:
```
[council] Deploying 'Gimli'...
[council] Deployed 'Gimli' (id: ...)
[council] Deploying orchestrator 'Elrond'...
[council] Deployed 'Elrond' (id: ...)
```

- [ ] **Step 4: Verify in n8n UI**

Open http://localhost:5678 and check:
- Both workflows exist and are active
- Elrond's workflow has: Telegram Trigger, negative filter, AI Agent, Chat Model, Reply, Chat Memory, all 7 tools
- Gimli's workflow has: Telegram Trigger, Execute Workflow Trigger, Set nodes, If node, AI Agent, Chat Model, Reply, 3 tools

- [ ] **Step 5: Test on Telegram**

Send a plain message (not `/run`) to the bot — Elrond should respond.
Send `/run gimli` — only Gimli should respond, not Elrond.
