"""Load and transform real production data for offline model evaluation."""
from __future__ import annotations

import json
import re
from pathlib import Path


def _strip_markdown_json(text: str) -> str:
    m = re.match(r"^```(?:json)?\s*\n(.*?)```\s*$", text, re.DOTALL)
    return m.group(1).strip() if m else text


def load_done_states(data_dir: Path) -> list[dict]:
    states_dir = data_dir / "novel_states"
    if not states_dir.is_dir():
        return []
    results = []
    for f in sorted(states_dir.glob("*.json")):
        try:
            state = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if state.get("phase") != "done":
            continue
        fp = state.get("final_prose", "")
        if not fp or fp.startswith("Error"):
            continue
        results.append(state)
    return results


def load_audit_entries(data_dir: Path, agent_id: str | None = None) -> list[dict]:
    logs_dir = data_dir / "audit_logs"
    if not logs_dir.is_dir():
        return []
    results = []
    for f in sorted(logs_dir.glob("*.jsonl")):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if agent_id and entry.get("agent_id") != agent_id:
                    continue
                if entry.get("output", "").startswith("Error"):
                    continue
                results.append(entry)
        except (json.JSONDecodeError, OSError):
            continue
    return results


def extract_prose_texts(states: list[dict]) -> list[dict]:
    texts = []
    for s in states:
        nid = s.get("novel_id", "unknown")
        scene = s.get("current_scene_number", 0)
        for field, text_type in [
            ("final_prose", "final_prose"),
            ("raw_scene_draft", "raw_scene_draft"),
        ]:
            val = s.get(field, "")
            if val and not val.startswith("Error"):
                texts.append({
                    "novel_id": nid,
                    "scene_number": scene,
                    "text_type": text_type,
                    "text": val,
                })
        for i, hist in enumerate(s.get("scene_history", [])):
            if hist and isinstance(hist, str):
                texts.append({
                    "novel_id": nid,
                    "scene_number": i + 1,
                    "text_type": "scene_history",
                    "text": hist,
                })
    return texts


def extract_consistency_results(audit_entries: list[dict]) -> list[dict]:
    results = []
    for entry in audit_entries:
        if entry.get("agent_id") != "consistency_checker":
            continue
        output_raw = entry.get("output", "")
        try:
            output = json.loads(_strip_markdown_json(output_raw))
        except (json.JSONDecodeError, TypeError):
            continue
        results.append({
            "novel_id": entry.get("novel_id", "unknown"),
            "scene_number": entry.get("scene_number", 0),
            "has_contradiction": output.get("has_contradiction", False),
            "contradictions": output.get("contradictions", []),
        })
    return results


def extract_world_rules_cases(states: list[dict]) -> list[dict]:
    cases = []
    for s in states:
        rules = s.get("world_rules_context", "")
        draft = s.get("raw_scene_draft", "")
        if rules and draft and not draft.startswith("Error"):
            cases.append({
                "novel_id": s.get("novel_id", "unknown"),
                "scene_number": s.get("current_scene_number", 0),
                "world_rules_context": rules,
                "raw_scene_draft": draft,
            })
    return cases


def extract_character_genders(states: list[dict]) -> list[dict]:
    chars = []
    for s in states:
        nid = s.get("novel_id", "unknown")
        profiles = s.get("character_profiles_snapshot", {})
        if not isinstance(profiles, dict):
            continue
        for name, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            core = profile.get("core_attributes", {})
            if not isinstance(core, dict):
                continue
            gender = core.get("gender")
            if gender:
                chars.append({
                    "novel_id": nid,
                    "name": name,
                    "gender": gender,
                    "description": profile.get("description", ""),
                })
    return chars
