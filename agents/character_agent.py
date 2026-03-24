"""CharacterAgent — maintains per-character memory and state across scenes."""
from __future__ import annotations

from .base_agent import BaseAgent
from memory.entity_store import query_entities, upsert_entity
from memory.schemas import EntityDoc
from prompts.registry import registry


class CharacterAgent(BaseAgent):
    agent_id = "character_agent"
    prompt_name = "character"

    def run(self, state: dict) -> dict:
        novel_id = state["novel_id"]
        scene_number = state["current_scene_number"]
        scene_brief = state.get("current_scene_brief", "")
        draft = state.get("raw_scene_draft", "")
        scene_history = state.get("scene_history", [])

        # Fetch character entities from ChromaDB
        characters = query_entities(novel_id, scene_brief, entity_type="character", k=10)
        character_profiles = "\n\n".join(
            f"**{c.name}** (v{c.version}): {c.description}" for c in characters
        ) or "(no characters established yet)"

        characters_list = ", ".join(c.name for c in characters) or "(unknown)"

        prompt_data = registry.get(self.prompt_name)
        user_msg = prompt_data["user_template"].format(
            scene_brief=scene_brief,
            characters_list=characters_list,
            character_profiles=character_profiles,
            scene_history="\n\n".join(scene_history[-3:]) or "(none)",
            draft=draft or "(no draft yet)",
        )

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_msg},
        ]

        content, _ = self._call_llm(messages, novel_id, scene_number)
        result = self._parse_json(content)

        character_states: dict[str, str] = result.get("character_states", {})

        # Upsert updated states back to ChromaDB
        existing = {c.name: c for c in characters}
        for name, state_summary in character_states.items():
            if name in existing:
                entity = existing[name]
                entity.description = state_summary
                entity.version += 1
                entity.last_updated_scene = scene_number
            else:
                entity = EntityDoc(
                    entity_type="character",
                    name=name,
                    novel_id=novel_id,
                    description=state_summary,
                    last_updated_scene=scene_number,
                )
            upsert_entity(entity)

        return {
            "character_states": character_states,
            "agent_messages": [{
                "agent_id": self.agent_id,
                "content": content,
                "timestamp": "",
                "prompt_version": "v1",
                "token_count": 0,
            }],
        }
