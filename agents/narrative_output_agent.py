"""NarrativeOutputAgent — synthesises contributions into polished prose."""
from __future__ import annotations

from datetime import datetime, timezone

from .base_agent import BaseAgent
from memory.entity_store import archive_scene, upsert_entity, query_entities, list_entities
from memory.schemas import EntityDoc, SceneArchiveDoc
from utils.token_counter import count_tokens
from utils.audit_logger import log_agent_call
from prompts.registry import registry


class NarrativeOutputAgent(BaseAgent):
    agent_id = "narrative_output_agent"
    prompt_name = "narrative_output"

    def run(self, state: dict) -> dict:
        novel_id = state["novel_id"]
        scene_number = state["current_scene_number"]
        genre = state.get("genre", "")
        style_guide = state.get("style_guide", "")
        output_language = state.get("output_language", "English")
        draft = state.get("raw_scene_draft", "")
        character_states = state.get("character_states", {})
        character_profiles_snapshot = state.get("character_profiles_snapshot", {})
        new_character_permanent = state.get("new_character_permanent", {})
        world_rules_context = state.get("world_rules_context", "")
        scene_history = state.get("scene_history", [])

        char_summary = "\n".join(
            f"- {name}: {summary}" for name, summary in character_states.items()
        ) or "(none)"

        prompt_data = registry.get(self.prompt_name)
        user_msg = prompt_data["user_template"].format(
            genre=genre,
            style_guide=style_guide,
            output_language=output_language,
            scene_draft=draft,
            character_states=char_summary,
            world_rules_context=world_rules_context or "(none)",
            scene_history="\n\n".join(scene_history[-2:]) or "(none)",
        )

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_msg},
        ]

        content, _ = self._call_llm(messages, novel_id, scene_number)
        result = self._parse_json(content)

        final_prose = result.get("final_prose") or ""
        scene_summary = result.get("scene_summary", "")
        locations_mentioned: list = result.get("locations_mentioned") or []
        corrections_log: list = result.get("corrections_log") or []

        # Fallback: if JSON parsing failed or final_prose is empty, try regex extraction
        if not final_prose:
            import re
            m = re.search(
                r'"final_prose"\s*:\s*"((?:[^"\\]|\\.)*)"',
                content,
                re.DOTALL,
            )
            if m:
                try:
                    final_prose = m.group(1).encode('raw_unicode_escape').decode('unicode_escape')
                except Exception:
                    final_prose = m.group(1).replace('\\n', '\n').replace('\\"', '"')
            else:
                final_prose = content

        # Safety: if prose still starts with '{' it's raw JSON — strip the wrapper
        stripped = final_prose.strip()
        if stripped.startswith('{'):
            import json as _json
            try:
                inner = _json.loads(stripped)
                if isinstance(inner.get("final_prose"), str):
                    final_prose = inner["final_prose"]
                    if not scene_summary:
                        scene_summary = inner.get("scene_summary", "")
                    if not corrections_log:
                        corrections_log = inner.get("corrections_log") or []
            except Exception:
                pass

        if not scene_summary:
            scene_summary = final_prose[:500]

        # Audit-log any discrepancies the LLM noticed between scene_history and the draft.
        # These entries make the formerly-silent corrections visible in the audit trail.
        if corrections_log:
            for correction in corrections_log:
                try:
                    log_agent_call(
                        novel_id=novel_id,
                        agent_id=self.agent_id,
                        scene_number=scene_number,
                        prompt_version="v1",
                        prompt="",
                        output="",
                        metadata={
                            "event": "narrative_correction_warning",
                            "character_or_field": correction.get("character_or_field", "unknown"),
                            "scene_history_value": correction.get("scene_history_value", ""),
                            "draft_value": correction.get("draft_value", ""),
                            "note": correction.get("note", ""),
                        },
                    )
                except Exception:
                    pass

        # Upsert location entities extracted by the LLM into ChromaDB
        if locations_mentioned and isinstance(locations_mentioned, list):
            try:
                existing_locs = query_entities(novel_id, " ".join(locations_mentioned),
                                               entity_type="location", k=50)
                existing_names = {e.name.lower() for e in existing_locs}
            except Exception:
                existing_names = set()

            for loc_name in locations_mentioned:
                if not isinstance(loc_name, str) or not loc_name.strip():
                    continue
                loc_name = loc_name.strip()
                if loc_name.lower() in existing_names:
                    continue
                entity = EntityDoc(
                    entity_type="location",
                    name=loc_name,
                    novel_id=novel_id,
                    description=f"Location mentioned in scene {scene_number}.",
                    last_updated_scene=scene_number,
                )
                try:
                    upsert_entity(entity)
                    existing_names.add(loc_name.lower())
                except Exception:
                    pass

        # Archive the scene to ChromaDB (cold storage)
        archive_doc = SceneArchiveDoc(
            novel_id=novel_id,
            scene_number=scene_number,
            summary=scene_summary,
            characters_present=", ".join(character_states.keys()),
            location=self._extract_location(scene_summary),
            plot_events="[]",
            timestamp=datetime.now(timezone.utc).isoformat(),
            token_count=count_tokens(scene_summary),
        )
        try:
            archive_scene(archive_doc)
        except Exception:
            pass

        # Commit finalised character states to DB now that the scene is approved.
        # Permanent attributes are never overwritten — only current_state is updated.
        for name, state_summary in character_states.items():
            try:
                if name in character_profiles_snapshot:
                    # Existing character: preserve permanent description, update dynamic state
                    profile = character_profiles_snapshot[name]
                    entity = EntityDoc(
                        entity_id=profile["entity_id"],
                        entity_type=profile["entity_type"],
                        name=profile["name"],
                        novel_id=profile["novel_id"],
                        description=profile["description"],   # permanent — never changed here
                        current_state=state_summary,          # dynamic state updated
                        last_updated_scene=scene_number,
                        version=profile["version"] + 1,
                        tags=profile.get("tags", ""),
                        is_active=profile.get("is_active", True),
                    )
                else:
                    # New character first appearing this scene.
                    # Use new_character_permanent for description so it contains ONLY
                    # permanent attributes — not the dynamic state_summary.
                    permanent_attrs = new_character_permanent.get(name, "")
                    if not permanent_attrs:
                        # Fallback: CharacterAgent did not provide permanent attrs.
                        # Log a warning and degrade gracefully — state_summary becomes description.
                        permanent_attrs = state_summary
                        try:
                            log_agent_call(
                                novel_id=novel_id,
                                agent_id=self.agent_id,
                                scene_number=scene_number,
                                prompt_version="v1",
                                prompt="",
                                output="",
                                metadata={
                                    "event": "missing_permanent_attrs",
                                    "character": name,
                                    "detail": (
                                        f"new_character_permanent not provided for '{name}'; "
                                        f"fell back to state_summary as description. "
                                        f"Permanent attributes may be contaminated with dynamic state."
                                    ),
                                },
                            )
                        except Exception:
                            pass

                    entity = EntityDoc(
                        entity_type="character",
                        name=name,
                        novel_id=novel_id,
                        description=permanent_attrs,   # permanent only — embedded for semantic search
                        current_state=state_summary,   # dynamic state
                        last_updated_scene=scene_number,
                    )
                upsert_entity(entity)
            except Exception:
                pass

        return {
            "final_prose": final_prose,
            "prose_chunks": [final_prose],
            "scene_history": [final_prose],
            "agent_messages": [{
                "agent_id": self.agent_id,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "prompt_version": "v1",
                "token_count": count_tokens(final_prose),
                "corrections_log": corrections_log,
            }],
        }

    @staticmethod
    def _extract_location(summary: str) -> str:
        """Best-effort location extraction from scene summary."""
        lower = summary.lower()
        for keyword in ("in the", "at the", "inside", "outside", "on the"):
            idx = lower.find(keyword)
            if idx != -1:
                snippet = summary[idx: idx + 40].split(".")[0].strip()
                return snippet
        return "unknown"
