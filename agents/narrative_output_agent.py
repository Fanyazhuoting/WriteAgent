"""NarrativeOutputAgent — synthesises contributions into polished prose."""
from __future__ import annotations

from datetime import datetime, timezone

from .base_agent import BaseAgent
from memory.entity_store import archive_scene, upsert_entity, query_entities, list_entities
from memory.schemas import EntityDoc, SceneArchiveDoc
from memory.attribute_extractor import extract_core_attributes, extract_extended_attributes
from utils.token_counter import count_tokens
from utils.audit_logger import log_agent_call
from utils.llm_client import chat_completion
from prompts.registry import registry
from guardrails.security_mcp import security_mcp


def _extract_permanent_attrs_via_llm(name: str, full_description: str) -> str:
    """
    Fallback mini-call: when CharacterAgent did not provide new_character_permanent,
    ask the LLM to extract only permanent attributes from the full state_summary.
    This is a small, focused call — not a full agent invocation.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "Extract ONLY the permanent attributes of the character from the description below. "
                "Permanent attributes are: physical appearance (hair colour, eye colour, height, "
                "build, skin tone, distinguishing marks), species, gender, approximate age, "
                "core personality traits, and background that will not change between scenes. "
                "Do NOT include location, emotional state, current goals, or anything situational. "
                "Return plain text only, no JSON."
            ),
        },
        {
            "role": "user",
            "content": f"Character: {name}\nFull description: {full_description}",
        },
    ]
    try:
        return chat_completion(messages).strip()
    except Exception:
        return full_description  # last resort: use full description as-is


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

        # Build permanent profile summary so the LLM always knows character gender/identity.
        # Priority: core_attributes (structured) > raw description text.
        profile_lines: list[str] = []
        for name, profile in character_profiles_snapshot.items():
            core_attrs: dict = profile.get("core_attributes") or {}
            desc: str = profile.get("description") or ""
            # Build a concise one-liner of permanent facts, leading with gender if present
            parts: list[str] = []
            if core_attrs.get("gender"):
                parts.append(f"gender={core_attrs['gender']}")
            for key in ("species", "hair_color", "eye_color", "height"):
                if core_attrs.get(key):
                    parts.append(f"{key}={core_attrs[key]}")
            attr_str = "; ".join(parts)
            if attr_str:
                profile_lines.append(f"- {name}: [{attr_str}] {desc}".strip())
            elif desc:
                profile_lines.append(f"- {name}: {desc}")
        # Also include new characters appearing for the first time
        for name, perm_desc in new_character_permanent.items():
            if name not in character_profiles_snapshot:
                profile_lines.append(f"- {name} (new): {perm_desc}")
        character_profiles_str = "\n".join(profile_lines) or "(none)"

        prompt_data = registry.get(self.prompt_name)
        user_msg = prompt_data["user_template"].format(
            genre=genre,
            style_guide=style_guide,
            output_language=output_language,
            scene_draft=draft,
            character_profiles=character_profiles_str,
            character_states=char_summary,
            world_rules_context=world_rules_context or "(none)",
            scene_history="\n\n".join(scene_history[-2:]) or "(none)",
        )

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_msg},
        ]

        # Use security MCP for self-audit
        content, _ = self._call_llm(
            messages, 
            novel_id, 
            scene_number, 
            mcp=security_mcp
        )
        result = self._parse_json(content)

        final_prose = result.get("final_prose") or ""
        scene_summary = result.get("scene_summary", "")
        locations_mentioned: list = result.get("locations_mentioned") or []
        corrections_log: list = result.get("corrections_log") or []
        narrative_reasoning: dict = result.get("reasoning", {})

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
                            "event": "narrative_correction_applied",
                            "character_or_field": correction.get("character_or_field", "unknown"),
                            "draft_value": correction.get("draft_value", ""),
                            "scene_history_value": correction.get("scene_history_value", ""),
                            "chosen_value": correction.get("chosen_value", ""),
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
                    # Existing character: preserve permanent description and structured
                    # attribute dicts, update only the dynamic current_state.
                    profile = character_profiles_snapshot[name]
                    entity = EntityDoc(
                        entity_id=profile["entity_id"],
                        entity_type=profile["entity_type"],
                        name=profile["name"],
                        novel_id=profile["novel_id"],
                        description=profile["description"],          # permanent — never changed here
                        current_state=state_summary,                 # dynamic state updated
                        last_updated_scene=scene_number,
                        version=profile["version"] + 1,
                        tags=profile.get("tags", ""),
                        is_active=profile.get("is_active", True),
                        # Pass through structured attrs so upsert_entity preserves them
                        # (upsert_entity itself also guards against overwriting non-empty dicts,
                        # but being explicit here makes the intent clear).
                        core_attributes=profile.get("core_attributes", {}),
                        extended_attributes=profile.get("extended_attributes", {}),
                    )
                else:
                    # New character first appearing this scene.
                    # Use new_character_permanent for description so it contains ONLY permanent attributes.
                    permanent_attrs = new_character_permanent.get(name, "")
                    if not permanent_attrs:
                        # CharacterAgent did not provide permanent attrs (LLM non-compliance).
                        # Run a targeted mini-call to extract them rather than silently degrading.
                        permanent_attrs = _extract_permanent_attrs_via_llm(name, state_summary)
                        try:
                            log_agent_call(
                                novel_id=novel_id,
                                agent_id=self.agent_id,
                                scene_number=scene_number,
                                prompt_version="v1",
                                prompt="",
                                output="",
                                metadata={
                                    "event": "permanent_attrs_extracted_via_fallback",
                                    "character": name,
                                    "extracted": permanent_attrs,
                                    "detail": (
                                        f"new_character_permanent not provided for '{name}'; "
                                        f"ran mini-call to extract permanent attributes."
                                    ),
                                },
                            )
                        except Exception:
                            pass

                    # Extract structured attributes from the permanent description so
                    # ConsistencyChecker can use them from the next scene onward.
                    core_attrs = extract_core_attributes(permanent_attrs)
                    ext_attrs = extract_extended_attributes(genre, name, permanent_attrs, core_attrs)

                    entity = EntityDoc(
                        entity_type="character",
                        name=name,
                        novel_id=novel_id,
                        description=permanent_attrs,   # permanent only — embedded for semantic search
                        current_state=state_summary,   # dynamic state
                        last_updated_scene=scene_number,
                        core_attributes=core_attrs,
                        extended_attributes=ext_attrs,
                    )
                upsert_entity(entity)
            except Exception:
                pass

        return {
            "final_prose": final_prose,
            "prose_chunks": [final_prose],
            "scene_history": [final_prose],
            "narrative_reasoning": narrative_reasoning,
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
