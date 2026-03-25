from typing import Literal

from pydantic import BaseModel, ConfigDict


class Param(BaseModel):
    """A parameter the AI agent must provide when calling a tool."""

    description: str
    type: str = "string"


class BearerToken(BaseModel):
    """Auth via Bearer token sourced from an environment variable at runtime."""

    env: str


class JsonBody(BaseModel):
    """Structured JSON body the AI agent must supply when invoking the tool.

    model_config disables Pydantic's protected-namespace check because the
    field name `schema` would otherwise collide with Pydantic's own `model_schema`.
    """

    model_config = ConfigDict(protected_namespaces=())

    schema: dict[str, str]


class HttpTool(BaseModel):
    """A tool an AI agent can invoke.

    At compile time this is translated into an n8n httpRequestTool node.
    `params` holds only the placeholders the AI must fill — project-level
    URL parameters (e.g. {owner}, {repo}) are injected by the wiring layer.
    """

    name: str
    description: str
    url: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    params: dict[str, Param] = {}
    auth: BearerToken | None = None
    headers: dict[str, str] = {}
    body: JsonBody | None = None


class WorkflowTool(BaseModel):
    """A tool that triggers another agent's n8n workflow.

    Unlike HttpTool, this compiles to an Execute Workflow node in n8n.
    The target_agent name is resolved to a workflow ID at deploy time.
    """

    name: str
    description: str
    target_agent: str


# Union of all tool types — used by the tool registry and compiler.
Tool = HttpTool | WorkflowTool
