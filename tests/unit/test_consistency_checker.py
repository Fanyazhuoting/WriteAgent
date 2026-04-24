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


# ---------------------------------------------------------------------------
# Deterministic pre-scan tests (no LLM, no DB)
# ---------------------------------------------------------------------------

class TestPrescanPhysicalAttributes:
    """Verify _pre_check_physical_attributes catches obvious colour flips."""

    @pytest.fixture
    def gold_entities(self):
        from memory.schemas import EntityDoc
        return [
            EntityDoc(
                entity_type="character", name="Elena", novel_id="test-001",
                description="A young archivist with black hair and green eyes.",
                core_attributes={"hair_color": "black", "eye_color": "green"},
            ),
            EntityDoc(
                entity_type="character", name="Marcus", novel_id="test-001",
                description="A tall mercenary with brown hair and blue eyes.",
                core_attributes={"hair_color": "brown", "eye_color": "blue"},
            ),
        ]

    def test_prescan_catches_hair_color_flip(self, gold_entities):
        from agents.consistency_checker import _pre_check_physical_attributes
        draft = "Elena brushed her blonde hair away from her face."
        hints = _pre_check_physical_attributes(gold_entities, draft)
        hair_hints = [h for h in hints if h.attribute == "hair_color" and h.character == "Elena"]
        assert len(hair_hints) == 1
        assert hair_hints[0].stored_value == "black"
        assert hair_hints[0].draft_value == "blonde"

    def test_prescan_catches_eye_color_flip(self, gold_entities):
        from agents.consistency_checker import _pre_check_physical_attributes
        draft = "Marcus stared with his brown eyes narrowed."
        hints = _pre_check_physical_attributes(gold_entities, draft)
        eye_hints = [h for h in hints if h.attribute == "eye_color" and h.character == "Marcus"]
        assert len(eye_hints) == 1
        assert eye_hints[0].stored_value == "blue"
        assert eye_hints[0].draft_value == "brown"

    def test_prescan_no_false_positive_on_clean_draft(self, gold_entities):
        from agents.consistency_checker import _pre_check_physical_attributes
        draft = (
            "Elena's black hair caught the moonlight as she turned. "
            "Marcus watched with his blue eyes."
        )
        hints = _pre_check_physical_attributes(gold_entities, draft)
        assert len(hints) == 0
