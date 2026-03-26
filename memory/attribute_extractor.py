"""
Structured attribute extraction for EntityDoc characters.

Two layers
----------
1. Code-based extraction (core attributes)
   Regex patterns for universal, reliably-comparable attributes:
   hair_color, eye_color, skin_tone, gender, species, height, notable_marks.
   These are written once at entity creation and never overwritten.

2. LLM-based extraction (extended attributes)
   A focused LLM call extracts genre-specific permanent attributes
   (spirit_root, cultivation_path, nationality, profession, …) not covered
   by the regex layer.  Also written once and never overwritten.

Pre-scan helpers
----------------
PRESCAN_PATTERNS  — subset of core patterns whose values can be compared
                    deterministically in ConsistencyChecker (colour-based).
_extract_character_windows — extract draft text near a character's name.
_find_attributed_value     — possessive-proximity search: only return a
                             colour match if the character's name appears
                             within PROXIMITY chars to the LEFT of the match.
values_conflict            — normalised string comparison.
"""
from __future__ import annotations

import json
import re

from utils.llm_client import chat_completion


# ---------------------------------------------------------------------------
# Colour vocabulary (ZH + EN)
# ---------------------------------------------------------------------------

_COLOURS_ZH = (
    "金色?|黑色?|棕色?|红色?|白色?|银色?|蓝色?|绿色?|紫色?|橙色?|粉色?|灰色?|褐色?|栗色?"
)
_COLOURS_EN = (
    r"golden|blond(?:e)?|black|brown|red|auburn|white|silver|"
    r"blue|green|purple|orange|pink|gr[ae]y|platinum"
)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Hair colour
_HAIR_ZH = re.compile(
    rf"({_COLOURS_ZH})[的]?(?:头发|发丝|发色|发型|长发|短发|卷发|直发)",
    re.IGNORECASE,
)
_HAIR_EN = re.compile(
    rf"\b({_COLOURS_EN})\b[\s-]*(?:hair|locks|tresses|curls|waves)",
    re.IGNORECASE,
)

# Eye colour
_EYE_ZH = re.compile(
    rf"({_COLOURS_ZH})[的]?(?:眼睛|眼眸|眼珠|眼神|双眸)",
    re.IGNORECASE,
)
_EYE_EN = re.compile(
    rf"\b({_COLOURS_EN})\b[\s-]*eyes?\b",
    re.IGNORECASE,
)

# Skin tone — colour adjectives + explicit skin/complexion nouns
_SKIN_ZH = re.compile(
    rf"({_COLOURS_ZH}|白皙|黝黑|古铜|苍白|红润)[的]?(?:皮肤|肤色|面容|脸庞)",
    re.IGNORECASE,
)
_SKIN_EN = re.compile(
    rf"\b({_COLOURS_EN}|pale|fair|dark|tan(?:ned)?|olive)\b[\s-]*(?:skin|complexion|face)",
    re.IGNORECASE,
)

# Gender — explicit noun-based statements only (pronouns are too ambiguous)
_GENDER_ZH = re.compile(r"(男|女)(?:性|子|孩|生|士|儿|人)\b")
_GENDER_EN = re.compile(r"\b(male|female|man|woman|boy|girl)\b", re.IGNORECASE)

# Species / race
_SPECIES_ZH = re.compile(
    r"(人类|妖族|魔族|精灵|半妖|兽人|龙族|吸血鬼|天使|恶魔|灵体|鬼魂|神族|人鱼|矮人|半人马)\b"
)
_SPECIES_EN = re.compile(
    r"\b(human|elf|demon|vampire|dragon|half-elf|dwarf|orc|angel|spirit|mermaid|beastman|undead)\b",
    re.IGNORECASE,
)

# Height — high-confidence keywords only
_HEIGHT_ZH = re.compile(r"(高挑|高大|魁梧|矮小|娇小|中等身材|修长)")
_HEIGHT_EN = re.compile(
    r"\b(tall|towering|short|petite|average height|slender|lanky)\b",
    re.IGNORECASE,
)

# Notable marks — multi-value (scars, tattoos, birthmarks, etc.)
_MARKS_ZH = re.compile(r"(疤痕|刀疤|烫伤疤|胎记|纹身|刺青|黑痣|独眼|断指|义肢|白发|银发)")
_MARKS_EN = re.compile(
    r"\b(scar|birthmark|tattoo|mole|prosthetic|glass eye|white hair)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Pattern registries (exported — used by ConsistencyChecker)
# ---------------------------------------------------------------------------

# PRESCAN_PATTERNS: colour-based attributes suitable for deterministic code
# contradiction detection.  Values can be compared with simple string ops.
PRESCAN_PATTERNS: dict[str, list[re.Pattern]] = {
    "hair_color": [_HAIR_ZH, _HAIR_EN],
    "eye_color":  [_EYE_ZH,  _EYE_EN],
    "skin_tone":  [_SKIN_ZH, _SKIN_EN],
}

# EXTRACTION_PATTERNS: superset used when building core_attributes at entity
# creation time.  Includes attributes verified by LLM (not code) in pre-scan.
EXTRACTION_PATTERNS: dict[str, list[re.Pattern]] = {
    **PRESCAN_PATTERNS,
    "gender":  [_GENDER_ZH,  _GENDER_EN],
    "species": [_SPECIES_ZH, _SPECIES_EN],
    "height":  [_HEIGHT_ZH,  _HEIGHT_EN],
}

# Attributes that may have multiple values (all matches collected)
_MULTI_VALUE_PATTERNS: dict[str, list[re.Pattern]] = {
    "notable_marks": [_MARKS_ZH, _MARKS_EN],
}

# ---------------------------------------------------------------------------
# Low-level helpers (exported for ConsistencyChecker)
# ---------------------------------------------------------------------------

_WINDOW = 150  # char window for _extract_character_windows fallback
_PROXIMITY = 30  # max chars between character name and colour match


def _first_match(patterns: list[re.Pattern], text: str) -> str | None:
    """Return the first capturing group from the first matching pattern, or None."""
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1)
    return None


def _all_matches(patterns: list[re.Pattern], text: str) -> list[str]:
    """Return all capturing-group values across all patterns."""
    found: list[str] = []
    for pat in patterns:
        found.extend(m.group(1) for m in pat.finditer(text))
    return found


def _extract_character_windows(name: str, draft: str, window: int = _WINDOW) -> str:
    """
    Return the portions of *draft* within ±window chars of each occurrence of *name*.
    Simple char-window approach — used for description extraction at entity creation.
    """
    segments: list[str] = []
    start = 0
    while True:
        pos = draft.find(name, start)
        if pos == -1:
            break
        lo = max(0, pos - window)
        hi = min(len(draft), pos + len(name) + window)
        segments.append(draft[lo:hi])
        start = pos + 1
    return " ".join(segments)


def _find_attributed_value(
    name: str,
    patterns: list[re.Pattern],
    text: str,
    proximity: int = _PROXIMITY,
) -> str | None:
    """
    Search *text* for an attribute value **owned by** character *name*.

    A match is accepted only if *name* appears within *proximity* chars to the
    LEFT of the matched colour word (possessive construction):
      - Chinese: "林月的银色发丝"  → name 林月 is 3 chars left of 银色
      - English: "Elena's golden hair" → name Elena is 9 chars left of golden

    This eliminates cross-character false positives regardless of whether the
    characters appear in the same sentence or adjacent sentences, because we
    always check ownership rather than just proximity to the name.
    """
    for pat in patterns:
        for m in pat.finditer(text):
            left_context = text[max(0, m.start() - proximity): m.start()]
            if name in left_context:
                return m.group(1)
    return None


def values_conflict(stored: str, found: str) -> bool:
    """
    Return True if two attribute values are meaningfully different.
    Normalises away the '色' suffix common in Chinese colour words and
    folds to lowercase for English comparisons.
    """
    def _norm(v: str) -> str:
        return v.lower().rstrip("色").strip()
    return _norm(stored) != _norm(found)


# ---------------------------------------------------------------------------
# Core attribute extraction — code-based, runs at entity creation
# ---------------------------------------------------------------------------

def extract_core_attributes(description: str) -> dict[str, str]:
    """
    Extract universal permanent attributes from *description* using regex.

    Returns only attributes that are **explicitly present** in the text.
    Never infers or speculates.  Safe to call on any description string.
    """
    result: dict[str, str] = {}

    # Single-value attributes
    for attr_key, patterns in EXTRACTION_PATTERNS.items():
        val = _first_match(patterns, description)
        if val:
            result[attr_key] = val

    # Multi-value attributes
    for attr_key, patterns in _MULTI_VALUE_PATTERNS.items():
        vals = _all_matches(patterns, description)
        if vals:
            result[attr_key] = ", ".join(vals)

    return result


# ---------------------------------------------------------------------------
# Extended attribute extraction — LLM-based, runs at entity creation
# ---------------------------------------------------------------------------

_EXTENDED_SYSTEM_PROMPT = (
    "You are a character archive analyst. Extract permanent, immutable attributes "
    "from the character description provided.\n\n"
    "Rules:\n"
    "- 'Permanent' means the attribute will NOT naturally change between story scenes.\n"
    "- Only extract attributes explicitly stated — never infer or speculate.\n"
    "- Do NOT repeat attributes already listed under 'Already extracted'.\n"
    "- Return a flat JSON object with snake_case English keys and string values.\n"
    "- Maximum 8 attributes. If nothing relevant remains, return {}.\n"
    "- Example keys (vary by genre): spirit_root, cultivation_path, clan, affiliation,\n"
    "  superpower_type, nationality, profession, notable_ability."
)


def extract_extended_attributes(
    genre: str,
    name: str,
    description: str,
    core_attrs: dict[str, str],
) -> dict[str, str]:
    """
    Use a small, focused LLM call to extract genre-specific permanent attributes
    not covered by the regex layer.

    *core_attrs* is passed so the LLM does not duplicate already-found values.
    Falls back to {} on any error so it never blocks the calling flow.
    """
    already_found = (
        ", ".join(f"{k}: {v}" for k, v in core_attrs.items())
        if core_attrs
        else "(none)"
    )
    user_content = (
        f"Novel genre: {genre}\n"
        f"Character: {name}\n"
        f"Description: {description}\n"
        f"Already extracted (do not repeat): {already_found}\n\n"
        "Extract remaining permanent attributes relevant to this genre and character."
    )

    try:
        content = chat_completion(
            messages=[
                {"role": "system", "content": _EXTENDED_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            max_tokens=256,
        )
    except Exception:
        return {}

    # --- Parse JSON from LLM response ---
    text = content.strip()
    # Strip markdown fences if present
    text = re.sub(r"```[a-zA-Z]*\n?", "", text).strip()
    if text.endswith("```"):
        text = text[:-3].strip()

    result: dict = {}
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            try:
                result = json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                return {}
        else:
            return {}

    if not isinstance(result, dict):
        return {}

    # Sanitise: keep only scalar values; convert everything to str
    return {
        str(k).strip(): str(v).strip()
        for k, v in result.items()
        if isinstance(v, (str, int, float)) and str(v).strip()
    }
