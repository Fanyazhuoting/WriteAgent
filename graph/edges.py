"""Conditional edge routing for the LangGraph state machine."""
from __future__ import annotations

from .state import GraphState


def route_after_consistency(state: GraphState) -> str:
    """After ConsistencyChecker: negotiate if contradiction, else go to narrative."""
    if state.get("veto_active"):
        # WorldbuildingAgent already corrected draft during worldbuilding phase
        return "narrative"
    if state.get("has_contradiction"):
        return "negotiation"
    return "narrative"


def route_after_negotiation(state: GraphState) -> str:
    """After negotiation: go to narrative or pause for human review."""
    if state.get("awaiting_human"):
        return "human_review"
    return "narrative"


def route_after_human_review(state: GraphState) -> str:
    """After human review: proceed directly to narrative with the best available draft."""
    return "narrative"
