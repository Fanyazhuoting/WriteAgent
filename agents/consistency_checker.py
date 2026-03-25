"""ConsistencyChecker — detects contradictions and initiates negotiation."""
from __future__ import annotations

from datetime import datetime, timezone

from .base_agent import BaseAgent
from memory.entity_store import get_world_rules
from memory.retrieval import get_entity_snapshot
from prompts.registry import registry


class ConsistencyChecker(BaseAgent):
    agent_id = "consistency_checker"
    prompt_name = "consistency_checker"

    def run(self, state: dict) -> dict:
        novel_id = state["novel_id"]
        scene_number = state["current_scene_number"]
        scene_brief = state.get("current_scene_brief", "")
        draft = state.get("raw_scene_draft", "")
        scene_history = state.get("scene_history", [])

        # Build entity snapshot from ChromaDB
        entity_snapshot = get_entity_snapshot(novel_id, scene_brief, k=12)

        # World rules for prompt
        rules = get_world_rules(novel_id)
        world_rules_text = "\n".join(
            f"[{r.severity.upper()}] {r.description}" for r in rules
        ) or "(none)"

        prompt_data = registry.get(self.prompt_name)
        user_msg = prompt_data["user_template"].format(
            draft=draft or "(no draft)",
            entity_snapshot=entity_snapshot,
            world_rules=world_rules_text,
            scene_history="\n\n".join(scene_history[-3:]) or "(none)",
        )

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_msg},
        ]

        content, _ = self._call_llm(messages, novel_id, scene_number)
        result = self._parse_json(content)

        has_contradiction = bool(result.get("has_contradiction", False))
        contradictions = result.get("contradictions", [])

        return {
            "has_contradiction": has_contradiction,
            "contradictions": contradictions,
            "agent_messages": [{
                "agent_id": self.agent_id,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "prompt_version": "v1",
                "token_count": 0,
            }],
        }

    def recheck(self, draft: str, state: dict) -> bool:
        """Re-run check on a revised draft. Returns True if clean."""
        temp_state = dict(state)
        temp_state["raw_scene_draft"] = draft
        result = self.run(temp_state)
        return not result.get("has_contradiction", False)
