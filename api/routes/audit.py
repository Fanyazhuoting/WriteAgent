"""Audit trail endpoints."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query
from api.models import AuditEntry, NegotiationEntry
from api.dependencies import get_state_store
from utils.audit_logger import get_log, get_log_from_disk
from fastapi import Depends

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/{novel_id}")
def get_audit_trail(
    novel_id: str,
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0),
    from_disk: bool = Query(False, description="Read from JSONL file instead of memory"),
    order: str = Query("desc", description="Sort order: 'desc' (newest first) or 'asc'"),
):
    if from_disk:
        all_entries = get_log_from_disk(novel_id, limit=10000, offset=0)
    else:
        all_entries = get_log(novel_id, limit=10000, offset=0)

    total = len(all_entries)
    if order == "desc":
        all_entries = list(reversed(all_entries))
    entries = all_entries[offset: offset + limit]

    items = [
        AuditEntry(
            log_id=e.get("log_id", ""),
            agent_id=e.get("agent_id", ""),
            scene_number=e.get("scene_number", 0),
            timestamp=e.get("timestamp", ""),
            output_preview=e.get("output_preview", ""),
            prompt=e.get("prompt"),
            output=e.get("output"),
            prompt_tokens=e.get("prompt_tokens", 0),
            completion_tokens=e.get("completion_tokens", 0),
            duration_ms=e.get("duration_ms", 0),
        )
        for e in entries
    ]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/{novel_id}/conflicts")
def get_conflicts(
    novel_id: str,
    scene_number: Optional[int] = Query(None, description="Filter by scene number"),
    states: dict = Depends(get_state_store),
):
    """
    Returns the conflict detection and negotiation log.
    Round 0 = initial detection by ConsistencyChecker.
    Rounds 1+ = negotiation revision attempts.
    Optionally filter by scene_number.
    """
    state = states.get(novel_id)
    if not state:
        return []
    rounds = state.get("negotiation_log", [])

    if scene_number is not None:
        rounds = [r for r in rounds if r.get("scene_number") == scene_number]

    result = []
    for r in rounds:
        round_num = r.get("round_number", 0)
        contradictions = r.get("contradictions", [])
        result.append({
            "scene_number": r.get("scene_number", 0),
            "round_number": round_num,
            # Round 0: initial detection; rounds 1+: contradictions before revision
            "entity_conflicts": contradictions if round_num == 0 else [],
            "contradictions_before": contradictions if round_num > 0 else [],
            "contradictions_after": r.get("contradictions_after", []),
            "resolution": r.get("resolution"),
            "resolved": r.get("resolved", False),
            "timestamp": r.get("timestamp"),
        })
    return result


@router.get("/{novel_id}/negotiations", response_model=list[NegotiationEntry])
def get_negotiations(
    novel_id: str,
    states: dict = Depends(get_state_store),
):
    state = states.get(novel_id)
    if not state:
        return []
    rounds = state.get("negotiation_log", [])
    return [
        NegotiationEntry(
            scene_number=r.get("scene_number", 0),
            round_number=r.get("round_number", 0),
            participants=r.get("participants", []),
            proposal=r.get("proposal", ""),
            contradictions=r.get("contradictions", []),
            resolution=r.get("resolution"),
            resolved=r.get("resolved", False),
            timestamp=r.get("timestamp"),
        )
        for r in rounds
    ]
