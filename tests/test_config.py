from pathlib import Path

import pytest

from council.config import load_project_config, ProjectConfig


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_project_config(tmp_path):
    config_file = tmp_path / "council.toml"
    config_file.write_text("""
[project]
owner = "majorlongval"
repo = "theCouncilOfElrond"

[litellm]
master_key = "sk-test"
""")
    config = load_project_config(config_file)
    assert config.owner == "majorlongval"
    assert config.repo == "theCouncilOfElrond"
    assert config.litellm_master_key == "sk-test"


def test_project_config_not_found():
    with pytest.raises(FileNotFoundError):
        load_project_config(Path("/nonexistent/council.toml"))
