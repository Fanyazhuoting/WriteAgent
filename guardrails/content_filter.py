"""Content safety filter — rule-based + optional LLM classifier for narrative output."""
from __future__ import annotations

import re

# Configurable blocked keyword patterns (extend as needed)
_BLOCKED_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(child\s+abuse|child\s+pornography|CSAM)\b", re.I),
    re.compile(r"\b(detailed\s+instructions?\s+(for|to)\s+(make|build|synthesize))\b.*?(bomb|weapon|explosive|poison)", re.I | re.S),
    re.compile(r"\b(suicide\s+method|how\s+to\s+kill\s+yourself)\b", re.I),
]

# Patterns that trigger a warning but not a block (configurable per content rating)
_WARNING_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(graphic\s+violence|torture\s+in\s+detail)\b", re.I),
    re.compile(r"\b(explicit\s+sexual)\b", re.I),
]


class FilterResult:
    def __init__(self, text: str, blocked: bool, warnings: list[str], reasons: list[str]):
        self.text = text
        self.blocked = blocked
        self.warnings = warnings
        self.reasons = reasons


def filter_output(text: str, content_rating: str = "PG-13") -> FilterResult:
    """
    Apply content safety rules to generated prose.

    Args:
        text: The narrative prose to check.
        content_rating: "G", "PG-13", "R", or "UNRATED".
                        "R" and "UNRATED" skip warning-level patterns.

    Returns:
        FilterResult with .blocked=True if hard-blocked content is detected.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(text):
            reasons.append(f"Blocked pattern: {pattern.pattern[:60]}")

    if content_rating in ("G", "PG-13"):
        for pattern in _WARNING_PATTERNS:
            if pattern.search(text):
                warnings.append(f"Warning pattern: {pattern.pattern[:60]}")

    blocked = bool(reasons)
    filtered_text = text if not blocked else "[Content blocked by safety filter]"
    return FilterResult(text=filtered_text, blocked=blocked, warnings=warnings, reasons=reasons)
