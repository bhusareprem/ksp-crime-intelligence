"""Responsible-AI guard — flags analyses that touch protected attributes so the
platform can never be used, even inadvertently, for discriminatory policing.

Predictive policing is widely criticised for entrenching bias against communities.
This guard makes that risk explicit: when a query or answer involves caste, religion,
or community, it appends a clear warning that correlation is not causation and the
output must be used only for lawful, non-discriminatory purposes.
"""
import re

_PROTECTED = re.compile(
    r"\b(caste|castes|casteism|religion|religious|communal|community|communities|"
    r"muslim|hindu|christian|sikh|jain|buddhist|dalit|scheduled\s+caste|scheduled\s+tribe|"
    r"\bsc\b|\bst\b|sc/st|minority|minorities|atrocit\w*|ethnic|sect\w*)\b",
    re.I,
)

NOTICE = (
    "⚠️ **Responsible-AI notice** — This analysis touches protected attributes "
    "(caste / religion / community). Correlation is **not** causation, and crime data "
    "reflects reporting and enforcement patterns, not any community. Use strictly for "
    "lawful, non-discriminatory policing — never to profile, target, or over-police any group."
)


def is_sensitive(*texts: str) -> bool:
    joined = " ".join(t for t in texts if t)
    return bool(_PROTECTED.search(joined))


def guard(*texts: str) -> str | None:
    """Return the responsible-AI notice if any text involves protected attributes."""
    return NOTICE if is_sensitive(*texts) else None
