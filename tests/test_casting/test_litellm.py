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
    parsed = yaml.safe_load(config)
    assert "model_list" in parsed
