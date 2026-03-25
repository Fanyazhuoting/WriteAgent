"""ConsistencyChecker — detects contradictions and initiates negotiation."""
from __future__ import annotations

from datetime import datetime, timezone

from .base_agent import BaseAgent
from memory.entity_store import list_entities, get_world_rules
from prompts.registry import registry


class ConsistencyChecker(BaseAgent):
    agent_id = "consistency_checker"
    prompt_name = "consistency_checker"

    def run(self, state: dict) -> dict:
        novel_id = state["novel_id"]
        scene_number = state["current_scene_number"]
        draft = state.get("raw_scene_draft", "")
        scene_history = state.get("scene_history", [])

        # Get ALL entities — full list ensures no entity is missed
        entities = list_entities(novel_id)
        if entities:
            entity_lines = []
            for e in entities:
                line = f"[{e.entity_type.upper()}] {e.name}\n  PERMANENT: {e.description}"
                if e.current_state:
                    line += f"\n  LAST STATE (context only, may change naturally): {e.current_state}"
                entity_lines.append(line)
            entity_snapshot = "\n\n".join(entity_lines)
        else:
            entity_snapshot = "(no entities stored yet)"

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

        # Round 0: initial detection entry
        detection_entry = {
            "scene_number": scene_number,
            "round_number": 0,
            "contradictions": contradictions,
            "resolution": "contradictions_found" if has_contradiction else "clean",
            "resolved": not has_contradiction,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "has_contradiction": has_contradiction,
            "contradictions": contradictions,
            "negotiation_log": [detection_entry],
            "agent_messages": [{
                "agent_id": self.agent_id,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "prompt_version": "v1",
                "token_count": 0,
            }],
        }
