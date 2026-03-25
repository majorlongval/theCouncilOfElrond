from council.config import ProjectConfig
from council.wiring.tools.models import HttpTool, Tool


def resolve_tool_urls(tools: list[Tool], config: ProjectConfig) -> list[Tool]:
    """Resolve project-level placeholders ({owner}, {repo}) in tool URLs.

    WorkflowTool instances are passed through unchanged — they have no URL.
    """
    resolved: list[Tool] = []
    for tool in tools:
        if isinstance(tool, HttpTool):
            url = tool.url.replace("{owner}", config.owner).replace("{repo}", config.repo)
            resolved.append(tool.model_copy(update={"url": url}))
        else:
            resolved.append(tool)
    return resolved
