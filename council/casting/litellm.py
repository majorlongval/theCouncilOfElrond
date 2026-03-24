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
    """Generate a LiteLLM config YAML from agent definitions.

    Deduplicates brains so each unique model appears once in the model_list.
    The master_key is embedded under general_settings for the LiteLLM proxy.
    """
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
