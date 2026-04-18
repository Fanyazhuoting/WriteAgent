"""Input sanitizer — detects and neutralises prompt injection attempts."""
from __future__ import annotations

import re
from config.constants import MAX_INPUT_LENGTH

# Patterns associated with prompt injection
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+(your\s+)?(role|instructions?|system\s+prompt)", re.I),
    re.compile(r"you\s+are\s+now\s+(a\s+)?", re.I),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a\s+)?", re.I),
    re.compile(r"(system|user|assistant)\s*:\s*", re.I),
    re.compile(r"<\|?(im_start|im_end|endoftext)\|?>", re.I),
    re.compile(r"jailbreak", re.I),
    re.compile(r"DAN\s+mode", re.I),
]

# Sensitive content patterns: Gore, Restricted/Adult, and Political Figures
_SENSITIVE_PATTERNS: list[re.Pattern] = [
    # Gore / Bloody
    re.compile(r"\b(blood|guts|gore|torture|mutilat|decapitat|dismember|massacre|slaughter)\b", re.I),
    # Restricted / Adult
    re.compile(r"\b(porn|sex|explicit|nsfw|erotic|naked|nude|sexual|intercourse)\b", re.I),
    # Political Figures (Common examples, can be expanded)
    re.compile(r"\b(Trump|Biden|Xi Jinping|Putin|Zelensky|Obama|Hitler|Stalin|Mao)\b", re.I),
]

# HTML/script tags
_HTML_PATTERN = re.compile(r"<[^>]+>")


class SanitizationResult:
    def __init__(self, text: str, is_injected: bool, reasons: list[str]):
        self.text = text
        self.is_injected = is_injected
        self.reasons = reasons


def sanitize(user_input: str) -> SanitizationResult:
    """
    Sanitize a user-provided string.

    Returns a SanitizationResult with:
        .text        — sanitized string safe to pass to agents
        .is_injected — True if injection patterns were detected
        .reasons     — list of matched pattern descriptions
    """
    reasons: list[str] = []

    # 1. Length check
    text = user_input[:MAX_INPUT_LENGTH]
    if len(user_input) > MAX_INPUT_LENGTH:
        reasons.append(f"Truncated: input exceeded {MAX_INPUT_LENGTH} characters")

    # 2. Strip HTML tags
    text = _HTML_PATTERN.sub("", text)

    # 3. Detect injection patterns (flag but also redact the match)
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            reasons.append(f"Injection pattern detected: {pattern.pattern[:40]}")
            text = pattern.sub("[REDACTED]", text)

    # 4. Detect sensitive content (Gore, Adult, Political Figures)
    for pattern in _SENSITIVE_PATTERNS:
        if pattern.search(text):
            reasons.append(f"Sensitive content detected: {pattern.pattern[:40]}")
            text = pattern.sub("[REDACTED]", text)

    is_injected = bool(reasons and any(("Injection" in r or "Sensitive" in r) for r in reasons))
    return SanitizationResult(text=text.strip(), is_injected=is_injected, reasons=reasons)
