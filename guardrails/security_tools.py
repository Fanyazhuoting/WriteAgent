"""
Security Tools — Tools for agents to perform active safety checks.
Organized into injection detection, content safety, and PII scanning.
"""
import json
import re
import logging
from typing import Dict, Any, List
from guardrails.input_sanitizer import sanitize
from guardrails.content_filter import filter_output

logger = logging.getLogger("writeagent.security_tools")


def detect_and_sanitize_injection(text: str) -> Dict[str, Any]:
    """
    Detects if the input text contains prompt injection attacks.
    Agents should call this when processing 'human_injection' or 'scene_brief'.
    """
    result = sanitize(text)
    return {
        "is_safe": not result.is_injected,
        "sanitized_text": result.text,
        "reasons": result.reasons if result.is_injected else [],
        "action_required": "reject_and_warn" if result.is_injected else "none"
    }


def verify_content_safety(text: str, safety_level: str = "PG-13") -> Dict[str, Any]:
    """
    Verifies if generated prose complies with safety guidelines.
    Agents should call this to self-audit their output.
    """
    filter_result = filter_output(text)
    return {
        "is_compliant": not filter_result.blocked,
        "blocked_reason": filter_result.reason if filter_result.blocked else "none",
        "suggested_action": "rewrite_violating_parts" if filter_result.blocked else "proceed",
        "safety_level_applied": safety_level
    }


def scan_pii_exposure(text: str) -> Dict[str, Any]:
    """
    Scans for PII (emails, phone numbers) to ensure privacy.
    Prevents accidental leakage of sensitive data in generated content.
    """
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\b(?:\+?86)?1[3-9]\d{9}\b'

    emails = re.findall(email_pattern, text)
    phones = re.findall(phone_pattern, text)

    has_pii = len(emails) > 0 or len(phones) > 0
    return {
        "has_pii": has_pii,
        "detected_count": len(emails) + len(phones),
        "found_types": (["email"] if emails else []) + (["phone"] if phones else []),
        "is_safe_to_publish": not has_pii
    }


# ---------------------------------------------------------------------------
# Tool Metadata Definitions (OpenAI/Qwen compatible)
# ---------------------------------------------------------------------------

SECURITY_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "detect_and_sanitize_injection",
            "description": "Checks for prompt injection attacks in user-provided text. Use this before incorporating user instructions into the story.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The user input text to examine."}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_content_safety",
            "description": "Verifies if the generated prose is safe and complies with content guidelines (violence, sensitive topics, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The generated prose or draft to verify."},
                    "safety_level": {"type": "string", "enum": ["G", "PG-13", "R"], "default": "PG-13"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scan_pii_exposure",
            "description": "Scans text for private information like emails or phone numbers to ensure data privacy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to scan."}
                },
                "required": ["text"]
            }
        }
    }
]

# Function mapping for execution
SECURITY_TOOL_MAP = {
    "detect_and_sanitize_injection": detect_and_sanitize_injection,
    "verify_content_safety": verify_content_safety,
    "scan_pii_exposure": scan_pii_exposure,
}
