"""Novel lifecycle endpoints."""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

logger = logging.getLogger("writeagent")

from api.models import (
    StartNovelRequest, InjectEventRequest, NextSceneRequest,
    NovelStatus, SceneResult,
)
from api.dependencies import get_graph, get_state_store, get_ws_queues
from graph.state import initial_state
from graph.graph_builder import novel_graph
from memory.entity_store import upsert_entity, upsert_world_rule
from memory.schemas import EntityDoc, WorldRuleDoc
from guardrails.input_sanitizer import sanitize
from guardrails.content_filter import filter_output

router = APIRouter(prefix="/novel", tags=["novel"])

# Track generation jobs: novel_id -> {"status": "generating"|"done"|"error", "result": ..., "error": ...}
_generation_jobs: dict[str, dict] = {}


def _push_ws_event(novel_id: str, event: dict, ws_queues: dict):
    if novel_id not in ws_queues:
        ws_queues[novel_id] = []
    ws_queues[novel_id].append(event)


def _run_graph(novel_id: str, state: dict, ws_queues: dict):
    """Run the LangGraph pipeline in a background thread."""
    try:
        result_state = novel_graph.invoke(state)

        # Content filter
        prose = result_state.get("final_prose", "")
        filter_result = filter_output(prose)
        if filter_result.blocked:
            result_state["final_prose"] = filter_result.text

        # Persist updated state
        from api.dependencies import get_state_store
        get_state_store()[novel_id] = result_state

        _generation_jobs[novel_id] = {
            "status": "done",
            "result": {
                "novel_id": novel_id,
                "scene_number": result_state.get("current_scene_number", 1),
                "final_prose": result_state.get("final_prose", ""),
                "contradictions_found": len(result_state.get("contradictions", [])),
                "negotiation_rounds": result_state.get("negotiation_round", 0),
                "negotiation_resolved": bool(result_state.get("negotiation_resolved")),
            },
        }
        _push_ws_event(novel_id, {
            "event_type": "done",
            "agent_id": "narrative_output_agent",
            "payload": {"prose": result_state.get("final_prose", "")},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, ws_queues)

    except Exception as e:
        _generation_jobs[novel_id] = {"status": "error", "error": str(e)}
        _push_ws_event(novel_id, {
            "event_type": "error",
            "agent_id": "system",
            "payload": {"message": str(e)},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, ws_queues)


@router.post("/start", response_model=NovelStatus)
def start_novel(
    body: StartNovelRequest,
    states=Depends(get_state_store),
):
    novel_id = str(uuid.uuid4())

    try:
        for char in body.initial_characters:
            upsert_entity(EntityDoc(
                entity_type="character",
                name=char.get("name", "Unknown"),
                novel_id=novel_id,
                description=char.get("description", char.get("name", "Unknown")),
            ))

        # Normalise severity: accept "hard" → stored as "hard" (now valid in schema)
        _VALID_SEV = {"soft", "hard", "absolute"}
        for rule in body.initial_world_rules:
            sev = rule.get("severity", "soft")
            if sev not in _VALID_SEV:
                sev = "soft"
            upsert_world_rule(WorldRuleDoc(
                novel_id=novel_id,
                description=rule.get("description", ""),
                severity=sev,
                category=rule.get("category", "other"),
            ))
    except Exception as exc:
        logger.exception("Error initialising novel entities: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to initialise entities: {exc}") from exc

    state = initial_state(
        novel_id=novel_id,
        genre=body.genre,
        style_guide=body.style_guide,
        first_scene_brief=body.first_scene_brief,
        output_language=body.output_language,
    )
    states[novel_id] = state

    return NovelStatus(
        novel_id=novel_id,
        phase="worldbuilding",
        current_scene_number=1,
        error=None,
    )


@router.post("/{novel_id}/scene/next")
def next_scene(
    novel_id: str,
    body: NextSceneRequest,
    states=Depends(get_state_store),
    ws_queues: dict = Depends(get_ws_queues),
):
    if novel_id not in states:
        raise HTTPException(status_code=404, detail="Novel not found")

    # Reject if already generating
    job = _generation_jobs.get(novel_id, {})
    if job.get("status") == "generating":
        raise HTTPException(status_code=409, detail="Scene generation already in progress")

    state = states[novel_id]
    state["current_scene_number"] += 1 if state.get("final_prose") else 0
    state["current_scene_brief"] = body.scene_brief
    state["phase"] = "worldbuilding"
    state["has_contradiction"] = False
    state["contradictions"] = []
    state["negotiation_round"] = 0
    state["negotiation_resolved"] = False
    state["character_profiles_snapshot"] = {}
    states[novel_id] = state

    _generation_jobs[novel_id] = {"status": "generating"}

    thread = threading.Thread(
        target=_run_graph,
        args=(novel_id, state, ws_queues),
        daemon=True,
    )
    thread.start()

    return {"status": "generating", "novel_id": novel_id}


@router.get("/{novel_id}/scene/generation_status")
def generation_status(novel_id: str, states=Depends(get_state_store)):
    """Poll this endpoint to check if scene generation is complete."""
    job = _generation_jobs.get(novel_id)
    if job is None:
        return {"status": "idle"}
    if job["status"] == "error":
        return {"status": "error", "error": job.get("error", "Unknown error")}
    if job["status"] == "done":
        return {"status": "done", "result": job["result"]}

    # Expose in-progress conflict/negotiation state so the UI can react
    state = states.get(novel_id, {})
    phase = state.get("phase", "worldbuilding")
    has_conflict = bool(state.get("has_contradiction"))
    negotiation_round = state.get("negotiation_round", 0)
    contradictions = state.get("contradictions", [])

    return {
        "status": "generating",
        "phase": phase,
        "has_conflict": has_conflict,
        "negotiation_round": negotiation_round,
        "contradictions": contradictions,
    }


@router.post("/{novel_id}/inject")
def inject_event(
    novel_id: str,
    body: InjectEventRequest,
    states=Depends(get_state_store),
    ws_queues: dict = Depends(get_ws_queues),
):
    if novel_id not in states:
        raise HTTPException(status_code=404, detail="Novel not found")

    san = sanitize(body.event)
    if san.is_injected:
        raise HTTPException(
            status_code=400,
            detail=f"Input rejected: prompt injection detected. Reasons: {san.reasons}",
        )

    state = states[novel_id]
    state["human_injection"] = san.text
    if body.next_scene_brief:
        state["current_scene_brief"] = body.next_scene_brief
    states[novel_id] = state
    return {"status": "injected", "novel_id": novel_id, "event": san.text}


@router.get("/{novel_id}/status", response_model=NovelStatus)
def get_status(novel_id: str, states=Depends(get_state_store)):
    if novel_id not in states:
        raise HTTPException(status_code=404, detail="Novel not found")
    state = states[novel_id]
    return NovelStatus(
        novel_id=novel_id,
        phase=state.get("phase", "unknown"),
        current_scene_number=state.get("current_scene_number", 0),
        error=state.get("error"),
    )


@router.get("/{novel_id}/output")
def get_output(novel_id: str, states=Depends(get_state_store)):
    if novel_id not in states:
        raise HTTPException(status_code=404, detail="Novel not found")
    state = states[novel_id]
    return {
        "novel_id": novel_id,
        "prose_chunks": state.get("prose_chunks", []),
        "current_scene": state.get("current_scene_number", 0),
    }
