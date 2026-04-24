"""Agent output schema conformance tests (mocked LLM, no real calls)."""
import json
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def isolated_chroma(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    import memory.chroma_client as cc
    cc._client = None
    yield
    cc._client = None


MINIMAL_STATE = {
    "novel_id": "eval-001",
    "current_scene_number": 1,
    "current_scene_brief": "Elena finds a map in the attic.",
    "raw_scene_draft": "Elena unrolled the ancient map, fingers trembling.",
    "genre": "Fantasy",
    "style_guide": "Literary fiction",
    "output_language": "English",
    "scene_history": [],
    "world_rules_context": "Magic requires crystals.",
    "character_states": {"Elena": "In the attic, excited."},
    "character_profiles_snapshot": {},
    "new_character_permanent": {},
    "plot_events": ["Found map"],
    "human_injection": None,
}


def _mock_response(data: dict) -> str:
    return json.dumps(data)


class TestConsistencyOutputSchema:
    def test_consistency_output_keys(self):
        resp = _mock_response({"has_contradiction": False, "contradictions": []})
        with patch("agents.base_agent.chat_completion", return_value=resp):
            from agents.consistency_checker import ConsistencyChecker
            result = ConsistencyChecker().run(MINIMAL_STATE)
        assert "has_contradiction" in result
        assert "contradictions" in result
        assert "negotiation_log" in result
        assert isinstance(result["contradictions"], list)
        assert isinstance(result["negotiation_log"], list)


class TestWorldbuilderOutputSchema:
    def test_worldbuilder_output_keys(self):
        resp = _mock_response({
            "world_rules_context": "No magic without crystals.",
            "veto": False,
            "veto_reason": None,
            "corrected_draft": None,
        })
        with patch("agents.base_agent.chat_completion", return_value=resp):
            from agents.worldbuilding_agent import WorldbuildingAgent
            result = WorldbuildingAgent().run(MINIMAL_STATE)
        assert "world_rules_context" in result
        assert "is_safe" in result
        assert "agent_messages" in result


class TestPlotAgentOutputSchema:
    def test_plot_agent_output_keys(self):
        resp = _mock_response({
            "scene_draft": "Elena unrolled the map.",
            "plot_events": ["Found map"],
            "new_subplot": None,
            "pacing_note": "rising action",
        })
        with patch("agents.base_agent.chat_completion", return_value=resp):
            from agents.plot_agent import PlotAgent
            result = PlotAgent().run(MINIMAL_STATE)
        assert "raw_scene_draft" in result
        assert "plot_events" in result
        assert "agent_messages" in result
        assert isinstance(result["plot_events"], list)


class TestNarrativeOutputSchema:
    def test_narrative_output_keys(self):
        resp = _mock_response({
            "final_prose": "Elena unrolled the ancient map with trembling fingers.",
            "scene_summary": "Elena finds a glowing map.",
        })
        with patch("agents.base_agent.chat_completion", return_value=resp):
            from agents.narrative_output_agent import NarrativeOutputAgent
            result = NarrativeOutputAgent().run(MINIMAL_STATE)
        assert "final_prose" in result
        assert "scene_history" in result
        assert "agent_messages" in result
        assert isinstance(result["final_prose"], str)
