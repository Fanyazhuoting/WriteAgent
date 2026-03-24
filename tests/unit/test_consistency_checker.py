"""Unit tests for ConsistencyChecker (mocks the LLM call)."""
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def isolated_chroma(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    import memory.chroma_client as cc
    cc._client = None
    yield
    cc._client = None


def _make_llm_response(has_contradiction: bool, contradictions: list) -> str:
    import json
    return json.dumps({
        "has_contradiction": has_contradiction,
        "contradictions": contradictions,
    })


def test_no_contradiction_detected():
    with patch("agents.base_agent.chat_completion", return_value=_make_llm_response(False, [])):
        from agents.consistency_checker import ConsistencyChecker
        checker = ConsistencyChecker()
        state = {
            "novel_id": "test-001",
            "current_scene_number": 1,
            "current_scene_brief": "Elena walks in the forest",
            "raw_scene_draft": "Elena walked carefully through the silvery trees.",
            "scene_history": [],
        }
        result = checker.run(state)
        assert result["has_contradiction"] is False
        assert result["contradictions"] == []


def test_contradiction_detected():
    contradiction = {
        "field": "character.Elena.hair_color",
        "stored_value": "black",
        "new_value": "blonde",
        "severity": "minor",
    }
    with patch("agents.base_agent.chat_completion", return_value=_make_llm_response(True, [contradiction])):
        from agents.consistency_checker import ConsistencyChecker
        checker = ConsistencyChecker()
        state = {
            "novel_id": "test-001",
            "current_scene_number": 2,
            "current_scene_brief": "Elena meets Marcus",
            "raw_scene_draft": "Elena's blonde hair caught the light.",
            "scene_history": ["Scene 1 prose here."],
        }
        result = checker.run(state)
        assert result["has_contradiction"] is True
        assert len(result["contradictions"]) == 1
        assert result["contradictions"][0]["field"] == "character.Elena.hair_color"
