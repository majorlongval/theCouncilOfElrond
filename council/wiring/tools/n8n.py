from council.wiring.tools.models import WorkflowTool

execute_workflow = WorkflowTool(
    name="Execute Gimli",
    description="Trigger Gimli's workflow to execute a task. Pass instructions as input.",
    target_agent="Gimli",
)
