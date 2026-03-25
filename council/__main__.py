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
    """Phase 1: Generate LiteLLM config from agent definitions.

    Reads all agent TOML files from agents_dir, loads the project config,
    and writes a LiteLLM YAML config to output_path.
    """
    config = load_project_config(config_path)
    agents = load_all_agents(agents_dir)

    if not agents:
        print("[council] No agent definitions found — skipping config generation.")
        return

    litellm_yaml = generate_litellm_config(agents, master_key=config.litellm_master_key)
    output_path.write_text(litellm_yaml)
    print(f"[council] Generated LiteLLM config with {len(agents)} agent(s) → {output_path}")


def _inject_credentials(
    workflow: dict,
    telegram_cred_id: str | None,
    litellm_cred_id: str,
) -> None:
    """Inject credential references into workflow nodes.

    Mutates the workflow dict in-place — n8n requires credential IDs to be
    embedded in each node rather than passed separately at deploy time.
    """
    for node in workflow["nodes"]:
        if node["type"] == "n8n-nodes-base.telegramTrigger" and telegram_cred_id:
            node["credentials"] = {"telegramApi": {"id": telegram_cred_id, "name": "Telegram account"}}
        elif node["type"] == "n8n-nodes-base.telegram" and telegram_cred_id:
            node["credentials"] = {"telegramApi": {"id": telegram_cred_id, "name": "Telegram account"}}
        elif node["type"] == "@n8n/n8n-nodes-langchain.lmChatOpenAi":
            node["credentials"] = {"openAiApi": {"id": litellm_cred_id, "name": "LiteLLM Proxy"}}


def run_deploy(
    agents_dir: Path,
    config_path: Path,
    n8n_api_url: str,
    n8n_api_key: str,
    telegram_token: str = "",
) -> None:
    """Phase 2: Compile and deploy workflows to n8n.

    Lazy imports are used here so that httpx and adapter modules are not
    loaded when only doing config generation (run_config path).
    """
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

    # Ensure LiteLLM credential exists (openAiApi type for the Chat Model node).
    # The 'url' field routes all requests to LiteLLM instead of OpenAI.
    # 'header' must be explicitly False to avoid requiring headerName/headerValue.
    litellm_cred_id = cred_manager.ensure_credential(
        name="LiteLLM Proxy",
        cred_type="openAiApi",
        data={
            "apiKey": config.litellm_master_key,
            "url": "http://litellm:4000/v1",
            "header": False,
        },
    )

    # Ensure Telegram credential if token is provided
    telegram_cred_id = None
    if telegram_token:
        telegram_cred_id = cred_manager.ensure_credential(
            name="Telegram account",
            cred_type="telegramApi",
            data={"accessToken": telegram_token},
        )

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

    # Pass 2: Deploy orchestrators with workflow registry so they can reference
    # worker workflow IDs via executeWorkflow nodes.
    for agent in orchestrators:
        print(f"[council] Deploying orchestrator '{agent.name}'...")
        tools = resolve_tools(agent.tools)
        tools = resolve_tool_urls(tools, config)
        workflow = compile_workflow(agent, tools, workflow_registry=workflow_registry)
        _inject_credentials(workflow, telegram_cred_id, litellm_cred_id)
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
