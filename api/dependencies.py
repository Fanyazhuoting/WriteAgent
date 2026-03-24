"""FastAPI dependency injection helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path

from graph.graph_builder import novel_graph
from memory.chroma_client import get_client
from prompts.registry import registry

_STATE_DIR = Path("novel_states")
_novel_ws_queues: dict[str, list] = {}


def _state_path(novel_id: str) -> Path:
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    return _STATE_DIR / f"{novel_id}.json"


def _save_state(novel_id: str, state: dict) -> None:
    """Persist a novel state to disk as JSON."""
    with open(_state_path(novel_id), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, default=str)


def _load_state(novel_id: str) -> dict | None:
    """Load a novel state from disk. Returns None if not found."""
    path = _state_path(novel_id)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class _PersistentStateStore:
    """Dict-like interface that reads/writes states to disk automatically."""

    def __contains__(self, novel_id: str) -> bool:
        return _state_path(novel_id).exists()

    def __getitem__(self, novel_id: str) -> dict:
        state = _load_state(novel_id)
        if state is None:
            raise KeyError(novel_id)
        return state

    def __setitem__(self, novel_id: str, state: dict) -> None:
        _save_state(novel_id, state)

    def get(self, novel_id: str, default=None):
        state = _load_state(novel_id)
        return state if state is not None else default


_novel_states = _PersistentStateStore()


def get_graph():
    return novel_graph


def get_registry():
    return registry


def get_state_store() -> _PersistentStateStore:
    return _novel_states


def get_ws_queues() -> dict[str, list]:
    return _novel_ws_queues
