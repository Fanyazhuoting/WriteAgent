"""NarrativeOutputAgent — synthesises contributions into polished prose."""
from __future__ import annotations

from datetime import datetime, timezone

from .base_agent import BaseAgent
from memory.entity_store import archive_scene, upsert_entity, query_entities
from memory.schemas import EntityDoc, SceneArchiveDoc
from utils.token_counter import count_tokens
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
                # Last resort: use raw content
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
            except Exception:
                pass

        if not scene_summary:
            scene_summary = final_prose[:500]

        # Upsert location entities extracted by the LLM into ChromaDB
        if locations_mentioned and isinstance(locations_mentioned, list):
            # Build a lookup of already-known locations for this novel to avoid duplicates
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
                    continue  # already stored — skip to avoid version churn
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
                    pass  # don't fail scene generation for a location upsert error

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
            pass  # don't fail if archive fails

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
