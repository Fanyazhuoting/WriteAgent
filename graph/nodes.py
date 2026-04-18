"""LangGraph node functions — thin wrappers around agent classes."""
from __future__ import annotations

from agents.worldbuilding_agent import WorldbuildingAgent
from agents.character_agent import CharacterAgent
from agents.plot_agent import PlotAgent
from agents.consistency_checker import ConsistencyChecker
from agents.narrative_output_agent import NarrativeOutputAgent
from .negotiation_subgraph import run_negotiation
from .state import GraphState

# Agent singletons
_worldbuilding = WorldbuildingAgent()
_character = CharacterAgent()
_plot = PlotAgent()
_checker = ConsistencyChecker()
_narrative = NarrativeOutputAgent()


def node_worldbuilding(state: GraphState) -> dict:
    update = _worldbuilding.run(state)
    if not update.get("is_safe", True):
        update["phase"] = "done"
    else:
        update["phase"] = "character"
    return update


def node_character(state: GraphState) -> dict:
    update = _character.run(state)
    update["phase"] = "plot"
    return update


def node_plot(state: GraphState) -> dict:
    update = _plot.run(state)
    update["phase"] = "consistency"
    return update


def node_consistency(state: GraphState) -> dict:
    update = _checker.run(state)
    # Phase routing happens via conditional edge (see edges.py)
    return update


def node_negotiation(state: GraphState) -> dict:
    update = run_negotiation(state)
    update["phase"] = "narrative"
    return update


def node_narrative(state: GraphState) -> dict:
    update = _narrative.run(state)
    update["phase"] = "done"
    return update
