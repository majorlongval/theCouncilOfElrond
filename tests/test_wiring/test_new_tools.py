from council.wiring.tools.models import HttpTool, WorkflowTool, Tool
from council.wiring.tools.github_write import update_file
from council.wiring.tools.github_pr import read_pr, merge_pr
from council.wiring.tools.n8n import execute_workflow as execute_workflow_tool


def test_workflow_tool_creation():
    tool = WorkflowTool(
        name="Execute Gimli",
        description="Trigger Gimli's workflow.",
        target_agent="Gimli",
    )
    assert tool.name == "Execute Gimli"
    assert tool.target_agent == "Gimli"


def test_workflow_tool_is_tool_type():
    tool = WorkflowTool(
        name="Execute Gimli",
        description="Trigger Gimli's workflow.",
        target_agent="Gimli",
    )
    assert isinstance(tool, (HttpTool, WorkflowTool))


def test_http_tool_is_tool_type():
    tool = HttpTool(name="Test", description="Test tool", url="http://example.com")
    assert isinstance(tool, (HttpTool, WorkflowTool))


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


def test_execute_workflow_tool():
    assert execute_workflow_tool.name == "Execute Gimli"
    assert execute_workflow_tool.target_agent == "Gimli"
    assert isinstance(execute_workflow_tool, WorkflowTool)


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
    tools = resolve_tools(["github.list_issues", "n8n.execute_workflow"])
    assert len(tools) == 2
    assert isinstance(tools[0], HttpTool)
    assert isinstance(tools[1], WorkflowTool)
