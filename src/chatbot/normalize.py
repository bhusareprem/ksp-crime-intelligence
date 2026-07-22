"""Normalize user questions — fix common typos and fuzzy-match district names."""

import re
from difflib import get_close_matches

# Common spelling mistakes and aliases
TYPO_REPLACEMENTS = {
    r"\bfive me\b": "give me",
    r"\bgiveme\b": "give me",
    r"\bbengaluru\b": "bengaluru",
    r"\bbanglore\b": "bengaluru",
    r"\bbangaluru\b": "bengaluru",
    r"\bbangalore\b": "bengaluru",
    r"\bbengalore\b": "bengaluru",
    r"\bbengaluru\b": "bengaluru",
    r"\bmysore\b": "mysuru",
    r"\bmysure\b": "mysuru",
    r"\btheift\b": "theft",
    r"\btheifts\b": "theft",
    r"\btehft\b": "theft",
    r"\btehfts\b": "theft",
    r"\bthief\b": "theft",
    r"\brobery\b": "robbery",
    r"\bmurdr\b": "murder",
    r"\bmuder\b": "murder",
    r"\bcybercrime\b": "cyber crime",
    r"\bcybercrimes\b": "cyber crimes",
    r"\bconvction\b": "conviction",
    r"\bconvicted\b": "convicted",
    r"\bconvict\b": "convict",
    r"\bacquital\b": "acquittal",
    r"\bacquited\b": "acquitted",
    r"\bkarnataka\b": "karnataka",
    r"\bkarnatka\b": "karnataka",
    r"\bkarnataca\b": "karnataka",
    r"\bncrb\b": "ncrb",
    r"\bprofil\b": "profile",
    r"\boffender\b": "offender",
    r"\bhotspot\b": "hotspot",
    r"\bhotspots\b": "hotspots",
}

KARNATAKA_DISTRICTS = [
    "bengaluru", "mysuru", "hassan", "shivamogga", "tumakuru", "ballari",
    "belagavi", "kalaburagi", "dakshina kannada", "mandya", "raichur",
    "dharwad", "bidar", "kolar", "chitradurga", "davanagere", "udupi",
    "bagalkot", "vijayapura", "ramanagara", "chikkaballapur", "kodagu",
    "chamarajanagar", "yadgir", "koppal", "gadag", "haveri", "uttara kannada",
    "chikkamagaluru", "vijayanagara",
]

DISTRICT_ALIASES = {
    "bangalore": "bengaluru",
    "bengaluru city": "bengaluru",
    "bengaluru urban": "bengaluru",
    "bengaluru rural": "bengaluru",
}


def normalize_question(question: str) -> tuple[str, str | None]:
    """
    Clean and correct common typos.
    Returns (normalized_question, correction_note or None).
    """
    original = question.strip()
    q = original.lower()

    for pattern, replacement in TYPO_REPLACEMENTS.items():
        q = re.sub(pattern, replacement, q, flags=re.I)

    # Fuzzy match district names mentioned in question
    words = re.findall(r"[a-zA-Z]+", q)
    correction_parts = []
    for i, word in enumerate(words):
        if len(word) < 4:
            continue
        matches = get_close_matches(word.lower(), KARNATAKA_DISTRICTS, n=1, cutoff=0.75)
        if matches and matches[0] != word.lower():
            if word.lower() not in ("crime", "court", "cases", "many", "what", "when", "where"):
                q = re.sub(rf"\b{re.escape(word)}\b", matches[0], q, flags=re.I)
                correction_parts.append(f"'{word}' -> '{matches[0]}'")

    for alias, canonical in DISTRICT_ALIASES.items():
        if alias in q:
            q = q.replace(alias, canonical)

    # Preserve sentence case loosely — capitalize first char
    normalized = q.strip()
    if not normalized:
        return original, None

    note = None
    if normalized != original.lower().strip() or correction_parts:
        parts = correction_parts or []
        if normalized != original.lower().strip() and not parts:
            parts.append("typo corrections applied")
        note = "Corrected: " + ", ".join(parts) if parts else None

    return normalized, note
