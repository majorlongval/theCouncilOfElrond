import tomllib
from pathlib import Path

from council.domain.agent import AgentDefinition


def load_agent(path: Path) -> AgentDefinition:
    """Load and validate a single agent definition from a TOML file.

    Raises FileNotFoundError before attempting to open so callers get a clear
    message rather than a cryptic OS error. Raises ValueError on schema
    violations so the caller can decide to skip or abort.
    """
    if not path.exists():
        raise FileNotFoundError(f"Agent file not found: {path}")

    with open(path, "rb") as f:
        data = tomllib.load(f)

    try:
        return AgentDefinition(**data)
    except Exception as e:
        raise ValueError(f"Invalid agent definition in {path}: {e}") from e


def load_all_agents(directory: Path) -> list[AgentDefinition]:
    """Load all valid agent definitions from a directory of TOML files.

    Invalid files are silently skipped — a broken agent definition should not
    prevent other agents from loading. Sorted by filename for deterministic
    ordering across runs.
    """
    agents: list[AgentDefinition] = []
    for path in sorted(directory.glob("*.toml")):
        try:
            agents.append(load_agent(path))
        except ValueError:
            continue
    return agents
