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
