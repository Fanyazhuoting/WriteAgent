"""Three-tier context builder with token budget enforcement."""
from __future__ import annotations

from config.settings import settings
from utils.token_counter import count_tokens, truncate_to_tokens
from .entity_store import query_entities, get_world_rules, query_scene_archive
from .schemas import EntityDoc, WorldRuleDoc


def build_context_for_agent(
    novel_id: str,
    scene_brief: str,
    scene_history: list[str],
    max_tokens: int | None = None,
) -> str:
    """
    Build a context string for an agent using a three-tier strategy:
      Tier 1 (hot):  last SLIDING_WINDOW_SIZE scenes verbatim
      Tier 2 (warm): top-k semantically relevant entities from ChromaDB
      Tier 3 (cold): absolute world rules (always included within budget)

    Returns a single string to inject into agent prompts.
    """
    budget = max_tokens or settings.hot_context_max_tokens
    parts: list[str] = []

    # Tier 1: Sliding window
    window = scene_history[-settings.sliding_window_size:]
    hot = "\n\n".join(window)
    hot_tokens = count_tokens(hot)
    if hot and hot_tokens <= budget:
        parts.append("## Recent Scenes\n" + hot)
        budget -= hot_tokens
    elif hot:
        truncated = truncate_to_tokens(hot, budget - 50)
        parts.append("## Recent Scenes (truncated)\n" + truncated)
        budget = 0

    if budget <= 0:
        return "\n\n---\n\n".join(parts)

    # Tier 2: ChromaDB entity retrieval
    try:
        entities = query_entities(novel_id, scene_brief, k=settings.retrieval_k)
        entity_parts: list[str] = []
        for entity in entities:
            snippet = f"[{entity.entity_type.upper()}] {entity.name}: {entity.description}"
            snippet_tokens = count_tokens(snippet)
            if snippet_tokens <= budget:
                entity_parts.append(snippet)
                budget -= snippet_tokens
            else:
                break
        if entity_parts:
            parts.append("## Relevant Entities\n" + "\n\n".join(entity_parts))
    except Exception:
        pass  # ChromaDB may be empty on first scene

    if budget <= 0:
        return "\n\n---\n\n".join(parts)

    # Tier 3: Absolute world rules
    try:
        rules = get_world_rules(novel_id, severity="absolute")
        rule_parts: list[str] = []
        for rule in rules:
            snippet = f"[ABSOLUTE RULE] {rule.description}"
            snippet_tokens = count_tokens(snippet)
            if snippet_tokens <= budget:
                rule_parts.append(snippet)
                budget -= snippet_tokens
        if rule_parts:
            parts.append("## World Rules (Absolute)\n" + "\n\n".join(rule_parts))
    except Exception:
        pass

    return "\n\n---\n\n".join(parts)


def get_entity_snapshot(novel_id: str, scene_brief: str, k: int = 10) -> str:
    """Return a compact entity snapshot string for the ConsistencyChecker."""
    try:
        entities = query_entities(novel_id, scene_brief, k=k)
    except Exception:
        return "(no entities found)"
    if not entities:
        return "(no entities found)"
    lines = []
    for e in entities:
        lines.append(f"- [{e.entity_type}] {e.name} (v{e.version}): {e.description}")
    return "\n".join(lines)
