"""Tests for the prompt registry."""
import pytest
from pathlib import Path
import tempfile
import os
import yaml

from prompts.registry import PromptRegistry


@pytest.fixture
def temp_registry(tmp_path):
    """Create a minimal prompt registry in a temp directory."""
    v1 = tmp_path / "v1"
    v1.mkdir()
    prompt = {"system": "You are a test agent.", "user_template": "Hello {name}"}
    with open(v1 / "test_agent.yaml", "w") as f:
        yaml.dump(prompt, f)
    return PromptRegistry(prompts_dir=str(tmp_path), version="v1")


def test_get_system_prompt(temp_registry):
    system = temp_registry.get_system("test_agent")
    assert "test agent" in system


def test_get_full_prompt(temp_registry):
    data = temp_registry.get("test_agent")
    assert "system" in data
    assert "user_template" in data


def test_list_versions(temp_registry, tmp_path):
    v2 = tmp_path / "v2"
    v2.mkdir()
    with open(v2 / "test_agent.yaml", "w") as f:
        yaml.dump({"system": "v2 prompt"}, f)
    versions = temp_registry.list_versions("test_agent")
    assert "v1" in versions
    assert "v2" in versions


def test_missing_prompt_raises(temp_registry):
    with pytest.raises(FileNotFoundError):
        temp_registry.get("nonexistent_agent")


def test_reload_clears_cache(temp_registry, tmp_path):
    # Load once to cache
    temp_registry.get("test_agent")
    assert len(temp_registry._cache) == 1
    temp_registry.reload()
    assert len(temp_registry._cache) == 0
