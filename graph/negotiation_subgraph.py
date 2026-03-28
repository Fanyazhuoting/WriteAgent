"""
Negotiation subgraph — invoked when ConsistencyChecker detects contradictions.

Flow:
  1. Build entity context (permanent facts) from DB
  2. Ask revision agent to fix contradictions with entity context provided
  3. ConsistencyChecker re-checks revised draft
  4. Loop up to MAX_NEGOTIATION_ROUNDS; proceed to narrative regardless of outcome
"""
from __future__ import annotations

from datetime import datetime, timezone
from config.settings import settings
from agents.consistency_checker import ConsistencyChecker
from memory.entity_store import list_entities
from utils.llm_client import chat_completion


_checker = ConsistencyChecker()


def _build_entity_context(novel_id: str) -> str:
    """Build a concise summary of permanent entity facts for the revision prompt."""
    entities = list_entities(novel_id)
    if not entities:
        return "(no entities stored)"
    lines = []
    for e in entities:
        lines.append(f"- [{e.entity_type.upper()}] {e.name}: {e.description}")
    return "\n".join(lines)


def _format_contradictions(contradictions: list[dict]) -> str:
    lines = []
    for c in contradictions:
        lines.append(
            f"- {c.get('field', '?')}: stored='{c.get('stored_value', '?')}' "
            f"vs draft='{c.get('new_value', '?')}' (severity: {c.get('severity', '?')})"
        )
    return "\n".join(lines) or "(none)"


def _request_revision(draft: str, contradictions: list[dict], entity_context: str) -> str:
    """Ask the LLM to revise the draft to fix contradictions, given the correct entity facts."""
    contradiction_text = _format_contradictions(contradictions)
    messages = [
        {
            "role": "system",
            "content": (
                "You are a scene revision agent. Your job is to fix factual contradictions "
                "in a scene draft by aligning it with the established entity facts below. "
                "Make the minimum changes necessary. Preserve the narrative intent. "
                "Return only the revised scene prose."
            ),
        },
        {
            "role": "user",
            "content": (
                f"## Established Entity Facts (source of truth)\n{entity_context}\n\n"
                f"## Contradictions to Fix\n{contradiction_text}\n\n"
                f"## Original Draft\n{draft}\n\n"
                "Produce the revised draft that corrects the contradictions above:"
            ),
        },
    ]
    return chat_completion(messages)


def run_negotiation(state: dict) -> dict:
    """
    Run the negotiation loop synchronously.

    Returns a partial state update with:
        raw_scene_draft, negotiation_log, negotiation_round, negotiation_resolved
    """
    draft = state.get("raw_scene_draft", "")
    contradictions = state.get("contradictions", [])
    scene_number = state.get("current_scene_number", 0)
    novel_id = state.get("novel_id", "")
    max_rounds = settings.max_negotiation_rounds

    entity_context = _build_entity_context(novel_id)

    negotiation_log: list[dict] = []
    round_num = 0
    resolved = False

    while round_num < max_rounds and not resolved:
        round_num += 1
        ts = datetime.now(timezone.utc).isoformat()

        # Step 1: Request revision with entity context
        revised_draft = _request_revision(draft, contradictions, entity_context)

        # Step 2: ConsistencyChecker re-checks the revised draft
        check_state = dict(state)
        check_state["raw_scene_draft"] = revised_draft
        check_result = _checker.run(check_state)

        still_contradictions = check_result.get("has_contradiction", False)
        new_contradictions = check_result.get("contradictions", [])

        # Summarise what was changed without a full diff algorithm
        changes_made = [
            f"Corrected: {c.get('field', '?')}"
            for c in contradictions[:3]
        ]
        if len(contradictions) > 3:
            changes_made.append(f"...and {len(contradictions) - 3} more")

        negotiation_log.append({
            "scene_number": scene_number,
            "round_number": round_num,
            "agent": "revision_agent",
            "role": "reviser",
            "action": "revised",
            "participants": ["revision_agent", "consistency_checker"],
            "changes_made": changes_made,
            "contradictions": contradictions,
            "contradictions_before": len(contradictions),
            "contradictions_after": new_contradictions,
            "contradictions_found": len(new_contradictions),
            "resolution": "resolved" if not still_contradictions else "pending",
            "resolved": not still_contradictions,
            "timestamp": ts,
        })

        draft = revised_draft
        if not still_contradictions:
            resolved = True
        else:
            contradictions = new_contradictions

    # Always proceed to narrative — unresolved contradictions are logged for review
    return {
        "raw_scene_draft": draft,
        "negotiation_log": negotiation_log,
        "negotiation_round": round_num,
        "negotiation_resolved": resolved,
    }
