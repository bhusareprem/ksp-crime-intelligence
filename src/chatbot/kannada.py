"""Kannada answers, produced without a model call.

The app understood Kannada perfectly from the start but always replied in
English: the language directive was only a prompt prefix, and the model ignored
it. "Bilingual" was therefore half delivered, since an officer who writes Kannada
still had to read English back.

Rather than asking the model more firmly and hoping, single-value answers are
built by **echoing the officer's own sentence** with the figure substituted for
the interrogative:

    ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ 2023 ರಲ್ಲಿ ಎಷ್ಟು ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು ದಾಖಲಾಗಿವೆ?
    ಮೈಸೂರು ಜಿಲ್ಲೆಯಲ್ಲಿ 2023 ರಲ್ಲಿ 1,089 ಕಳ್ಳತನ ಪ್ರಕರಣಗಳು ದಾಖಲಾಗಿವೆ.

The grammar comes from the officer, so the reply is natural Kannada with no
composition risk, it costs no tokens, and it still works when the model quota is
spent. Anything the echo cannot handle falls through to the model.
"""
from __future__ import annotations

import re

# Kannada block, used to detect script rather than guess from a language flag.
_KN_CHAR = re.compile(r"[ಀ-೿]")

# "how many" / "how much". The word the figure replaces.
_HOW_MANY = re.compile(r"ಎಷ್ಟು")

# Interrogatives that mean the question is not a simple count, so the echo
# would produce a sentence that does not answer it.
_NON_COUNT = re.compile(r"ಯಾವುದು|ಯಾರು|ಏಕೆ|ಹೇಗೆ|ಯಾವ\b")


def has_kannada(text: str) -> bool:
    return bool(_KN_CHAR.search(text or ""))


def kannada_ratio(text: str) -> float:
    """Share of word characters that are Kannada. Used to check a model reply."""
    if not text:
        return 0.0
    words = re.findall(r"\w", text)
    if not words:
        return 0.0
    return len(_KN_CHAR.findall(text)) / len(words)


def wants_kannada(question: str, directive: str | None = None) -> bool:
    """True when the officer asked in Kannada, or the UI requested Kannada."""
    if directive and re.search(r"\bkannada\b", directive, re.I):
        return True
    return has_kannada(question)


def _fmt(value) -> str | None:
    """Indian-style grouping is what the UI uses elsewhere; keep plain commas."""
    try:
        if isinstance(value, str):
            value = value.strip().replace(",", "")
        num = float(value)
    except (TypeError, ValueError):
        return None
    if num != num or num in (float("inf"), float("-inf")):
        return None
    return f"{int(num):,}" if float(num).is_integer() else f"{num:,.2f}"


def answer_count(question: str, value) -> str | None:
    """Kannada sentence for a single-figure answer, or None if not applicable.

    Returns None rather than guessing whenever the echo would not produce a
    sentence that actually answers the question.
    """
    q = (question or "").strip()
    if not has_kannada(q):
        return None
    if _NON_COUNT.search(q):          # "which district", "who", "why", "how"
        return None
    if not _HOW_MANY.search(q):       # nothing to substitute
        return None

    num = _fmt(value)
    if num is None:
        return None

    sentence = _HOW_MANY.sub(num, q, count=1)
    sentence = sentence.strip().rstrip("?？ ").rstrip()
    if not sentence.endswith("."):
        sentence += "."
    return sentence


# A Kannada instruction inside an English prompt is ignored: the model follows
# the dominant language of the whole turn. Every feature that generates prose
# swaps to this system message rather than appending a line to an English one.
SYSTEM_KN = (
    "ನೀವು ಕರ್ನಾಟಕ ರಾಜ್ಯ ಪೊಲೀಸ್‌ನ ಅಪರಾಧ ಗುಪ್ತಚರ ಸಹಾಯಕ. "
    "ಎಲ್ಲಾ ಉತ್ತರಗಳನ್ನು ಕನ್ನಡದಲ್ಲಿಯೇ ಬರೆಯಿರಿ. "
    "ಕೊಟ್ಟಿರುವ ಡೇಟಾದಲ್ಲಿರುವ ಸಂಖ್ಯೆಗಳನ್ನು ಮಾತ್ರ ಬಳಸಿ. ಯಾವುದೇ ಸಂಖ್ಯೆಯನ್ನು ಊಹಿಸಬೇಡಿ. "
    "ಜಿಲ್ಲೆಗಳ ಹೆಸರುಗಳು, ಅಪರಾಧ ವಿಧಗಳು ಮತ್ತು ವ್ಯಕ್ತಿಗಳ ಹೆಸರುಗಳನ್ನು "
    "ಡೇಟಾದಲ್ಲಿ ಇರುವಂತೆಯೇ ಬರೆಯಿರಿ."
)

# Appended to a Kannada turn so the closing instruction is Kannada too.
ASK_KN = "ಮೇಲಿನ ಡೇಟಾವನ್ನು ಆಧರಿಸಿ ಕನ್ನಡದಲ್ಲಿ ಉತ್ತರ ಬರೆಯಿರಿ."


# Data notes are written in English by the SQL layer, so a Kannada answer ended
# with an English footnote. Only the fixed wording is translated; crime head
# names inside a note stay as they are, because those are the literal values
# stored in the database and the officer sees the same spelling in the SQL.
_NOTES_KN = {
    "Figures are lifetime totals across all FIRs on record (2020-2024).":
        "ಅಂಕಿಅಂಶಗಳು ದಾಖಲೆಯಲ್ಲಿರುವ ಎಲ್ಲಾ FIRಗಳ ಜೀವಿತಾವಧಿ ಒಟ್ಟು ಮೊತ್ತ (2020-2024).",
    "Accused with 2+ FIRs — proxy for repeat offenders.":
        "2 ಅಥವಾ ಹೆಚ್ಚು FIRಗಳಿರುವ ಆರೋಪಿಗಳು — ಪುನರಾವರ್ತಿತ ಅಪರಾಧಿಗಳ ಸೂಚಕ.",
    "Filtered on MotiveType='communal'/'caste' and crime names containing riot/communal/atrocity.":
        "MotiveType='communal'/'caste' ಮತ್ತು riot/communal/atrocity ಹೊಂದಿರುವ ಅಪರಾಧ ಹೆಸರುಗಳ ಮೇಲೆ ಫಿಲ್ಟರ್ ಮಾಡಲಾಗಿದೆ.",
}

_NOTE_PREFIX_KN = {
    "Matched crime types: ": "ಹೊಂದಿಕೆಯಾದ ಅಪರಾಧ ಪ್ರಕಾರಗಳು: ",
}


def localize_note(note: str | None) -> str | None:
    """The Kannada wording for a data note, or the note unchanged."""
    if not note:
        return note
    exact = _NOTES_KN.get(note.strip())
    if exact:
        return exact
    for en, kn in _NOTE_PREFIX_KN.items():
        if note.startswith(en):
            return kn + note[len(en):]
    return note


# ── Script hygiene ──────────────────────────────────────────────────────────
# Models writing Kannada occasionally emit a letter from a neighbouring Indic
# script: a real answer came back beginning "ತদন্তಿ", where the middle three
# characters are Bengali. It renders as mismatched glyphs and reads, to a
# Kannada speaker, as though the system does not know the language.
#
# The repair is exact rather than a guess. The Indic blocks in Unicode are laid
# out in the same phonetic order, so a character at offset N in the Bengali
# block is the same letter as offset N in the Kannada block: দ (U+09A6) is at
# offset 0x26, and Kannada 0x0C80 + 0x26 is ದ, the correct letter. The example
# above becomes ತದನ್ತಿ, which is how the word is spelled.
_KANNADA_BASE = 0x0C80
_SIBLING_BLOCKS = (
    0x0900,  # Devanagari
    0x0980,  # Bengali
    0x0A00,  # Gurmukhi
    0x0A80,  # Gujarati
    0x0B00,  # Oriya
    0x0B80,  # Tamil
    0x0C00,  # Telugu
    0x0D00,  # Malayalam
)


def normalize_script(text: str) -> str:
    """Rewrite stray non-Kannada Indic letters as their Kannada counterparts."""
    if not text:
        return text
    out = []
    for ch in text:
        cp = ord(ch)
        for base in _SIBLING_BLOCKS:
            if base <= cp < base + 0x80:
                ch = chr(_KANNADA_BASE + (cp - base))
                break
        out.append(ch)
    return "".join(out)


def foreign_script_chars(text: str) -> list[str]:
    """Non-Kannada Indic characters present, for tests and diagnostics."""
    return [c for c in (text or "")
            if any(b <= ord(c) < b + 0x80 for b in _SIBLING_BLOCKS)]


def system_for(english_system: str, kannada: bool) -> str:
    """The Kannada system prompt when Kannada is wanted, else the English one."""
    return SYSTEM_KN if kannada else english_system


def is_kn(language: str | None) -> bool:
    return (language or "en").strip().lower().startswith("kn")


def single_value(df):
    """The one figure in a 1x1 result, else None."""
    try:
        if df is None or getattr(df, "empty", True):
            return None
        if len(df) != 1 or len(df.columns) != 1:
            return None
        return df.iloc[0, 0]
    except Exception:
        return None
