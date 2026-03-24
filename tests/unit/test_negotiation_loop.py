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


def _wb_response(veto: bool = False) -> str:
    return json.dumps({
        "world_rules_context": "No magic without crystals.",
        "veto": veto,
        "veto_reason": "Magic used without crystals." if veto else None,
        "corrected_draft": "Elena used a crystal to cast the spell." if veto else None,
    })


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
    call_sequence = [
        _revision_response(),          # revision request
        _wb_response(veto=False),      # worldbuilding validation
        _checker_response(False),      # recheck passes
    ]
    with patch("agents.base_agent.chat_completion", side_effect=call_sequence), \
         patch("graph.negotiation_subgraph.chat_completion", return_value=_revision_response()):
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


def test_veto_exits_immediately():
    with patch("agents.base_agent.chat_completion", return_value=_wb_response(veto=True)), \
         patch("graph.negotiation_subgraph.chat_completion", return_value=_revision_response()):
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
        assert result["veto_active"] is True
        assert result["negotiation_resolved"] is True
