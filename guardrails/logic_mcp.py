"""
Logic MCP — Physical and spatio-temporal consistency tools.
Includes world clock management and travel feasibility checks.
"""
from utils.mcp_types import MCPTool, MCPRegistry
from memory.spatio_temporal import get_world_clock, advance_clock, sync_world_clock, calculate_travel_logic

# Initialize the Logic tool registry
logic_mcp = MCPRegistry()

# ... (check_world_clock and advance_world_clock) ...

# 2.5 Sync World Clock (Absolute)
logic_mcp.register(MCPTool(
    name="sync_world_clock",
    description="Directly set the in-universe date and time. Use this when the Scene Brief implies a significant time jump (e.g., '7 days later') that needs to be synchronized.",
    input_schema={
        "type": "object",
        "properties": {
            "novel_id": {"type": "string"},
            "year": {"type": "integer"},
            "month": {"type": "integer"},
            "day": {"type": "integer"},
            "hour": {"type": "integer"}
        },
        "required": ["novel_id", "year", "month", "day", "hour"]
    },
    handler=sync_world_clock
))

# 1. World Clock Lookup
logic_mcp.register(MCPTool(
    name="check_world_clock",
    description="[MANDATORY] Get the current in-universe date and time. You MUST call this at the beginning of every scene to ground your narrative in the correct temporal context.",
    input_schema={
        "type": "object",
        "properties": {
            "novel_id": {"type": "string", "description": "The unique ID of the novel."}
        },
        "required": ["novel_id"]
    },
    handler=get_world_clock
))

# 2. Advance World Clock
logic_mcp.register(MCPTool(
    name="advance_world_clock",
    description="[MANDATORY] Move the in-universe time forward based on the duration of the current scene. You MUST call this to ensure the next scene starts at the correct time.",
    input_schema={
        "type": "object",
        "properties": {
            "novel_id": {"type": "string"},
            "hours": {"type": "integer", "description": "Number of hours to advance (e.g., 1 for a short conversation, 8 for a night's sleep)."}
        },
        "required": ["novel_id", "hours"]
    },
    handler=advance_clock
))

# 3. Travel Feasibility
logic_mcp.register(MCPTool(
    name="validate_travel_feasibility",
    description="Calculate distance and travel time between two locations. Prevents teleportation errors.",
    input_schema={
        "type": "object",
        "properties": {
            "novel_id": {"type": "string"},
            "origin": {"type": "string", "description": "The name of the starting location."},
            "destination": {"type": "string", "description": "The name of the target location."},
            "mode": {
                "type": "string", 
                "enum": ["walking", "horse", "carriage", "magic_portal", "sailing"],
                "default": "walking"
            }
        },
        "required": ["novel_id", "origin", "destination"]
    },
    handler=calculate_travel_logic
))
