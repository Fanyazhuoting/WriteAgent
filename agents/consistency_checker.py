"""ConsistencyChecker — detects contradictions and initiates negotiation."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

from .base_agent import BaseAgent
from memory.entity_store import list_entities, get_world_rules
from memory.schemas import EntityDoc
from memory.attribute_extractor import (
    PRESCAN_PATTERNS,
    _find_attributed_value,
    values_conflict,
)
from prompts.registry import registry


# ---------------------------------------------------------------------------
# Code-based physical attribute pre-scanner
# ---------------------------------------------------------------------------

class _AttributeHint(NamedTuple):
    character: str
    attribute: str
    stored_value: str
    draft_value: str


def _pre_check_physical_attributes(
    entities: list[EntityDoc], draft: str
) -> list[_AttributeHint]:
    """
    Deterministic scan for physical attribute contradictions using structured
    core_attributes stored on each EntityDoc.

    Algorithm per character
    -----------------------
    1. Skip if entity is not a character or name is absent from draft.
    2. Skip if core_attributes is empty (entity pre-dates this feature or has
       no extractable attributes — LLM layer handles verification in that case).
    3. For every key in core_attributes that belongs to PRESCAN_PATTERNS:
       a. Extract a text window around each mention of the character's name in
          the draft (avoids cross-character colour mis-attribution).
       b. Search the window text for the attribute using the registered pattern.
       c. If a different value is found, emit a hint.

    Only PRESCAN_PATTERNS keys are code-checked; extended_attributes keys are
    left entirely to the LLM layer which receives them in structured form.

    Absence of an attribute in the draft is not flagged (absence ≠ contradiction).
    """
    hints: list[_AttributeHint] = []

    for e in entities:
        if e.entity_type != "character":
            continue
        if e.name not in draft:
            continue
        if not e.core_attributes:
            # No structured attributes yet — LLM handles consistency for this entity
            continue

        for attr_key, stored_value in e.core_attributes.items():
            if attr_key not in PRESCAN_PATTERNS:
                # Non-colour or multi-value attribute — skip code scan, LLM verifies
                continue

            patterns = PRESCAN_PATTERNS[attr_key]
            # Use possessive-proximity search: only accept a colour match if
            # the character's name appears within PROXIMITY chars to the LEFT
            # of the match.  This eliminates cross-character false positives
            # regardless of sentence structure.
            draft_value = _find_attributed_value(e.name, patterns, draft)
            if draft_value and values_conflict(stored_value, draft_value):
                hints.append(_AttributeHint(
                    character=e.name,
                    attribute=attr_key,
                    stored_value=stored_value,
                    draft_value=draft_value,
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
                line = f"[{e.entity_type.upper()}] {e.name}"
                # Structured attributes are listed first so the LLM can spot
                # contradictions without having to parse free-form prose.
                if e.core_attributes:
                    attrs = "\n    ".join(
                        f"{k}: {v}" for k, v in e.core_attributes.items()
                    )
                    line += f"\n  CORE ATTRIBUTES:\n    {attrs}"
                if e.extended_attributes:
                    attrs = "\n    ".join(
                        f"{k}: {v}" for k, v in e.extended_attributes.items()
                    )
                    line += f"\n  EXTENDED ATTRIBUTES:\n    {attrs}"
                line += f"\n  PERMANENT DESCRIPTION: {e.description}"
                if e.current_state:
                    line += (
                        f"\n  LAST STATE (context only, may change naturally): "
                        f"{e.current_state}"
                    )
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
        consistency_reasoning = result.get("reasoning", {})

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
            "agent": "consistency_checker",
            "role": "detector",
            "action": "detected",
            "contradictions": contradictions,
            "contradictions_found": len(contradictions),
            "resolution": "contradictions_found" if has_contradiction else "clean",
            "resolved": not has_contradiction,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "has_contradiction": has_contradiction,
            "contradictions": contradictions,
            "consistency_reasoning": consistency_reasoning,
            "negotiation_log": [detection_entry],
            "agent_messages": [{
                "agent_id": self.agent_id,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "prompt_version": "v1",
                "token_count": 0,
            }],
        }
