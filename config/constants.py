MAX_INPUT_LENGTH = 2000          # Max chars for human-injected plot events
ENTITY_SUMMARY_MAX_TOKENS = 300  # Max tokens per entity doc in context
SCENE_COMPRESS_TOKENS = 250      # Target tokens for cold-archived scene summaries
CONTENT_FILTER_MAX_TOKENS = 512  # Max tokens sent to LLM safety classifier

ENTITY_TYPES = ("character", "location", "world_rule", "faction", "artifact")
RULE_SEVERITIES = ("absolute", "soft")
RULE_CATEGORIES = ("physics", "magic", "social", "geography", "other")

AGENT_IDS = {
    "worldbuilding": "worldbuilding_agent",
    "character": "character_agent",
    "plot": "plot_agent",
    "consistency": "consistency_checker",
    "narrative": "narrative_output_agent",
}

WS_EVENT_TYPES = (
    "prose_chunk",
    "phase_change",
    "negotiation",
    "veto",
    "human_required",
    "error",
    "done",
)
