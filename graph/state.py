"""Central GraphState TypedDict — the shared contract for all LangGraph nodes."""
from __future__ import annotations

import operator
from typing import Annotated, Literal, Optional
from typing_extensions import TypedDict


class GraphState(TypedDict):
    # Novel metadata
    novel_id: str
    genre: str
    style_guide: str
    output_language: str

    # Scene progress
    current_scene_number: int
    current_scene_brief: str
    scene_history: Annotated[list[str], operator.add]       # append-only

    # Agent outputs (current round)
    world_rules_context: str
    character_states: dict[str, str]                        # {char_name: state_summary}
    plot_events: Annotated[list[str], operator.add]         # append-only
    raw_scene_draft: str

    # Memory
    retrieved_entities: list[dict]
    sliding_window_context: str

    # Consistency & negotiation
    contradictions: list[dict]
    has_contradiction: bool
    veto_active: bool
    negotiation_log: Annotated[list[dict], operator.add]    # append-only
    negotiation_round: int
    negotiation_resolved: bool

    # Final output
    final_prose: str
    prose_chunks: Annotated[list[str], operator.add]        # append-only

    # Human-in-the-loop
    human_injection: Optional[str]
    awaiting_human: bool

    # Audit
    agent_messages: Annotated[list[dict], operator.add]     # append-only

    # Control
    error: Optional[str]
    phase: Literal[
        "worldbuilding", "character", "plot", "consistency",
        "negotiation", "narrative", "human_review", "done"
    ]


def initial_state(
    novel_id: str,
    genre: str,
    style_guide: str,
    first_scene_brief: str,
    output_language: str = "English",
) -> GraphState:
    """Return a fresh GraphState for a new novel."""
    return GraphState(
        novel_id=novel_id,
        genre=genre,
        style_guide=style_guide,
        output_language=output_language,
        current_scene_number=1,
        current_scene_brief=first_scene_brief,
        scene_history=[],
        world_rules_context="",
        character_states={},
        plot_events=[],
        raw_scene_draft="",
        retrieved_entities=[],
        sliding_window_context="",
        contradictions=[],
        has_contradiction=False,
        veto_active=False,
        negotiation_log=[],
        negotiation_round=0,
        negotiation_resolved=False,
        final_prose="",
        prose_chunks=[],
        human_injection=None,
        awaiting_human=False,
        agent_messages=[],
        error=None,
        phase="worldbuilding",
    )
