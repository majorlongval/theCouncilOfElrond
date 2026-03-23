# Council Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python pipeline that compiles TOML agent definitions into n8n workflows via LiteLLM, proving the architecture end-to-end with the Gimli agent.

**Architecture:** Four-layer design (domain, casting, wiring, adapter). TOML files define agents. Python compiles them to n8n workflow JSON and deploys via REST API. LiteLLM proxies all LLM calls for provider agnosticism.

**Tech Stack:** Python 3.12, Pydantic, tomllib, pytest, Docker, n8n REST API, LiteLLM

**Spec:** `docs/superpowers/specs/2026-03-22-council-architecture-design.md`

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `council/__init__.py`
- Create: `council/domain/__init__.py`
- Create: `council/casting/__init__.py`
- Create: `council/wiring/__init__.py`
- Create: `council/wiring/tools/__init__.py`
- Create: `council/adapters/__init__.py`
- Create: `council/adapters/n8n/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_domain/__init__.py`
- Create: `tests/test_casting/__init__.py`
- Create: `tests/test_wiring/__init__.py`
- Create: `tests/test_adapters/__init__.py`
- Create: `council.toml`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "council"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "httpx>=0.27",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: Create council.toml (project config)**

```toml
[project]
owner = "majorlongval"
repo = "theCouncilOfElrond"

[litellm]
master_key = "sk-council-local"
```

- [ ] **Step 3: Create all __init__.py files**

Create empty `__init__.py` in all directories listed above.

- [ ] **Step 4: Create virtualenv and install**

Run: `python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: Installs successfully

- [ ] **Step 5: Verify pytest runs**

Run: `source .venv/bin/activate && pytest --co -q`
Expected: "no tests ran" (no errors)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml council.toml council/ tests/
git commit -m "feat: scaffold council package with project config"
```

---

### Task 2: Domain models (AgentDefinition, Trigger, Reply)

**Files:**
- Create: `council/domain/agent.py`
- Create: `tests/test_domain/test_agent.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_domain/test_agent.py
import pytest
from council.domain.agent import AgentDefinition, Trigger, Reply


def test_valid_agent_definition():
    agent = AgentDefinition(
        name="Gimli",
        role="Builder",
        brain="gemini/gemini-flash-latest",
        prompt="You are Gimli.",
        tools=["github.list_issues", "github.read_file"],
        artifacts=["github.pull_request"],
        trigger=Trigger(type="telegram", command="/run gimli"),
        reply=Reply(type="telegram"),
    )
    assert agent.name == "Gimli"
    assert agent.brain == "gemini/gemini-flash-latest"
    assert len(agent.tools) == 2


def test_trigger_type_must_be_valid():
    with pytest.raises(ValueError):
        Trigger(type="invalid")


def test_reply_type_must_be_valid():
    with pytest.raises(ValueError):
        Reply(type="invalid")


def test_trigger_telegram_allows_command():
    trigger = Trigger(type="telegram", command="/run gimli")
    assert trigger.command == "/run gimli"


def test_trigger_webhook_allows_path():
    trigger = Trigger(type="webhook", path="my-webhook")
    assert trigger.path == "my-webhook"


def test_trigger_cron_allows_schedule():
    trigger = Trigger(type="cron", schedule="0 * * * *")
    assert trigger.schedule == "0 * * * *"


def test_agent_requires_all_fields():
    with pytest.raises(ValueError):
        AgentDefinition(
            name="Gimli",
            role="Builder",
            # missing brain, prompt, tools, artifacts, trigger, reply
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_domain/test_agent.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

- [ ] **Step 3: Implement domain models**

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


class AgentDefinition(BaseModel):
    """Complete definition of an agent — the single source of truth."""
    name: str
    role: str
    brain: str
    prompt: str
    tools: list[str]
    artifacts: list[str]
    trigger: Trigger
    reply: Reply
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_domain/test_agent.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add council/domain/agent.py tests/test_domain/test_agent.py
git commit -m "feat: add AgentDefinition domain models with validation"
```

---

### Task 3: Domain loader (TOML → AgentDefinition)

**Files:**
- Create: `council/domain/loader.py`
- Create: `tests/test_domain/test_loader.py`
- Create: `tests/fixtures/agents/valid_agent.toml`
- Create: `tests/fixtures/agents/invalid_agent.toml`

- [ ] **Step 1: Create test fixtures**

```toml
# tests/fixtures/agents/valid_agent.toml
name = "Gimli"
role = "Builder"
brain = "gemini/gemini-flash-latest"

prompt = """
You are Gimli, a builder agent.
"""

tools = [
    "github.list_issues",
    "github.read_file",
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

```toml
# tests/fixtures/agents/invalid_agent.toml
name = "Broken"
role = "Nothing"
# missing required fields
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_domain/test_loader.py
from pathlib import Path

import pytest

from council.domain.agent import AgentDefinition
from council.domain.loader import load_agent, load_all_agents


FIXTURES = Path(__file__).parent.parent / "fixtures" / "agents"


def test_load_agent_from_toml():
    agent = load_agent(FIXTURES / "valid_agent.toml")
    assert isinstance(agent, AgentDefinition)
    assert agent.name == "Gimli"
    assert agent.role == "Builder"
    assert agent.brain == "gemini/gemini-flash-latest"
    assert agent.trigger.type == "telegram"
    assert agent.trigger.command == "/run gimli"
    assert agent.reply.type == "telegram"
    assert "github.list_issues" in agent.tools


def test_load_agent_invalid_toml_raises():
    with pytest.raises(ValueError):
        load_agent(FIXTURES / "invalid_agent.toml")


def test_load_all_agents_from_directory():
    agents = load_all_agents(FIXTURES)
    assert len(agents) == 1  # only valid_agent.toml is valid
    assert agents[0].name == "Gimli"


def test_load_agent_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_agent(Path("/nonexistent/agent.toml"))
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_domain/test_loader.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 4: Implement loader**

```python
# council/domain/loader.py
import tomllib
from pathlib import Path

from council.domain.agent import AgentDefinition


def load_agent(path: Path) -> AgentDefinition:
    """Load and validate a single agent definition from a TOML file."""
    if not path.exists():
        raise FileNotFoundError(f"Agent file not found: {path}")

    with open(path, "rb") as f:
        data = tomllib.load(f)

    try:
        return AgentDefinition(**data)
    except Exception as e:
        raise ValueError(f"Invalid agent definition in {path}: {e}") from e


def load_all_agents(directory: Path) -> list[AgentDefinition]:
    """Load all valid agent definitions from a directory of TOML files."""
    agents: list[AgentDefinition] = []
    for path in sorted(directory.glob("*.toml")):
        try:
            agents.append(load_agent(path))
        except ValueError:
            continue
    return agents
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_domain/test_loader.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add council/domain/loader.py tests/test_domain/test_loader.py tests/fixtures/
git commit -m "feat: add TOML agent loader with validation"
```

---

### Task 4: Wiring — tool models

**Files:**
- Create: `council/wiring/tools/models.py`
- Create: `tests/test_wiring/test_tool_models.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_wiring/test_tool_models.py
import pytest
from council.wiring.tools.models import HttpTool, Param, BearerToken, JsonBody


def test_http_tool_minimal():
    tool = HttpTool(
        name="List Issues",
        description="List open issues.",
        url="https://api.github.com/repos/{owner}/{repo}/issues",
    )
    assert tool.method == "GET"
    assert tool.params == {}
    assert tool.auth is None
    assert tool.headers == {}
    assert tool.body is None


def test_http_tool_with_params():
    tool = HttpTool(
        name="Read File",
        description="Read a file.",
        url="https://api.github.com/repos/{owner}/{repo}/contents/{filepath}",
        params={"filepath": Param(description="Path to file")},
        auth=BearerToken(env="GITHUB_TOKEN"),
        headers={"Accept": "application/vnd.github.raw+json"},
    )
    assert "filepath" in tool.params
    assert tool.auth.env == "GITHUB_TOKEN"
    assert tool.headers["Accept"] == "application/vnd.github.raw+json"


def test_http_tool_with_json_body():
    tool = HttpTool(
        name="Create Issue",
        description="Create an issue.",
        url="https://api.github.com/repos/{owner}/{repo}/issues",
        method="POST",
        body=JsonBody(schema={"title": "string", "body": "string"}),
        auth=BearerToken(env="GITHUB_TOKEN"),
    )
    assert tool.method == "POST"
    assert tool.body.schema == {"title": "string", "body": "string"}


def test_http_tool_invalid_method():
    with pytest.raises(ValueError):
        HttpTool(
            name="Bad",
            description="Bad tool.",
            url="https://example.com",
            method="INVALID",
        )


def test_param_defaults_to_string_type():
    param = Param(description="A parameter")
    assert param.type == "string"


def test_url_placeholder_extraction():
    tool = HttpTool(
        name="Test",
        description="Test tool.",
        url="https://api.github.com/repos/{owner}/{repo}/contents/{filepath}",
        params={"filepath": Param(description="file path")},
    )
    # AI params are in tool.params, project params are the rest
    ai_placeholders = set(tool.params.keys())
    assert ai_placeholders == {"filepath"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_wiring/test_tool_models.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Implement tool models**

```python
# council/wiring/tools/models.py
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Param(BaseModel):
    """A parameter the AI agent must provide when calling a tool."""
    description: str
    type: str = "string"


class BearerToken(BaseModel):
    """Auth via Bearer token from an environment variable."""
    env: str


class JsonBody(BaseModel):
    """Structured JSON body the AI agent must provide."""
    model_config = ConfigDict(protected_namespaces=())
    schema: dict[str, str]


class HttpTool(BaseModel):
    """A tool that an AI agent can invoke. Compiled to an n8n httpRequestTool node."""
    name: str
    description: str
    url: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    params: dict[str, Param] = {}
    auth: BearerToken | None = None
    headers: dict[str, str] = {}
    body: JsonBody | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_wiring/test_tool_models.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add council/wiring/tools/models.py tests/test_wiring/test_tool_models.py
git commit -m "feat: add HttpTool and related wiring models"
```

---

### Task 5: Wiring — GitHub tool catalog and registry

**Files:**
- Create: `council/wiring/tools/github.py`
- Modify: `council/wiring/tools/__init__.py`
- Create: `tests/test_wiring/test_tool_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_wiring/test_tool_registry.py
import pytest
from council.wiring.tools import resolve_tool
from council.wiring.tools.models import HttpTool


def test_resolve_github_list_issues():
    tool = resolve_tool("github.list_issues")
    assert isinstance(tool, HttpTool)
    assert tool.name == "List Issues"
    assert tool.method == "GET"
    assert "issues" in tool.url


def test_resolve_github_read_file():
    tool = resolve_tool("github.read_file")
    assert isinstance(tool, HttpTool)
    assert tool.name == "Read File"
    assert "filepath" in tool.params


def test_resolve_github_create_issue():
    tool = resolve_tool("github.create_issue")
    assert isinstance(tool, HttpTool)
    assert tool.name == "Create Issue"
    assert tool.method == "POST"
    assert tool.body is not None


def test_resolve_unknown_tool_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        resolve_tool("nonexistent.tool")


def test_resolve_unknown_module_raises():
    with pytest.raises(ValueError, match="Unknown tool"):
        resolve_tool("fakemoudle.read_file")


def test_resolve_tools_returns_list():
    from council.wiring.tools import resolve_tools
    tools = resolve_tools(["github.list_issues", "github.read_file"])
    assert len(tools) == 2
    assert all(isinstance(t, HttpTool) for t in tools)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_wiring/test_tool_registry.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Implement GitHub tools**

```python
# council/wiring/tools/github.py
from council.wiring.tools.models import BearerToken, HttpTool, JsonBody, Param


list_issues = HttpTool(
    name="List Issues",
    description="List open issues on the GitHub repository. Returns all open issues with their titles and details.",
    url="https://api.github.com/repos/{owner}/{repo}/issues?state=open",
    method="GET",
    auth=BearerToken(env="GITHUB_TOKEN"),
)

read_file = HttpTool(
    name="Read File",
    description=(
        "Read a single file from the GitHub repository. "
        "You MUST provide the file path. For example, to read README.md set filepath to 'README.md'. "
        "Only reads ONE file at a time. Do NOT use this to list directories."
    ),
    url="https://api.github.com/repos/{owner}/{repo}/contents/{filepath}",
    method="GET",
    params={"filepath": Param(description="The path to the file to read, e.g. README.md or docs/design.md")},
    auth=BearerToken(env="GITHUB_TOKEN"),
    headers={"Accept": "application/vnd.github.raw+json"},
)

create_issue = HttpTool(
    name="Create Issue",
    description=(
        'Create a new GitHub issue. You MUST provide a JSON body with "title" (required) '
        'and "body" (optional) fields.'
    ),
    url="https://api.github.com/repos/{owner}/{repo}/issues",
    method="POST",
    body=JsonBody(schema={"title": "string", "body": "string"}),
    auth=BearerToken(env="GITHUB_TOKEN"),
)
```

- [ ] **Step 4: Implement tool registry**

```python
# council/wiring/tools/__init__.py
import importlib

from council.wiring.tools.models import HttpTool


def resolve_tool(dotted_name: str) -> HttpTool:
    """Resolve a dotted tool reference like 'github.read_file' to an HttpTool."""
    parts = dotted_name.split(".")
    if len(parts) != 2:
        raise ValueError(f"Unknown tool: {dotted_name} (expected 'module.name' format)")

    module_name, attr_name = parts

    try:
        module = importlib.import_module(f"council.wiring.tools.{module_name}")
    except ModuleNotFoundError:
        raise ValueError(f"Unknown tool: {dotted_name} (module '{module_name}' not found)")

    tool = getattr(module, attr_name, None)
    if not isinstance(tool, HttpTool):
        raise ValueError(f"Unknown tool: {dotted_name} ('{attr_name}' not found in '{module_name}')")

    return tool


def resolve_tools(dotted_names: list[str]) -> list[HttpTool]:
    """Resolve a list of dotted tool references."""
    return [resolve_tool(name) for name in dotted_names]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_wiring/test_tool_registry.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add council/wiring/tools/ tests/test_wiring/test_tool_registry.py
git commit -m "feat: add GitHub tool catalog and dotted-name registry"
```

---

### Task 6: Casting — LiteLLM config generation

**Files:**
- Create: `council/casting/litellm.py`
- Create: `tests/test_casting/test_litellm.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_casting/test_litellm.py
import yaml

from council.domain.agent import AgentDefinition, Reply, Trigger
from council.casting.litellm import generate_litellm_config


def _make_agent(name: str, brain: str) -> AgentDefinition:
    return AgentDefinition(
        name=name,
        role="Test",
        brain=brain,
        prompt="Test prompt.",
        tools=["github.list_issues"],
        artifacts=[],
        trigger=Trigger(type="telegram", command=f"/run {name.lower()}"),
        reply=Reply(type="telegram"),
    )


def test_single_agent_config():
    agents = [_make_agent("Gimli", "gemini/gemini-flash-latest")]
    config = generate_litellm_config(agents, master_key="sk-test")
    parsed = yaml.safe_load(config)

    assert len(parsed["model_list"]) == 1
    entry = parsed["model_list"][0]
    assert entry["model_name"] == "gemini/gemini-flash-latest"
    assert entry["litellm_params"]["model"] == "gemini/gemini-flash-latest"


def test_deduplicates_brains():
    agents = [
        _make_agent("Gimli", "gemini/gemini-flash-latest"),
        _make_agent("Legolas", "gemini/gemini-flash-latest"),
    ]
    config = generate_litellm_config(agents, master_key="sk-test")
    parsed = yaml.safe_load(config)

    assert len(parsed["model_list"]) == 1


def test_multiple_providers():
    agents = [
        _make_agent("Gimli", "gemini/gemini-flash-latest"),
        _make_agent("Legolas", "anthropic/claude-sonnet"),
    ]
    config = generate_litellm_config(agents, master_key="sk-test")
    parsed = yaml.safe_load(config)

    assert len(parsed["model_list"]) == 2
    model_names = {e["model_name"] for e in parsed["model_list"]}
    assert model_names == {"gemini/gemini-flash-latest", "anthropic/claude-sonnet"}


def test_provider_to_env_var_mapping():
    agents = [_make_agent("Gimli", "gemini/gemini-flash-latest")]
    config = generate_litellm_config(agents, master_key="sk-test")
    parsed = yaml.safe_load(config)

    entry = parsed["model_list"][0]
    assert entry["litellm_params"]["api_key"] == "os.environ/GEMINI_API_KEY"


def test_anthropic_env_var():
    agents = [_make_agent("Legolas", "anthropic/claude-sonnet")]
    config = generate_litellm_config(agents, master_key="sk-test")
    parsed = yaml.safe_load(config)

    entry = parsed["model_list"][0]
    assert entry["litellm_params"]["api_key"] == "os.environ/ANTHROPIC_API_KEY"


def test_openai_env_var():
    agents = [_make_agent("Gandalf", "openai/gpt-4o")]
    config = generate_litellm_config(agents, master_key="sk-test")
    parsed = yaml.safe_load(config)

    entry = parsed["model_list"][0]
    assert entry["litellm_params"]["api_key"] == "os.environ/OPENAI_API_KEY"


def test_master_key_in_config():
    agents = [_make_agent("Gimli", "gemini/gemini-flash-latest")]
    config = generate_litellm_config(agents, master_key="sk-test")
    parsed = yaml.safe_load(config)

    assert parsed["general_settings"]["master_key"] == "sk-test"


def test_returns_valid_yaml_string():
    agents = [_make_agent("Gimli", "gemini/gemini-flash-latest")]
    config = generate_litellm_config(agents, master_key="sk-test")
    assert isinstance(config, str)
    # Should be parseable YAML
    parsed = yaml.safe_load(config)
    assert "model_list" in parsed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_casting/test_litellm.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Implement LiteLLM config generator**

```python
# council/casting/litellm.py
import yaml

from council.domain.agent import AgentDefinition


# Maps LiteLLM provider prefix to the env var name for API keys
PROVIDER_ENV_VARS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _provider_from_brain(brain: str) -> str:
    """Extract the provider name from a brain string like 'gemini/gemini-flash-latest'."""
    return brain.split("/")[0]


def _env_var_for_brain(brain: str) -> str:
    """Get the environment variable name for a brain's API key."""
    provider = _provider_from_brain(brain)
    env_var = PROVIDER_ENV_VARS.get(provider)
    if env_var is None:
        raise ValueError(f"Unknown provider '{provider}' in brain '{brain}'")
    return f"os.environ/{env_var}"


def generate_litellm_config(agents: list[AgentDefinition], master_key: str) -> str:
    """Generate a LiteLLM config YAML from agent definitions."""
    unique_brains = sorted(set(agent.brain for agent in agents))

    model_list = [
        {
            "model_name": brain,
            "litellm_params": {
                "model": brain,
                "api_key": _env_var_for_brain(brain),
            },
        }
        for brain in unique_brains
    ]

    config = {
        "model_list": model_list,
        "general_settings": {
            "master_key": master_key,
        },
    }

    return yaml.dump(config, default_flow_style=False, sort_keys=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_casting/test_litellm.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add council/casting/litellm.py tests/test_casting/test_litellm.py
git commit -m "feat: add LiteLLM config generation from agent brains"
```

---

### Task 7: n8n compiler — AgentDefinition → workflow JSON

This is the largest task. The compiler produces n8n workflow JSON matching the shape:
`Telegram Trigger → If (command filter) → AI Agent → Reply`
with `OpenAI Chat Model` and `httpRequestTool` nodes connected via `ai_languageModel` and `ai_tool`.

**Files:**
- Create: `council/adapters/n8n/compiler.py`
- Create: `tests/test_adapters/test_compiler.py`

**Reference:** The existing `workflows/gimli-v2.json` shows the exact n8n JSON structure for nodes, connections, and positions. The new compiler must produce equivalent structure but using the generic AI Agent + OpenAI Chat Model pattern instead of the native Gemini node.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_adapters/test_compiler.py
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


def test_workflow_without_command_skips_if_node(resolved_tools):
    """When trigger has no command, If node is omitted."""
    agent = AgentDefinition(
        name="Elrond",
        role="Director",
        brain="anthropic/claude-sonnet",
        prompt="You are Elrond.",
        tools=["github.list_issues"],
        artifacts=[],
        trigger=Trigger(type="telegram"),  # no command
        reply=Reply(type="telegram"),
    )
    workflow = compile_workflow(agent, resolved_tools)
    if_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.if"]
    assert len(if_nodes) == 0
    # Trigger connects directly to agent
    conns = workflow["connections"]
    assert conns["Telegram Trigger"]["main"][0][0]["node"] == "Elrond agent"


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
    # Model ID should match agent's brain
    assert model["parameters"]["model"]["value"] == "gemini/gemini-flash-latest"
    # Base URL should point to LiteLLM
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
    # Chat ID should reference trigger node
    assert "Telegram Trigger" in reply["parameters"]["chatId"]


def test_workflow_connections_main_flow(gimli_agent, resolved_tools):
    workflow = compile_workflow(gimli_agent, resolved_tools)
    conns = workflow["connections"]
    # Trigger → If
    assert conns["Telegram Trigger"]["main"][0][0]["node"] == "Is /run gimli?"
    # If → Agent
    assert conns["Is /run gimli?"]["main"][0][0]["node"] == "Gimli agent"
    # Agent → Reply
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
    # URL should contain $fromAI expression for filepath param
    assert "$fromAI" in read_file_node["parameters"]["url"]
    # URL should start with = for n8n expression evaluation
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
    # Should be serializable to JSON without errors
    json_str = json.dumps(workflow)
    reparsed = json.loads(json_str)
    assert reparsed["name"] == workflow["name"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_adapters/test_compiler.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Implement the compiler**

```python
# council/adapters/n8n/compiler.py
"""Compiles an AgentDefinition + resolved tools into n8n workflow JSON."""
import uuid

from council.domain.agent import AgentDefinition
from council.wiring.tools.models import HttpTool


def compile_workflow(
    agent: AgentDefinition,
    tools: list[HttpTool],
    litellm_base_url: str = "http://litellm:4000/v1",
) -> dict:
    """Compile an agent definition into n8n workflow JSON."""
    agent_node_name = f"{agent.name} agent"
    trigger_node_name = "Telegram Trigger"
    if_node_name = f"Is {agent.trigger.command}?"
    reply_node_name = "Reply"
    model_node_name = "Chat Model"

    nodes = [
        _build_trigger_node(agent, trigger_node_name),
    ]

    # Only add command filter if a command is specified
    has_command_filter = agent.trigger.command is not None
    if has_command_filter:
        nodes.append(_build_if_node(agent, if_node_name))

    nodes.extend([
        _build_agent_node(agent, agent_node_name),
        _build_chat_model_node(agent, model_node_name, litellm_base_url),
        _build_reply_node(agent, reply_node_name, trigger_node_name),
    ])

    tool_nodes = [_build_tool_node(tool, i) for i, tool in enumerate(tools)]
    nodes.extend(tool_nodes)

    connections = _build_connections(
        trigger_node_name=trigger_node_name,
        if_node_name=if_node_name if has_command_filter else None,
        agent_node_name=agent_node_name,
        reply_node_name=reply_node_name,
        model_node_name=model_node_name,
        tool_names=[t.name for t in tools],
    )

    return {
        "name": f"{agent.name} — {agent.role}",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1"},
    }


def _build_trigger_node(agent: AgentDefinition, name: str) -> dict:
    """Build a Telegram Trigger node."""
    return {
        "parameters": {"updates": ["message"], "additionalFields": {}},
        "type": "n8n-nodes-base.telegramTrigger",
        "typeVersion": 1.2,
        "position": [-640, -576],
        "id": str(uuid.uuid4()),
        "name": name,
        "webhookId": f"{agent.name.lower()}-trigger",
    }


def _build_if_node(agent: AgentDefinition, name: str) -> dict:
    """Build an If node that filters by the trigger command."""
    return {
        "parameters": {
            "conditions": {
                "options": {
                    "caseSensitive": False,
                    "leftValue": "",
                    "typeValidation": "strict",
                    "version": 3,
                },
                "conditions": [
                    {
                        "id": str(uuid.uuid4()),
                        "leftValue": "={{ $json.message.text }}",
                        "rightValue": agent.trigger.command,
                        "operator": {"type": "string", "operation": "startsWith"},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.3,
        "position": [-304, -576],
        "id": str(uuid.uuid4()),
        "name": name,
    }


def _build_agent_node(agent: AgentDefinition, name: str) -> dict:
    """Build an AI Agent node with the agent's system prompt."""
    command = agent.trigger.command or ""
    return {
        "parameters": {
            "promptType": "define",
            "text": (
                f"={{{{ $('Telegram Trigger').item.json.message.text"
                f".replace('{command}', '').trim() "
                f"|| 'Check the open issues and decide what to work on.' }}}}"
            ),
            "options": {
                "systemMessage": agent.prompt,
                "maxIterations": 10,
            },
        },
        "type": "@n8n/n8n-nodes-langchain.agent",
        "typeVersion": 3.1,
        "position": [48, -608],
        "id": str(uuid.uuid4()),
        "name": name,
    }


def _build_chat_model_node(
    agent: AgentDefinition, name: str, litellm_base_url: str
) -> dict:
    """Build an OpenAI Chat Model node pointed at LiteLLM."""
    return {
        "parameters": {
            "model": {
                "__rl": True,
                "value": agent.brain,
                "mode": "id",
            },
            "responsesApiEnabled": False,
            "options": {
                "baseURL": litellm_base_url,
            },
        },
        "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
        "typeVersion": 1.3,
        "position": [48, -400],
        "id": str(uuid.uuid4()),
        "name": name,
    }


def _build_reply_node(
    agent: AgentDefinition, name: str, trigger_node_name: str
) -> dict:
    """Build a Telegram reply node."""
    return {
        "parameters": {
            "chatId": f"={{{{ $('{trigger_node_name}').item.json.message.chat.id }}}}",
            "text": "={{ $json.output }}",
            "additionalFields": {},
        },
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2,
        "position": [560, -592],
        "id": str(uuid.uuid4()),
        "name": name,
    }


def _build_tool_node(tool: HttpTool, index: int) -> dict:
    """Build an httpRequestTool node from an HttpTool definition."""
    # Build URL — replace AI params with $fromAI expressions
    url = tool.url
    needs_expression_prefix = False
    for param_name, param in tool.params.items():
        placeholder = f"{{{param_name}}}"
        from_ai = f"{{{{ $fromAI('{param_name}', '{param.description}', '{param.type}') }}}}"
        url = url.replace(placeholder, from_ai)
        needs_expression_prefix = True

    if needs_expression_prefix:
        url = f"={url}"

    parameters: dict = {
        "toolDescription": tool.description,
        "url": url,
        "options": {},
    }

    if tool.method != "GET":
        parameters["method"] = tool.method

    # Auth + custom headers
    header_list: list[dict] = []
    if tool.auth:
        header_list.append({
            "name": "Authorization",
            "value": f"=token {{{{ $env.{tool.auth.env} }}}}",
        })
    for header_name, header_value in tool.headers.items():
        header_list.append({"name": header_name, "value": header_value})

    if header_list:
        parameters["sendHeaders"] = True
        parameters["headerParameters"] = {"parameters": header_list}

    # JSON body
    if tool.body:
        parameters["sendBody"] = True
        parameters["specifyBody"] = "json"
        parameters["jsonBody"] = (
            "={{ /*n8n-auto-generated-fromAI-override*/ $fromAI('JSON', ``, 'json') }}"
        )

    x_offset = -100 + (index * 200)
    return {
        "parameters": parameters,
        "type": "n8n-nodes-base.httpRequestTool",
        "typeVersion": 4.4,
        "position": [x_offset, -352],
        "id": str(uuid.uuid4()),
        "name": tool.name,
    }


def _build_connections(
    trigger_node_name: str,
    if_node_name: str | None,
    agent_node_name: str,
    reply_node_name: str,
    model_node_name: str,
    tool_names: list[str],
) -> dict:
    """Build the connections dict wiring all nodes together."""
    connections: dict = {}

    if if_node_name:
        # Trigger → If → Agent
        connections[trigger_node_name] = {
            "main": [[{"node": if_node_name, "type": "main", "index": 0}]]
        }
        connections[if_node_name] = {
            "main": [[{"node": agent_node_name, "type": "main", "index": 0}]]
        }
    else:
        # Trigger → Agent directly
        connections[trigger_node_name] = {
            "main": [[{"node": agent_node_name, "type": "main", "index": 0}]]
        }
        agent_node_name: {
            "main": [[{"node": reply_node_name, "type": "main", "index": 0}]]
        },
        model_node_name: {
            "ai_languageModel": [
                [{"node": agent_node_name, "type": "ai_languageModel", "index": 0}]
            ]
        },
    }

    for tool_name in tool_names:
        connections[tool_name] = {
            "ai_tool": [[{"node": agent_node_name, "type": "ai_tool", "index": 0}]]
        }

    return connections
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_adapters/test_compiler.py -v`
Expected: All 16 tests PASS

- [ ] **Step 5: Commit**

```bash
git add council/adapters/n8n/compiler.py tests/test_adapters/test_compiler.py
git commit -m "feat: add n8n workflow compiler (AgentDefinition → workflow JSON)"
```

---

### Task 8: n8n deployer — upsert workflows via REST API

**Files:**
- Create: `council/adapters/n8n/deployer.py`
- Create: `tests/test_adapters/test_deployer.py`

- [ ] **Step 1: Write failing tests**

Tests use `httpx` mock transport to avoid real API calls.

```python
# tests/test_adapters/test_deployer.py
import json

import httpx
import pytest

from council.adapters.n8n.deployer import N8nDeployer


class MockTransport(httpx.BaseTransport):
    """Records requests and returns canned responses."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.responses: dict[str, httpx.Response] = {}

    def add_response(self, method: str, path: str, status_code: int, json_data: dict):
        key = f"{method} {path}"
        self.responses[key] = httpx.Response(status_code, json=json_data)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = f"{request.method} {request.url.path}"
        if key in self.responses:
            return self.responses[key]
        # Default: return empty list for GET workflows
        if "workflows" in str(request.url) and request.method == "GET":
            return httpx.Response(200, json={"data": []})
        return httpx.Response(404, json={"message": "not found"})


@pytest.fixture
def transport():
    return MockTransport()


@pytest.fixture
def deployer(transport):
    client = httpx.Client(transport=transport, base_url="http://n8n:5678")
    return N8nDeployer(client=client, api_key="test-key")


def test_deploy_creates_new_workflow(deployer, transport):
    transport.add_response("POST", "/api/v1/workflows", 201, {"id": "abc123"})
    transport.add_response("PATCH", "/api/v1/workflows/abc123", 200, {"id": "abc123", "active": True})

    workflow = {"name": "Test Workflow", "nodes": [], "connections": {}, "settings": {}}
    result = deployer.deploy(workflow)

    assert result == "abc123"
    post_req = next(r for r in transport.requests if r.method == "POST")
    body = json.loads(post_req.content)
    assert body["name"] == "Test Workflow"


def test_deploy_updates_existing_workflow(deployer, transport):
    transport.add_response("GET", "/api/v1/workflows", 200, {
        "data": [{"id": "existing-id", "name": "Test Workflow"}]
    })
    transport.add_response("PUT", "/api/v1/workflows/existing-id", 200, {"id": "existing-id"})
    transport.add_response("PATCH", "/api/v1/workflows/existing-id", 200, {"id": "existing-id", "active": True})

    workflow = {"name": "Test Workflow", "nodes": [], "connections": {}, "settings": {}}
    result = deployer.deploy(workflow)

    assert result == "existing-id"
    put_req = next(r for r in transport.requests if r.method == "PUT")
    assert "existing-id" in str(put_req.url)


def test_deploy_activates_workflow(deployer, transport):
    transport.add_response("POST", "/api/v1/workflows", 201, {"id": "new-id"})
    transport.add_response("PATCH", "/api/v1/workflows/new-id", 200, {"id": "new-id", "active": True})

    workflow = {"name": "Test", "nodes": [], "connections": {}, "settings": {}}
    deployer.deploy(workflow, activate=True)

    patch_req = next(r for r in transport.requests if r.method == "PATCH")
    body = json.loads(patch_req.content)
    assert body["active"] is True


def test_deployer_sends_api_key_header(deployer, transport):
    transport.add_response("POST", "/api/v1/workflows", 201, {"id": "abc"})
    transport.add_response("PATCH", "/api/v1/workflows/abc", 200, {"id": "abc"})

    deployer.deploy({"name": "Test", "nodes": [], "connections": {}, "settings": {}})

    for req in transport.requests:
        assert req.headers["X-N8N-API-KEY"] == "test-key"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_adapters/test_deployer.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Implement deployer**

```python
# council/adapters/n8n/deployer.py
import httpx


class N8nDeployer:
    """Deploys workflow JSON to n8n via its REST API."""

    def __init__(self, client: httpx.Client, api_key: str):
        self._client = client
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "X-N8N-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }

    def _find_workflow_by_name(self, name: str) -> str | None:
        """Find an existing workflow ID by name, or None."""
        resp = self._client.get("/api/v1/workflows", headers=self._headers(), params={"limit": 100})
        resp.raise_for_status()
        for wf in resp.json().get("data", []):
            if wf["name"] == name:
                return wf["id"]
        return None

    def deploy(self, workflow: dict, activate: bool = True) -> str:
        """Upsert a workflow and optionally activate it. Returns the workflow ID."""
        name = workflow["name"]
        existing_id = self._find_workflow_by_name(name)

        if existing_id:
            resp = self._client.put(
                f"/api/v1/workflows/{existing_id}",
                headers=self._headers(),
                json=workflow,
            )
            resp.raise_for_status()
            workflow_id = existing_id
        else:
            resp = self._client.post(
                "/api/v1/workflows",
                headers=self._headers(),
                json=workflow,
            )
            resp.raise_for_status()
            workflow_id = resp.json()["id"]

        if activate:
            self._client.patch(
                f"/api/v1/workflows/{workflow_id}",
                headers=self._headers(),
                json={"active": True},
            )

        return workflow_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_adapters/test_deployer.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add council/adapters/n8n/deployer.py tests/test_adapters/test_deployer.py
git commit -m "feat: add n8n workflow deployer with upsert and activation"
```

---

### Task 9: n8n credentials — create from env vars

**Files:**
- Create: `council/adapters/n8n/credentials.py`
- Create: `tests/test_adapters/test_credentials.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_adapters/test_credentials.py
import json

import httpx
import pytest

from council.adapters.n8n.credentials import N8nCredentialManager


class MockTransport(httpx.BaseTransport):
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self._existing_creds: list[dict] = []

    def set_existing(self, creds: list[dict]):
        self._existing_creds = creds

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET" and "credentials" in str(request.url):
            return httpx.Response(200, json={"data": self._existing_creds})
        if request.method == "POST" and "credentials" in str(request.url):
            body = json.loads(request.content)
            return httpx.Response(201, json={"id": "new-cred-id", "name": body["name"]})
        return httpx.Response(404)


@pytest.fixture
def transport():
    return MockTransport()


@pytest.fixture
def manager(transport):
    client = httpx.Client(transport=transport, base_url="http://n8n:5678")
    return N8nCredentialManager(client=client, api_key="test-key")


def test_ensure_telegram_credential(manager, transport):
    cred_id = manager.ensure_credential(
        name="Telegram account",
        cred_type="telegramApi",
        data={"accessToken": "bot-token-123"},
    )
    assert cred_id == "new-cred-id"


def test_returns_existing_credential_id(manager, transport):
    transport.set_existing([{"id": "existing-id", "name": "Telegram account"}])
    cred_id = manager.ensure_credential(
        name="Telegram account",
        cred_type="telegramApi",
        data={"accessToken": "bot-token-123"},
    )
    assert cred_id == "existing-id"
    # Should NOT have made a POST request
    post_reqs = [r for r in transport.requests if r.method == "POST"]
    assert len(post_reqs) == 0


def test_ensure_openai_credential_for_litellm(manager, transport):
    cred_id = manager.ensure_credential(
        name="LiteLLM Proxy",
        cred_type="openAiApi",
        data={"apiKey": "sk-council-local"},
    )
    assert cred_id == "new-cred-id"
    post_req = next(r for r in transport.requests if r.method == "POST")
    body = json.loads(post_req.content)
    assert body["type"] == "openAiApi"
    assert body["data"]["apiKey"] == "sk-council-local"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_adapters/test_credentials.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Implement credential manager**

```python
# council/adapters/n8n/credentials.py
import httpx


class N8nCredentialManager:
    """Creates and manages n8n credentials via REST API."""

    def __init__(self, client: httpx.Client, api_key: str):
        self._client = client
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "X-N8N-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }

    def ensure_credential(self, name: str, cred_type: str, data: dict) -> str:
        """Create a credential if it doesn't exist. Returns the credential ID."""
        existing_id = self._find_by_name(name)
        if existing_id:
            return existing_id

        resp = self._client.post(
            "/api/v1/credentials",
            headers=self._headers(),
            json={"name": name, "type": cred_type, "data": data},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _find_by_name(self, name: str) -> str | None:
        resp = self._client.get("/api/v1/credentials", headers=self._headers())
        resp.raise_for_status()
        for cred in resp.json().get("data", []):
            if cred["name"] == name:
                return cred["id"]
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_adapters/test_credentials.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add council/adapters/n8n/credentials.py tests/test_adapters/test_credentials.py
git commit -m "feat: add n8n credential manager for auto-creating credentials"
```

---

### Task 10: Project config loader

**Files:**
- Create: `council/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py
from pathlib import Path

import pytest

from council.config import load_project_config, ProjectConfig


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_project_config(tmp_path):
    config_file = tmp_path / "council.toml"
    config_file.write_text("""
[project]
owner = "majorlongval"
repo = "theCouncilOfElrond"

[litellm]
master_key = "sk-test"
""")
    config = load_project_config(config_file)
    assert config.owner == "majorlongval"
    assert config.repo == "theCouncilOfElrond"
    assert config.litellm_master_key == "sk-test"


def test_project_config_not_found():
    with pytest.raises(FileNotFoundError):
        load_project_config(Path("/nonexistent/council.toml"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_config.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Implement config loader**

```python
# council/config.py
import tomllib
from pathlib import Path

from pydantic import BaseModel


class ProjectConfig(BaseModel):
    """Project-level configuration from council.toml."""
    owner: str
    repo: str
    litellm_master_key: str


def load_project_config(path: Path) -> ProjectConfig:
    """Load project config from a TOML file."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return ProjectConfig(
        owner=data["project"]["owner"],
        repo=data["project"]["repo"],
        litellm_master_key=data["litellm"]["master_key"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_config.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add council/config.py tests/test_config.py
git commit -m "feat: add project config loader for council.toml"
```

---

### Task 11: URL placeholder resolution

The compiler needs to resolve `{owner}` and `{repo}` placeholders in tool URLs from the project config before outputting the workflow JSON.

**Files:**
- Create: `council/wiring/resolver.py`
- Create: `tests/test_wiring/test_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_wiring/test_resolver.py
from council.config import ProjectConfig
from council.wiring.tools.models import BearerToken, HttpTool, Param
from council.wiring.resolver import resolve_tool_urls


def test_resolves_owner_and_repo():
    config = ProjectConfig(owner="majorlongval", repo="theCouncilOfElrond", litellm_master_key="sk-test")
    tool = HttpTool(
        name="List Issues",
        description="List issues.",
        url="https://api.github.com/repos/{owner}/{repo}/issues",
        auth=BearerToken(env="GITHUB_TOKEN"),
    )
    resolved = resolve_tool_urls([tool], config)
    assert resolved[0].url == "https://api.github.com/repos/majorlongval/theCouncilOfElrond/issues"


def test_preserves_ai_params():
    config = ProjectConfig(owner="majorlongval", repo="theCouncilOfElrond", litellm_master_key="sk-test")
    tool = HttpTool(
        name="Read File",
        description="Read a file.",
        url="https://api.github.com/repos/{owner}/{repo}/contents/{filepath}",
        params={"filepath": Param(description="Path to file")},
        auth=BearerToken(env="GITHUB_TOKEN"),
    )
    resolved = resolve_tool_urls([tool], config)
    # {filepath} should NOT be resolved — it's an AI param
    assert "{filepath}" in resolved[0].url
    # {owner} and {repo} should be resolved
    assert "{owner}" not in resolved[0].url
    assert "majorlongval" in resolved[0].url


def test_returns_new_list_does_not_mutate():
    config = ProjectConfig(owner="majorlongval", repo="theCouncilOfElrond", litellm_master_key="sk-test")
    tool = HttpTool(
        name="Test",
        description="Test.",
        url="https://api.github.com/repos/{owner}/{repo}/test",
    )
    resolved = resolve_tool_urls([tool], config)
    assert resolved[0].url != tool.url  # original unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_wiring/test_resolver.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Implement resolver**

```python
# council/wiring/resolver.py
from council.config import ProjectConfig
from council.wiring.tools.models import HttpTool


def resolve_tool_urls(tools: list[HttpTool], config: ProjectConfig) -> list[HttpTool]:
    """Resolve project-level placeholders ({owner}, {repo}) in tool URLs.

    AI-provided params (those in tool.params) are left as placeholders
    for the compiler to convert to $fromAI() expressions.
    """
    resolved: list[HttpTool] = []
    for tool in tools:
        url = tool.url.replace("{owner}", config.owner).replace("{repo}", config.repo)
        resolved.append(tool.model_copy(update={"url": url}))
    return resolved
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_wiring/test_resolver.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add council/wiring/resolver.py tests/test_wiring/test_resolver.py
git commit -m "feat: add URL placeholder resolver for project config"
```

---

### Task 12: Entry point (__main__.py)

**Files:**
- Create: `council/__main__.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_main.py
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from council.__main__ import run_config


def test_config_generates_litellm_yaml(tmp_path):
    # Create agent TOML
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "gimli.toml").write_text("""
name = "Gimli"
role = "Builder"
brain = "gemini/gemini-flash-latest"
prompt = "You are Gimli."
tools = ["github.list_issues"]
artifacts = []

[trigger]
type = "telegram"
command = "/run gimli"

[reply]
type = "telegram"
""")

    # Create project config
    config_file = tmp_path / "council.toml"
    config_file.write_text("""
[project]
owner = "majorlongval"
repo = "theCouncilOfElrond"

[litellm]
master_key = "sk-test"
""")

    output_file = tmp_path / "litellm_config.yaml"

    run_config(
        agents_dir=agents_dir,
        config_path=config_file,
        output_path=output_file,
    )

    assert output_file.exists()
    parsed = yaml.safe_load(output_file.read_text())
    assert len(parsed["model_list"]) == 1
    assert parsed["model_list"][0]["model_name"] == "gemini/gemini-flash-latest"
    assert parsed["general_settings"]["master_key"] == "sk-test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_main.py -v`
Expected: FAIL with "ImportError"

- [ ] **Step 3: Implement entry point**

```python
# council/__main__.py
"""Entry point: python -m council <config|deploy>."""
import sys
from pathlib import Path

from council.config import load_project_config
from council.domain.loader import load_all_agents
from council.casting.litellm import generate_litellm_config


def run_config(
    agents_dir: Path,
    config_path: Path,
    output_path: Path,
) -> None:
    """Phase 1: Generate LiteLLM config from agent definitions."""
    config = load_project_config(config_path)
    agents = load_all_agents(agents_dir)

    if not agents:
        print("[council] No agent definitions found — skipping config generation.")
        return

    litellm_yaml = generate_litellm_config(agents, master_key=config.litellm_master_key)
    output_path.write_text(litellm_yaml)
    print(f"[council] Generated LiteLLM config with {len(agents)} agent(s) → {output_path}")


def run_deploy(
    agents_dir: Path,
    config_path: Path,
    n8n_api_url: str,
    n8n_api_key: str,
    telegram_token: str = "",
) -> None:
    """Phase 2: Compile and deploy workflows to n8n."""
    import httpx

    from council.wiring.tools import resolve_tools
    from council.wiring.resolver import resolve_tool_urls
    from council.adapters.n8n.compiler import compile_workflow
    from council.adapters.n8n.deployer import N8nDeployer
    from council.adapters.n8n.credentials import N8nCredentialManager

    config = load_project_config(config_path)
    agents = load_all_agents(agents_dir)

    if not agents:
        print("[council] No agent definitions found — skipping deployment.")
        return

    client = httpx.Client(base_url=n8n_api_url)
    deployer = N8nDeployer(client=client, api_key=n8n_api_key)
    cred_manager = N8nCredentialManager(client=client, api_key=n8n_api_key)

    # Ensure LiteLLM credential exists (openAiApi type for the Chat Model node)
    litellm_cred_id = cred_manager.ensure_credential(
        name="LiteLLM Proxy",
        cred_type="openAiApi",
        data={"apiKey": config.litellm_master_key},
    )

    # Ensure Telegram credential if token is provided
    telegram_cred_id = None
    if telegram_token:
        telegram_cred_id = cred_manager.ensure_credential(
            name="Telegram account",
            cred_type="telegramApi",
            data={"accessToken": telegram_token},
        )

    for agent in agents:
        print(f"[council] Deploying '{agent.name}'...")
        tools = resolve_tools(agent.tools)
        tools = resolve_tool_urls(tools, config)
        workflow = compile_workflow(agent, tools)

        # Inject credential references into nodes
        for node in workflow["nodes"]:
            if node["type"] == "n8n-nodes-base.telegramTrigger" and telegram_cred_id:
                node["credentials"] = {"telegramApi": {"id": telegram_cred_id, "name": "Telegram account"}}
            elif node["type"] == "n8n-nodes-base.telegram" and telegram_cred_id:
                node["credentials"] = {"telegramApi": {"id": telegram_cred_id, "name": "Telegram account"}}
            elif node["type"] == "@n8n/n8n-nodes-langchain.lmChatOpenAi":
                node["credentials"] = {"openAiApi": {"id": litellm_cred_id, "name": "LiteLLM Proxy"}}

        workflow_id = deployer.deploy(workflow)
        print(f"[council] Deployed '{agent.name}' (id: {workflow_id})")

    print(f"[council] Done — {len(agents)} agent(s) deployed.")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m council <config|deploy>")
        sys.exit(1)

    command = sys.argv[1]
    # Default paths — overridable via env vars
    import os
    agents_dir = Path(os.environ.get("COUNCIL_AGENTS_DIR", "/app/agents"))
    config_path = Path(os.environ.get("COUNCIL_CONFIG_PATH", "/app/council.toml"))

    if command == "config":
        output_path = Path(os.environ.get("LITELLM_CONFIG_OUTPUT", "/config/litellm_config.yaml"))
        run_config(agents_dir, config_path, output_path)
    elif command == "deploy":
        n8n_api_url = os.environ.get("N8N_API_URL", "http://n8n:5678")
        n8n_api_key = os.environ.get("N8N_API_KEY", "")
        if not n8n_api_key:
            print("[council] N8N_API_KEY not set — skipping deployment.")
            sys.exit(0)
        telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        run_deploy(agents_dir, config_path, n8n_api_url, n8n_api_key, telegram_token)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_main.py -v`
Expected: All 1 test(s) PASS

- [ ] **Step 5: Commit**

```bash
git add council/__main__.py tests/test_main.py
git commit -m "feat: add council entry point with config and deploy commands"
```

---

### Task 13: Gimli agent definition

**Files:**
- Create: `agents/gimli.toml`

- [ ] **Step 1: Create Gimli's TOML definition**

```toml
name = "Gimli"
role = "Builder"
brain = "gemini/gemini-flash-latest"

prompt = """
You are Gimli, a builder agent in the Council of Elrond.

You love building things and shipping code. You take pride in your craft — clean code, passing tests, solid architecture. When there's work to be done, you do it.

You have tools to interact with the GitHub repo majorlongval/theCouncilOfElrond.

RULES:
- Be concise and act swiftly.
- Use at most 2 scouting calls (list issues, read file), then act.
- Do NOT recursively explore directories. Only read specific files you need.
- Your deliverable is always a concrete artifact: an issue created, a file read and summarized.
- When done, summarize what you accomplished in 2-3 sentences.
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

- [ ] **Step 2: Verify it loads**

Run: `source .venv/bin/activate && python -c "from council.domain.loader import load_agent; from pathlib import Path; a = load_agent(Path('agents/gimli.toml')); print(f'{a.name} ({a.role}) — brain: {a.brain}, tools: {len(a.tools)}')"`
Expected: `Gimli (Builder) — brain: gemini/gemini-flash-latest, tools: 3`

- [ ] **Step 3: Commit**

```bash
git add agents/gimli.toml
git commit -m "feat: add Gimli agent definition (TOML)"
```

---

### Task 14: Docker integration

**Files:**
- Create: `Dockerfile.council`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Dockerfile.council
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY council/ council/
RUN pip install --no-cache-dir .

COPY agents/ agents/
COPY council.toml .

ENTRYPOINT ["python", "-m", "council"]
```

- [ ] **Step 2: Update docker-compose.yml**

Replace the existing `seed` service and add `litellm`, `seed-config`, `seed-deploy` services. Keep `n8n` and `n8n-mcp` as-is.

```yaml
services:
  n8n:
    image: n8nio/n8n
    ports:
      - "5678:5678"
    volumes:
      - ./n8n-data:/home/node/.n8n
    env_file: .env
    environment:
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      - WEBHOOK_URL=${WEBHOOK_URL:-http://localhost:5678/}
      - N8N_BLOCK_ENV_ACCESS_IN_NODE=false
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:5678/"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
    networks:
      - council-net

  seed-config:
    build:
      context: .
      dockerfile: Dockerfile.council
    command: ["config"]
    environment:
      - COUNCIL_AGENTS_DIR=/app/agents
      - COUNCIL_CONFIG_PATH=/app/council.toml
      - LITELLM_CONFIG_OUTPUT=/config/litellm_config.yaml
    volumes:
      - litellm-config:/config
    networks:
      - council-net

  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    ports:
      - "4000:4000"
    volumes:
      - litellm-config:/config:ro
    command: ["--config", "/config/litellm_config.yaml", "--port", "4000"]
    env_file: .env
    depends_on:
      seed-config:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4000/health"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
    networks:
      - council-net

  seed-deploy:
    build:
      context: .
      dockerfile: Dockerfile.council
    command: ["deploy"]
    env_file: .env
    environment:
      - N8N_API_URL=http://n8n:5678
      - COUNCIL_AGENTS_DIR=/app/agents
      - COUNCIL_CONFIG_PATH=/app/council.toml
    depends_on:
      n8n:
        condition: service_healthy
      litellm:
        condition: service_healthy
    networks:
      - council-net

  n8n-mcp:
    image: ghcr.io/czlonkowski/n8n-mcp:latest
    ports:
      - "3000:3000"
    env_file: .env
    environment:
      - N8N_API_URL=http://n8n:5678
      - MCP_MODE=http
      - AUTH_TOKEN=${MCP_AUTH_TOKEN:-local-dev-token}
      - WEBHOOK_SECURITY_MODE=moderate
    depends_on:
      n8n:
        condition: service_healthy
    networks:
      - council-net

networks:
  council-net:

volumes:
  litellm-config:
```

- [ ] **Step 3: Update .env.example**

Add `LITELLM_MASTER_KEY` and note about provider-specific keys. Ensure `N8N_API_KEY` is present:

```
# n8n API key — generate in n8n UI: Settings > API > Create API Key
N8N_API_KEY=your-api-key-here

# LiteLLM master key — used by n8n to authenticate with the LLM proxy
LITELLM_MASTER_KEY=sk-council-local

# Provider API keys — only needed for providers referenced in agents/*.toml
# ANTHROPIC_API_KEY=your-anthropic-key-here
# OPENAI_API_KEY=your-openai-key-here
```

- [ ] **Step 4: Update .gitignore**

Add:
```
.venv/
__pycache__/
*.egg-info/
.superpowers/
```

- [ ] **Step 5: Commit**

```bash
git add Dockerfile.council docker-compose.yml .env.example .gitignore
git commit -m "feat: add Docker integration with LiteLLM and two-phase seed"
```

---

### Task 15: End-to-end verification

**Files:** None (manual testing)

- [ ] **Step 1: Run all unit tests**

Run: `source .venv/bin/activate && pytest -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Test config generation locally**

Run:
```bash
source .venv/bin/activate
COUNCIL_AGENTS_DIR=agents COUNCIL_CONFIG_PATH=council.toml LITELLM_CONFIG_OUTPUT=/tmp/litellm_config.yaml python -m council config
cat /tmp/litellm_config.yaml
```
Expected: Valid YAML with gemini/gemini-flash-latest model entry

- [ ] **Step 3: Build Docker image**

Run: `docker build -f Dockerfile.council -t council:local .`
Expected: Build succeeds

- [ ] **Step 4: Start the full stack**

Run: `docker compose up -d`
Expected: All services start. Check with `docker compose ps` — all should be healthy or exited 0.

- [ ] **Step 5: Verify workflow was deployed to n8n**

Open http://localhost:5678 and check that the "Gimli — Builder" workflow exists with:
- Telegram Trigger → If → AI Agent → Reply
- OpenAI Chat Model sub-node
- 3 HTTP Request Tool nodes

- [ ] **Step 6: Test via Telegram**

Send `/run gimli check the README` to the Telegram bot.
Expected: Gimli responds with a summary (LLM call goes through LiteLLM → Gemini).

- [ ] **Step 7: Commit any fixes**

If any adjustments were needed during verification, commit them.

- [ ] **Step 8: Remove old workflow files**

The hand-crafted workflow JSON files are now obsolete:

```bash
git rm workflows/gimli-v2.json workflows/telegram-run-agent.json workflows/config.json
git commit -m "chore: remove hand-crafted workflow JSON (replaced by TOML definitions)"
```

Note: Keep `scripts/export-workflow.sh` — it's still useful for debugging.
