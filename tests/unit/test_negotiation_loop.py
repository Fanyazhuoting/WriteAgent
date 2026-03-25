"""Unit tests for the negotiation subgraph (mocks all LLM calls)."""
import pytest
from unittest.mock import patch
import json


@pytest.fixture(autouse=True)
def isolated_chroma(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    import memory.chroma_client as cc
    cc._client = None
    yield
    cc._client = None


def _checker_response(has_contradiction: bool) -> str:
    return json.dumps({
        "has_contradiction": has_contradiction,
        "contradictions": [] if not has_contradiction else [{
            "field": "character.Elena.location",
            "stored_value": "city",
            "new_value": "forest",
            "severity": "minor",
        }],
    })


def _revision_response() -> str:
    return "Elena walked carefully through the city streets."


def test_negotiation_resolves_in_one_round():
    with patch("graph.negotiation_subgraph.chat_completion", return_value=_revision_response()), \
         patch("agents.base_agent.chat_completion", return_value=_checker_response(False)):
        from graph.negotiation_subgraph import run_negotiation
        state = {
            "novel_id": "test-001",
            "current_scene_number": 2,
            "current_scene_brief": "Elena in the forest",
            "raw_scene_draft": "Elena ran through the forest.",
            "scene_history": [],
            "contradictions": [{"field": "character.Elena.location", "stored_value": "city", "new_value": "forest", "severity": "minor"}],
            "genre": "Fantasy",
            "style_guide": "Literary",
            "world_rules_context": "",
            "character_states": {},
            "plot_events": [],
            "negotiation_round": 0,
        }
        result = run_negotiation(state)
        assert result["negotiation_resolved"] is True
        assert result["negotiation_round"] >= 1


def test_negotiation_proceeds_to_narrative_when_unresolved():
    """Even if contradictions persist, negotiation always proceeds (no veto/human_review)."""
    with patch("graph.negotiation_subgraph.chat_completion", return_value=_revision_response()), \
         patch("agents.base_agent.chat_completion", return_value=_checker_response(True)):
        from graph.negotiation_subgraph import run_negotiation
        state = {
            "novel_id": "test-001",
            "current_scene_number": 3,
            "current_scene_brief": "Elena casts a spell",
            "raw_scene_draft": "Elena cast a fireball without any crystal.",
            "scene_history": [],
            "contradictions": [{"field": "magic_system", "stored_value": "requires crystal", "new_value": "no crystal used", "severity": "critical"}],
            "genre": "Fantasy",
            "style_guide": "Literary",
            "world_rules_context": "Magic requires crystals.",
            "character_states": {},
            "plot_events": [],
            "negotiation_round": 0,
        }
        result = run_negotiation(state)
        # Should always return a draft and log — never block
        assert "raw_scene_draft" in result
        assert "negotiation_log" in result
        assert "veto_active" not in result
        assert "awaiting_human" not in result
