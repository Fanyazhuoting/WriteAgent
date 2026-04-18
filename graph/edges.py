"""Conditional edge routing for the LangGraph state machine."""
from __future__ import annotations

from .state import GraphState


def route_after_worldbuilding(state: GraphState) -> str:
    """After Worldbuilding: stop if unsafe, else go to character."""
    if not state.get("is_safe", True):
        return "end"
    return "character"


def route_after_consistency(state: GraphState) -> str:
    """After ConsistencyChecker: negotiate if contradiction, else go to narrative."""
    if state.get("has_contradiction"):
        return "negotiation"
    return "narrative"
