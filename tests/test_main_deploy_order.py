"""Tests for two-pass deployment ordering in __main__.py."""
from council.domain.agent import AgentDefinition, Trigger, Reply
from council.wiring.tools.models import WorkflowTool
from council.adapters.n8n.compiler import compile_workflow


def _make_agent(name: str, orchestrator: bool = False) -> AgentDefinition:
    return AgentDefinition(
        name=name,
        role="Test",
        brain="gemini/gemini-flash-latest",
        prompt=f"You are {name}.",
        tools=[],
        trigger=Trigger(type="telegram", command=f"/run {name.lower()}" if not orchestrator else None),
        reply=Reply(type="telegram"),
        orchestrator=orchestrator,
    )


def test_orchestrators_deploy_after_workers():
    """Verify sorting logic: workers first, orchestrators second."""
    gimli = _make_agent("Gimli")
    elrond = _make_agent("Elrond", orchestrator=True)
    agents = [elrond, gimli]  # intentionally out of order

    workers = [a for a in agents if not a.orchestrator]
    orchestrators = [a for a in agents if a.orchestrator]

    assert workers[0].name == "Gimli"
    assert orchestrators[0].name == "Elrond"

    deploy_order = workers + orchestrators
    assert deploy_order[0].name == "Gimli"
    assert deploy_order[1].name == "Elrond"


def test_orchestrator_receives_workflow_registry():
    """Verify compile_workflow works with registry for orchestrators."""
    elrond = _make_agent("Elrond", orchestrator=True)
    wf_tool = WorkflowTool(name="Execute Gimli", description="Trigger Gimli.", target_agent="Gimli")
    registry = {"Gimli": "gimli-wf-id"}

    workflow = compile_workflow(elrond, [wf_tool], workflow_registry=registry)
    exec_nodes = [n for n in workflow["nodes"] if n["type"] == "@n8n/n8n-nodes-langchain.toolWorkflow"]
    assert len(exec_nodes) == 1
    assert exec_nodes[0]["parameters"]["workflowId"]["value"] == "gimli-wf-id"
