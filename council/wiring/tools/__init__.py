import importlib

from council.wiring.tools.models import HttpTool


def resolve_tool(dotted_name: str) -> HttpTool:
    """Resolve a dotted tool reference like 'github.read_file' to an HttpTool."""
    parts = dotted_name.split(".")
    if len(parts) != 2:
        raise ValueError(f"Unknown tool: {dotted_name} (expected 'module.name' format)")

    module_name, attr_name = parts

    try:
        module = importlib.import_module(f"council.wiring.tools.{module_name}")
    except ModuleNotFoundError:
        raise ValueError(f"Unknown tool: {dotted_name} (module '{module_name}' not found)")

    tool = getattr(module, attr_name, None)
    if not isinstance(tool, HttpTool):
        raise ValueError(f"Unknown tool: {dotted_name} ('{attr_name}' not found in '{module_name}')")

    return tool


def resolve_tools(dotted_names: list[str]) -> list[HttpTool]:
    """Resolve a list of dotted tool references."""
    return [resolve_tool(name) for name in dotted_names]
