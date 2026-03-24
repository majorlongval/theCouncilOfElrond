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
