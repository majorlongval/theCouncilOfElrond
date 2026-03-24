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
