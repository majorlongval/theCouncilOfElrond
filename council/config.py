import tomllib
from pathlib import Path

from pydantic import BaseModel


class ProjectConfig(BaseModel):
    """Project-level configuration from council.toml."""
    owner: str
    repo: str
    litellm_master_key: str


def load_project_config(path: Path) -> ProjectConfig:
    """Load project config from a TOML file.

    Reads [project] (owner, repo) and [litellm] (master_key) sections.
    Raises FileNotFoundError if the file does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "rb") as f:
        data = tomllib.load(f)

    return ProjectConfig(
        owner=data["project"]["owner"],
        repo=data["project"]["repo"],
        litellm_master_key=data["litellm"]["master_key"],
    )
