from council.wiring.tools.models import HttpTool, WorkflowTool, Tool
from council.wiring.tools.github_write import update_file
from council.wiring.tools.github_pr import read_pr, merge_pr


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
