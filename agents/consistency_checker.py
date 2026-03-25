"""ConsistencyChecker — detects contradictions and initiates negotiation."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import NamedTuple

from .base_agent import BaseAgent
from memory.entity_store import list_entities, get_world_rules
from memory.schemas import EntityDoc
from prompts.registry import registry


# ---------------------------------------------------------------------------
# Code-based physical attribute pre-scanner
# ---------------------------------------------------------------------------

class _AttributeHint(NamedTuple):
    character: str
    attribute: str
    stored_value: str
    draft_value: str


# Colour tokens for ZH and EN — extend this list as needed
_COLOURS_ZH = (
    "金色?|黑色?|棕色?|红色?|白色?|银色?|蓝色?|绿色?|紫色?|橙色?|粉色?|灰色?|褐色?|栗色?"
)
_COLOURS_EN = (
    r"golden|blond(?:e)?|black|brown|red|auburn|white|silver|"
    r"blue|green|purple|orange|pink|gr[ae]y|platinum"
)

# Match <colour> + optional connector + hair noun
_HAIR_ZH = re.compile(
    rf"({_COLOURS_ZH})[的]?(?:头发|发丝|发色|发型|长发|短发|卷发|直发)",
    re.IGNORECASE,
)
_HAIR_EN = re.compile(
    rf"\b({_COLOURS_EN})\b[\s-]*(?:hair|locks|tresses|curls|waves)",
    re.IGNORECASE,
)

# Eye colour
_EYE_ZH = re.compile(
    rf"({_COLOURS_ZH})[的]?(?:眼睛|眼眸|眼珠|眼神|双眸)",
    re.IGNORECASE,
)
_EYE_EN = re.compile(
    rf"\b({_COLOURS_EN})\b[\s-]*eyes?\b",
    re.IGNORECASE,
)


def _first_match(patterns: list[re.Pattern], text: str) -> str | None:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


def _pre_check_physical_attributes(
    entities: list[EntityDoc], draft: str
) -> list[_AttributeHint]:
    """
    Code-based scan for obvious physical attribute contradictions.

    Only flags when:
    1. The character's name appears in the draft (character is present in the scene).
    2. The permanent description contains a known physical descriptor.
    3. The draft contains a DIFFERENT value for the same descriptor.

    Returns a list of hints to be forwarded to the LLM for confirmation.
    Absence of an attribute in the draft is deliberately ignored (absence ≠ contradiction).
    """
    hints: list[_AttributeHint] = []
    for e in entities:
        if e.entity_type != "character":
            continue
        if e.name not in draft:
            continue  # character not mentioned in draft — skip

        # Hair colour
        stored_hair = _first_match([_HAIR_ZH, _HAIR_EN], e.description)
        if stored_hair:
            draft_hair = _first_match([_HAIR_ZH, _HAIR_EN], draft)
            if draft_hair and draft_hair.rstrip("色") != stored_hair.rstrip("色"):
                hints.append(_AttributeHint(
                    character=e.name,
                    attribute="hair_color",
                    stored_value=stored_hair,
                    draft_value=draft_hair,
                ))

        # Eye colour
        stored_eye = _first_match([_EYE_ZH, _EYE_EN], e.description)
        if stored_eye:
            draft_eye = _first_match([_EYE_ZH, _EYE_EN], draft)
            if draft_eye and draft_eye.rstrip("色") != stored_eye.rstrip("色"):
                hints.append(_AttributeHint(
                    character=e.name,
                    attribute="eye_color",
                    stored_value=stored_eye,
                    draft_value=draft_eye,
                ))

    return hints


def _format_hints(hints: list[_AttributeHint]) -> str:
    if not hints:
        return "(none)"
    lines = []
    for h in hints:
        lines.append(
            f"- [{h.character}] {h.attribute}: "
            f"PERMANENT='{h.stored_value}' vs draft='{h.draft_value}'"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ConsistencyChecker(BaseAgent):
    agent_id = "consistency_checker"
    prompt_name = "consistency_checker"

    def run(self, state: dict) -> dict:
        novel_id = state["novel_id"]
        scene_number = state["current_scene_number"]
        draft = state.get("raw_scene_draft", "")
        scene_history = state.get("scene_history", [])

        entities = list_entities(novel_id)

        # Code pre-scan: find obvious physical attribute conflicts before LLM call
        pre_scan_hints = _pre_check_physical_attributes(entities, draft)

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
            pre_scan_hints=_format_hints(pre_scan_hints),
        )

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_msg},
        ]

        content, _ = self._call_llm(messages, novel_id, scene_number)
        result = self._parse_json(content)

        has_contradiction = bool(result.get("has_contradiction", False))
        contradictions = result.get("contradictions", [])

        # If the code pre-scan found hints that the LLM did not flag, promote them.
        # This prevents LLM under-reporting from silently dropping confirmed code findings.
        llm_fields = {c.get("field", "") for c in contradictions}
        for hint in pre_scan_hints:
            hint_field = f"character.{hint.character}.{hint.attribute}"
            if hint_field not in llm_fields:
                contradictions.append({
                    "field": hint_field,
                    "stored_value": hint.stored_value,
                    "new_value": hint.draft_value,
                    "severity": "critical",
                    "tier": "1",
                    "source": "pre_scan",
                    "note": "Flagged by code pre-scan; not confirmed by LLM — verify before acting.",
                })
                has_contradiction = True

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
