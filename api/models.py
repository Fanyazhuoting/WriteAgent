"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class StartNovelRequest(BaseModel):
    genre: str = Field(..., description="Novel genre (e.g. 'fantasy', 'sci-fi')")
    style_guide: str = Field(default="Third-person limited, literary fiction style")
    first_scene_brief: str = Field(..., description="Brief for the opening scene")
    output_language: str = Field(default="English", description="Prose output language, e.g. 'English' or 'Chinese'")
    initial_characters: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of {name, description} dicts for initial characters",
    )
    initial_world_rules: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of {description, severity, category} dicts for world rules",
    )


class InjectEventRequest(BaseModel):
    event: str = Field(..., description="Plot event to inject (max 2000 chars)")
    next_scene_brief: Optional[str] = None


class NextSceneRequest(BaseModel):
    scene_brief: str = Field(..., description="Brief for the next scene")


class EntityUpdateRequest(BaseModel):
    description: str
    tags: Optional[str] = None


class PromptActivateRequest(BaseModel):
    version: str


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class NovelStatus(BaseModel):
    novel_id: str
    phase: str
    current_scene_number: int
    error: Optional[str]


class SceneResult(BaseModel):
    novel_id: str
    scene_number: int
    final_prose: str
    contradictions_found: int
    negotiation_rounds: int
    negotiation_resolved: bool


class EntityResponse(BaseModel):
    entity_id: str
    entity_type: str
    name: str
    description: str
    version: int
    last_updated_scene: int


class EntityGraphResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class AuditEntry(BaseModel):
    log_id: str
    agent_id: str
    scene_number: int
    timestamp: str
    output_preview: str
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int


class NegotiationEntry(BaseModel):
    scene_number: int = 0
    round_number: int
    participants: list[str] = []
    proposal: str = ""
    contradictions: list[dict] = []
    resolution: Optional[str]
    resolved: bool
    timestamp: Optional[str]


class PromptVersionInfo(BaseModel):
    agent: str
    versions: list[str]
    active_version: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    chroma: str
    llm: str
    langsmith: str


class WSEvent(BaseModel):
    event_type: Literal["prose_chunk", "phase_change", "negotiation", "veto", "human_required", "error", "done"]
    agent_id: str
    payload: dict[str, Any]
    timestamp: str
