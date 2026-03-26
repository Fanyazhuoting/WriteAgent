"""CharacterAgent — maintains per-character memory and state across scenes."""
from __future__ import annotations

from .base_agent import BaseAgent
from memory.entity_store import query_entities
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

        # Build profile display: show permanent attributes + last known dynamic state
        profile_parts = []
        for c in characters:
            entry = f"**{c.name}** (v{c.version}): {c.description}"
            if c.current_state:
                entry += f"\n  [Last known state] {c.current_state}"
            profile_parts.append(entry)
        character_profiles = "\n\n".join(profile_parts) or "(no characters established yet)"
        characters_list = ", ".join(c.name for c in characters) or "(unknown)"

        # Build snapshot dict: permanent entity metadata keyed by name for downstream upsert
        # NOTE: this does NOT get written to DB here — NarrativeOutputAgent commits after finalization
        character_profiles_snapshot: dict[str, dict] = {
            c.name: {
                "entity_id": c.entity_id,
                "entity_type": c.entity_type,
                "name": c.name,
                "novel_id": c.novel_id,
                "description": c.description,        # permanent — never overwritten here
                "current_state": c.current_state,
                "version": c.version,
                "last_updated_scene": c.last_updated_scene,
                "tags": c.tags,
                "is_active": c.is_active,
                # Carry structured attribute dicts through to NarrativeOutputAgent
                # so they are preserved on the upsert that follows scene finalisation.
                "core_attributes": c.core_attributes,
                "extended_attributes": c.extended_attributes,
            }
            for c in characters
        }

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
        # Only populated for characters NOT already in character_profiles_snapshot
        new_character_permanent: dict[str, str] = result.get("new_character_permanent", {})

        # No DB writes here — NarrativeOutputAgent commits finalized states after prose is approved
        return {
            "character_states": character_states,
            "character_profiles_snapshot": character_profiles_snapshot,
            "new_character_permanent": new_character_permanent,
            "agent_messages": [{
                "agent_id": self.agent_id,
                "content": content,
                "timestamp": "",
                "prompt_version": "v1",
                "token_count": 0,
            }],
        }
