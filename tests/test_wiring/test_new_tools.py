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
    tool = WorkflowTool(
        name="Execute Gimli",
        description="Trigger Gimli's workflow.",
        target_agent="Gimli",
    )
    assert isinstance(tool, (HttpTool, WorkflowTool))


def test_http_tool_is_tool_type():
    tool = HttpTool(name="Test", description="Test tool", url="http://example.com")
    assert isinstance(tool, (HttpTool, WorkflowTool))
