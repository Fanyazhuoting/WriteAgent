"""Assemble the full LangGraph StateGraph."""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from .state import GraphState
from .nodes import (
    node_worldbuilding,
    node_character,
    node_plot,
    node_consistency,
    node_negotiation,
    node_narrative,
)
from .edges import route_after_worldbuilding, route_after_consistency


def build_graph() -> StateGraph:
    """Build and compile the novel-writing state graph."""
    graph = StateGraph(GraphState)

    # Register nodes
    graph.add_node("worldbuilding", node_worldbuilding)
    graph.add_node("character", node_character)
    graph.add_node("plot", node_plot)
    graph.add_node("consistency", node_consistency)
    graph.add_node("negotiation", node_negotiation)
    graph.add_node("narrative", node_narrative)

    # Entry point
    graph.set_entry_point("worldbuilding")

    # Conditional: security check after worldbuilding
    graph.add_conditional_edges(
        "worldbuilding",
        route_after_worldbuilding,
        {
            "character": "character",
            "end": END,
        },
    )

    # Linear edges
    graph.add_edge("character", "plot")
    graph.add_edge("plot", "consistency")

    # Conditional: contradiction → negotiate, else → narrative
    graph.add_conditional_edges(
        "consistency",
        route_after_consistency,
        {
            "negotiation": "negotiation",
            "narrative": "narrative",
        },
    )

    # Negotiation always proceeds to narrative (unresolved issues are logged)
    graph.add_edge("negotiation", "narrative")

    # Terminal
    graph.add_edge("narrative", END)

    return graph.compile()


# Module-level compiled graph (import this in the API)
novel_graph = build_graph()
