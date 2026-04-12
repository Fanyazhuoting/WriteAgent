"""
Spatio-temporal Memory — Manages in-universe time and geographic consistency.
"""
from __future__ import annotations
import math
import logging
from typing import Dict, Any, Optional
from memory.entity_store import query_entities, upsert_entity, list_entities
from memory.schemas import EntityDoc

logger = logging.getLogger("writeagent.memory.spatio_temporal")

def get_world_clock(novel_id: str) -> Dict[str, Any]:
    """Retrieve the current in-universe time from ChromaDB."""
    try:
        entities = query_entities(novel_id, "WORLD_CLOCK system time", entity_type="system", k=5)
        clock = next((e for e in entities if e.name == "WORLD_CLOCK"), None)
        if clock and clock.extended_attributes:
            return clock.extended_attributes
    except Exception:
        logger.warning(f"Could not retrieve world clock for {novel_id}, using default.")
    
    return {"year": 1, "month": 1, "day": 1, "hour": 12}

def advance_clock(novel_id: str, hours: int) -> Dict[str, Any]:
    """Advance the world clock and persist it."""
    current = get_world_clock(novel_id)
    
    h = int(current.get("hour", 12)) + hours
    new_hour = h % 24
    days_to_add = h // 24
    
    d = int(current.get("day", 1)) + days_to_add
    new_day = ((d - 1) % 30) + 1
    months_to_add = (d - 1) // 30
    
    m = int(current.get("month", 1)) + months_to_add
    new_month = ((m - 1) % 12) + 1
    years_to_add = (m - 1) // 12
    
    new_year = int(current.get("year", 1)) + years_to_add
    
    new_time = {"year": int(new_year), "month": int(new_month), "day": int(new_day), "hour": int(new_hour)}
    
    clock_entity = EntityDoc(
        entity_type="system",
        name="WORLD_CLOCK",
        novel_id=novel_id,
        description="The master clock for this novel universe.",
        extended_attributes=new_time,
        last_updated_scene=0
    )
    try:
        upsert_entity(clock_entity)
    except Exception:
        logger.exception("Failed to persist world clock.")
        
    return new_time

def sync_world_clock(novel_id: str, year: int, month: int, day: int, hour: int) -> Dict[str, Any]:
    """Directly set the world clock (used for significant time jumps)."""
    new_time = {"year": int(year), "month": int(month), "day": int(day), "hour": int(hour)}
    clock_entity = EntityDoc(
        entity_type="system",
        name="WORLD_CLOCK",
        novel_id=novel_id,
        description="The master clock for this novel universe.",
        extended_attributes=new_time,
        last_updated_scene=0
    )
    try:
        upsert_entity(clock_entity)
    except Exception:
        logger.exception("Failed to sync world clock.")
    return new_time

def calculate_travel_logic(novel_id: str, origin: str, destination: str, mode: str = "walking") -> Dict[str, Any]:
    """Calculate travel time between two known locations."""
    try:
        locs = list_entities(novel_id, entity_type="location")
        origin_ent = next((l for l in locs if l.name.lower() == origin.lower()), None)
        dest_ent = next((l for l in locs if l.name.lower() == destination.lower()), None)
        
        if not origin_ent or not dest_ent:
            return {
                "error": f"One or both locations ('{origin}', '{destination}') not found in database.",
                "feasible": True, # Fallback to prevent blocking Agent if data is missing
                "note": "Please establish location coordinates in worldbuilding."
            }
        
        # Extract coordinates from extended attributes
        attr_a = origin_ent.extended_attributes or {}
        attr_b = dest_ent.extended_attributes or {}
        
        x1, y1 = float(attr_a.get("x", 0)), float(attr_a.get("y", 0))
        x2, y2 = float(attr_b.get("x", 0)), float(attr_b.get("y", 0))
        
        distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
        
        # KM/H rough estimates
        speeds = {
            "walking": 5.0,
            "horse": 15.0,
            "carriage": 10.0,
            "magic_portal": 5000.0,
            "sailing": 8.0
        }
        speed = speeds.get(mode.lower(), 5.0)
        travel_hours = distance / speed
        
        return {
            "distance_units": round(distance, 2),
            "travel_hours": round(travel_hours, 1),
            "origin": origin_ent.name,
            "destination": dest_ent.name,
            "mode": mode,
            "feasible": True,
            "arrival_time_estimate": f"Current Time + {round(travel_hours, 1)} hours"
        }
    except Exception as e:
        return {"error": str(e), "feasible": True}
