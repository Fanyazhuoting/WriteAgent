"""Pydantic models for ChromaDB entity documents."""
from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


EntityType = Literal["character", "location", "world_rule", "faction", "artifact"]
RuleSeverity = Literal["absolute", "hard", "soft"]
RuleCategory = Literal["physics", "magic", "social", "geography", "other"]


class EntityDoc(BaseModel):
    """A character, location, faction, or artifact stored in world_entities collection."""
    entity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entity_type: EntityType
    name: str
    novel_id: str
    description: str          # permanent attributes (appearance, background) — embedded for semantic search
    current_state: str = ""   # dynamic scene state — stored in metadata only, not embedded
    last_updated_scene: int = 0
    version: int = 1
    tags: str = ""            # comma-separated for Chroma metadata filtering
    is_active: bool = True


class SceneArchiveDoc(BaseModel):
    """Compressed summary of a past scene stored in scene_archive collection."""
    archive_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    novel_id: str
    scene_number: int
    chapter: int = 1
    summary: str              # ~250 token factual summary (the ChromaDB document)
    characters_present: str   # comma-separated names
    location: str
    plot_events: str          # JSON-encoded list[str]
    timestamp: str
    token_count: int = 0


class WorldRuleDoc(BaseModel):
    """An immutable or near-immutable world rule stored in world_rules collection."""
    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    novel_id: str
    description: str          # rule description in plain prose (the ChromaDB document)
    category: RuleCategory = "other"
    severity: RuleSeverity = "soft"
    established_at_scene: int = 0
    established_by: Literal["worldbuilding_agent", "human"] = "worldbuilding_agent"
