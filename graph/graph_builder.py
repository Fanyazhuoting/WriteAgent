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
    node_human_review,
)
from .edges import (
    route_after_consistency,
    route_after_negotiation,
    route_after_human_review,
)


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
    graph.add_node("human_review", node_human_review)

    # Entry point
    graph.set_entry_point("worldbuilding")

    # Linear edges
    graph.add_edge("worldbuilding", "character")
    graph.add_edge("character", "plot")
    graph.add_edge("plot", "consistency")

    # Conditional edges
    graph.add_conditional_edges(
        "consistency",
        route_after_consistency,
        {
            "negotiation": "negotiation",
            "narrative": "narrative",
        },
    )
    graph.add_conditional_edges(
        "negotiation",
        route_after_negotiation,
        {
            "human_review": "human_review",
            "narrative": "narrative",
        },
    )
    graph.add_conditional_edges(
        "human_review",
        route_after_human_review,
        {
            "human_review": "human_review",
            "consistency": "consistency",
            "narrative": "narrative",
        },
    )

    # Terminal
    graph.add_edge("narrative", END)

    return graph.compile()


# Module-level compiled graph (import this in the API)
novel_graph = build_graph()
