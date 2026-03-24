"""
Negotiation subgraph — invoked when ConsistencyChecker detects contradictions.

Flow:
  1. Present contradictions to the flagged/plot agent for a revision proposal
  2. WorldbuildingAgent validates; if absolute-rule violation → VETO and done
  3. ConsistencyChecker re-checks revised draft
  4. Loop up to MAX_NEGOTIATION_ROUNDS; escalate to human if unresolved
"""
from __future__ import annotations

from datetime import datetime, timezone
from config.settings import settings
from config.constants import NEGOTIATION_VETO_LABEL
from agents.worldbuilding_agent import WorldbuildingAgent
from agents.consistency_checker import ConsistencyChecker
from utils.llm_client import chat_completion


_worldbuilding = WorldbuildingAgent()
_checker = ConsistencyChecker()


def _format_contradictions(contradictions: list[dict]) -> str:
    lines = []
    for c in contradictions:
        lines.append(
            f"- Field: {c.get('field', '?')} | "
            f"Stored: {c.get('stored_value', '?')} | "
            f"Draft: {c.get('new_value', '?')} | "
            f"Severity: {c.get('severity', '?')}"
        )
    return "\n".join(lines) or "(none)"


def _request_revision(draft: str, contradictions: list[dict], state: dict) -> str:
    """Ask the LLM (as PlotAgent) to revise the draft to fix contradictions."""
    contradiction_text = _format_contradictions(contradictions)
    messages = [
        {
            "role": "system",
            "content": (
                "You are the Plot Agent revising a scene draft to resolve factual contradictions. "
                "Make the minimum changes necessary to fix the contradictions listed. "
                "Preserve the narrative intent. Return only the revised scene prose."
            ),
        },
        {
            "role": "user",
            "content": (
                f"## Original Draft\n{draft}\n\n"
                f"## Contradictions to Fix\n{contradiction_text}\n\n"
                "Produce the revised draft:"
            ),
        },
    ]
    return chat_completion(messages)


def run_negotiation(state: dict) -> dict:
    """
    Run the negotiation loop synchronously.

    Modifies and returns a partial state update with:
        raw_scene_draft, negotiation_log, negotiation_round,
        negotiation_resolved, veto_active, awaiting_human
    """
    draft = state.get("raw_scene_draft", "")
    contradictions = state.get("contradictions", [])
    max_rounds = settings.max_negotiation_rounds

    negotiation_log: list[dict] = []
    round_num = 0
    resolved = False
    veto_active = False
    awaiting_human = False

    while round_num < max_rounds and not resolved:
        round_num += 1
        ts = datetime.now(timezone.utc).isoformat()

        # Step 1: Request revision from plot agent
        revised_draft = _request_revision(draft, contradictions, state)

        # Step 2: WorldbuildingAgent validates
        wb_state = dict(state)
        wb_state["raw_scene_draft"] = revised_draft
        wb_result = _worldbuilding.run(wb_state)

        if wb_result.get("veto_active"):
            # Veto — worldbuilding agent corrected the draft
            corrected = wb_result.get("raw_scene_draft", revised_draft)
            negotiation_log.append({
                "round_number": round_num,
                "participants": ["plot_agent", "worldbuilding_agent"],
                "proposal": _format_contradictions(contradictions),
                "contradictions": contradictions,
                "counter_proposal": None,
                "resolution": NEGOTIATION_VETO_LABEL,
                "resolved": True,
                "timestamp": ts,
            })
            return {
                "raw_scene_draft": corrected,
                "negotiation_log": negotiation_log,
                "negotiation_round": round_num,
                "negotiation_resolved": True,
                "veto_active": True,
                "awaiting_human": False,
            }

        # Step 3: ConsistencyChecker re-checks
        check_state = dict(state)
        check_state["raw_scene_draft"] = revised_draft
        check_result = _checker.run(check_state)

        still_contradictions = check_result.get("has_contradiction", False)
        new_contradictions = check_result.get("contradictions", [])

        negotiation_log.append({
            "round_number": round_num,
            "participants": ["plot_agent", "consistency_checker", "worldbuilding_agent"],
            "proposal": _format_contradictions(contradictions),
            "contradictions": contradictions,
            "counter_proposal": None,
            "resolution": "resolved" if not still_contradictions else "pending",
            "resolved": not still_contradictions,
            "timestamp": ts,
        })

        if not still_contradictions:
            draft = revised_draft
            resolved = True
        else:
            draft = revised_draft
            contradictions = new_contradictions

    if not resolved:
        awaiting_human = True

    return {
        "raw_scene_draft": draft,
        "negotiation_log": negotiation_log,
        "negotiation_round": round_num,
        "negotiation_resolved": resolved,
        "veto_active": False,
        "awaiting_human": awaiting_human,
    }
