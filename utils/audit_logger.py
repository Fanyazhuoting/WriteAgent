"""Structured audit logger: writes JSONL per novel and keeps an in-memory deque."""
import json
import hashlib
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


_LOG_DIR = Path("audit_logs")
_in_memory: dict[str, deque] = {}   # novel_id -> deque of log dicts
_MAX_IN_MEMORY = 500                 # per novel


def _log_path(novel_id: str) -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR / f"{novel_id}.jsonl"


def log_agent_call(
    *,
    novel_id: str,
    agent_id: str,
    scene_number: int,
    prompt_version: str,
    prompt: str,
    output: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: int = 0,
    langsmith_run_id: str = "",
    metadata: dict | None = None,
) -> dict:
    """Record a single agent call and return the log entry."""
    entry = {
        "log_id": str(uuid.uuid4()),
        "novel_id": novel_id,
        "agent_id": agent_id,
        "scene_number": scene_number,
        "prompt_version": prompt_version,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "input_hash": hashlib.sha256(prompt.encode()).hexdigest()[:16],
        "output_preview": output[:200],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_ms": duration_ms,
        "langsmith_run_id": langsmith_run_id,
        "metadata": metadata or {},
    }
    # Write to JSONL
    with open(_log_path(novel_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # Keep in memory
    if novel_id not in _in_memory:
        _in_memory[novel_id] = deque(maxlen=_MAX_IN_MEMORY)
    _in_memory[novel_id].append(entry)
    return entry


def get_log(novel_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Return recent log entries for a novel from the in-memory deque."""
    buf = _in_memory.get(novel_id, deque())
    entries = list(buf)
    return entries[offset: offset + limit]


def get_log_from_disk(novel_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Read log entries from disk (for large histories)."""
    path = _log_path(novel_id)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    slice_ = lines[offset: offset + limit]
    return [json.loads(l) for l in slice_]
