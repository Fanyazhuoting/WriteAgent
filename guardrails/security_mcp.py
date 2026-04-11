"""
Security MCP — Security tools wrapped in a unified MCP registry.
Includes injection detection, content safety, and PII scanning.
"""
from utils.mcp_types import MCPTool, MCPRegistry
from guardrails.security_tools import (
    detect_and_sanitize_injection,
    verify_content_safety,
    scan_pii_exposure
)

# Initialize the shared Security tool registry
security_mcp = MCPRegistry()

# 1. Injection Detection
security_mcp.register(MCPTool(
    name="detect_and_sanitize_injection",
    description="Checks for prompt injection attacks in user-provided text. Mandatory when using external user input.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The raw input text to examine."}
        },
        "required": ["text"]
    },
    handler=detect_and_sanitize_injection
))

# 2. Content Safety Audit
security_mcp.register(MCPTool(
    name="verify_content_safety",
    description="Verifies if generated prose complies with safety guidelines (violence, sensitive topics).",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The prose or draft to verify."},
            "safety_level": {
                "type": "string", 
                "enum": ["G", "PG-13", "R"], 
                "default": "PG-13"
            }
        },
        "required": ["text"]
    },
    handler=verify_content_safety
))

# 3. Privacy Scanning
security_mcp.register(MCPTool(
    name="scan_pii_exposure",
    description="Scans text for private information like emails or phone numbers to ensure data privacy.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The text to scan for PII."}
        },
        "required": ["text"]
    },
    handler=scan_pii_exposure
))
