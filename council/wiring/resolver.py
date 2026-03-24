from council.config import ProjectConfig
from council.wiring.tools.models import HttpTool


def resolve_tool_urls(tools: list[HttpTool], config: ProjectConfig) -> list[HttpTool]:
    """Resolve project-level placeholders ({owner}, {repo}) in tool URLs.

    AI-provided params (those in tool.params) are left as placeholders
    for the compiler to convert to $fromAI() expressions.
    """
    resolved: list[HttpTool] = []
    for tool in tools:
        url = tool.url.replace("{owner}", config.owner).replace("{repo}", config.repo)
        resolved.append(tool.model_copy(update={"url": url}))
    return resolved
