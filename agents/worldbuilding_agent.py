"""WorldbuildingAgent — establishes world rules and holds veto power."""
from __future__ import annotations

from .base_agent import BaseAgent
from memory.entity_store import get_world_rules
from memory.retrieval import build_context_for_agent
from prompts.registry import registry


class WorldbuildingAgent(BaseAgent):
    agent_id = "worldbuilding_agent"
    prompt_name = "worldbuilding"

    def run(self, state: dict) -> dict:
        novel_id = state["novel_id"]
        scene_number = state["current_scene_number"]
        scene_brief = state.get("current_scene_brief", "")
        draft = state.get("raw_scene_draft", "")
        genre = state.get("genre", "")
        style_guide = state.get("style_guide", "")
        scene_history = state.get("scene_history", [])

        # Fetch world rules for context
        rules = get_world_rules(novel_id)
        world_rules_text = "\n".join(
            f"[{r.severity.upper()}][{r.category}] {r.description}" for r in rules
        ) or "(none established yet)"

        prompt_data = registry.get(self.prompt_name)
        user_msg = prompt_data["user_template"].format(
            genre=genre,
            style_guide=style_guide,
            world_rules=world_rules_text,
            scene_brief=scene_brief,
            draft=draft or "(no draft yet)",
        )

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_msg},
        ]

        content, _ = self._call_llm(messages, novel_id, scene_number)
        result = self._parse_json(content)

        veto_active = bool(result.get("veto", False))
        corrected_draft = result.get("corrected_draft") or draft

        update: dict = {
            "world_rules_context": result.get("world_rules_context", ""),
            "veto_active": veto_active,
            "agent_messages": [{
                "agent_id": self.agent_id,
                "content": content,
                "timestamp": "",
                "prompt_version": "v1",
                "token_count": 0,
            }],
        }

        if veto_active and corrected_draft:
            update["raw_scene_draft"] = corrected_draft
            update["negotiation_log"] = [{
                "round_number": 0,
                "participants": [self.agent_id],
                "proposal": corrected_draft,
                "counter_proposal": None,
                "resolution": f"VETO: {result.get('veto_reason', '')}",
                "resolved": True,
            }]

        return update
