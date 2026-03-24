from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from council.__main__ import run_config


def test_config_generates_litellm_yaml(tmp_path):
    # Create agent TOML
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "gimli.toml").write_text("""
name = "Gimli"
role = "Builder"
brain = "gemini/gemini-flash-latest"
prompt = "You are Gimli."
tools = ["github.list_issues"]
artifacts = []

[trigger]
type = "telegram"
command = "/run gimli"

[reply]
type = "telegram"
""")

    # Create project config
    config_file = tmp_path / "council.toml"
    config_file.write_text("""
[project]
owner = "majorlongval"
repo = "theCouncilOfElrond"

[litellm]
master_key = "sk-test"
""")

    output_file = tmp_path / "litellm_config.yaml"

    run_config(
        agents_dir=agents_dir,
        config_path=config_file,
        output_path=output_file,
    )

    assert output_file.exists()
    parsed = yaml.safe_load(output_file.read_text())
    assert len(parsed["model_list"]) == 1
    assert parsed["model_list"][0]["model_name"] == "gemini/gemini-flash-latest"
    assert parsed["general_settings"]["master_key"] == "sk-test"
