"""Match a person named in Kannada script against the English names in CCTNS.

The evidence pipeline extracted names with a Latin-only regex, so a statement
written properly in Kannada produced an empty cross-reference: the district and
the offence were found, the people were not. That is the one place the bilingual
claim broke.

Matching people is not matching districts. Karnataka has 31 districts and their
consonant skeletons are distinct, so a skeleton hit is an identification. The
accused table holds 3,525 distinct names and **17.7% of them collide on
skeleton**:

    rnptl  ->  Eranna Patil, Arun Patel, Eranna Patel, Arun Patil
    mnds   ->  Meena Dias, Amina Desai, Meena Desai, Amina Dias

Telling an officer that ಅರುಣ್ ಪಾಟೀಲ್ is the Arun Patil with 200 prior FIRs,
when the database also holds Eranna Patel, is how an innocent person acquires a
criminal history. So this module never returns *the* match. It returns ranked
candidates with their priors and leaves the identification to the officer.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

# ── Kannada -> Latin ────────────────────────────────────────────────────────
# Deliberately loose. CCTNS spellings are themselves inconsistent transliterations
# ("Nayak"/"Nayaka", "Patil"/"Patel"), so aiming for one correct romanisation
# would miss more than it caught. The output feeds a fuzzy comparison, not a
# lookup key.

_INDEPENDENT_VOWELS = {
    "ಅ": "a", "ಆ": "a", "ಇ": "i", "ಈ": "i", "ಉ": "u", "ಊ": "u",
    "ಋ": "ru", "ಎ": "e", "ಏ": "e", "ಐ": "ai", "ಒ": "o", "ಓ": "o", "ಔ": "au",
}

_CONSONANTS = {
    "ಕ": "k", "ಖ": "kh", "ಗ": "g", "ಘ": "gh", "ಙ": "n",
    "ಚ": "ch", "ಛ": "chh", "ಜ": "j", "ಝ": "jh", "ಞ": "n",
    "ಟ": "t", "ಠ": "th", "ಡ": "d", "ಢ": "dh", "ಣ": "n",
    "ತ": "t", "ಥ": "th", "ದ": "d", "ಧ": "dh", "ನ": "n",
    "ಪ": "p", "ಫ": "ph", "ಬ": "b", "ಭ": "bh", "ಮ": "m",
    "ಯ": "y", "ರ": "r", "ಱ": "r", "ಲ": "l", "ಳ": "l", "ೞ": "l",
    "ವ": "v", "ಶ": "sh", "ಷ": "sh", "ಸ": "s", "ಹ": "h",
}

_MATRAS = {
    "ಾ": "a", "ಿ": "i", "ೀ": "i", "ು": "u", "ೂ": "u", "ೃ": "ru",
    "ೆ": "e", "ೇ": "e", "ೈ": "ai", "ೊ": "o", "ೋ": "o", "ೌ": "au",
}

_VIRAMA = "್"          # removes the consonant's inherent vowel
_ANUSVARA = "ಂ"        # nasal, written as n
_VISARGA = "ಃ"

_KN_CHAR = re.compile(r"[ಀ-೿]")


def has_kannada(text: str) -> bool:
    return bool(_KN_CHAR.search(text or ""))


def transliterate(word: str) -> str:
    """A rough Latin form of a Kannada word. Not reversible, not authoritative."""
    out: list[str] = []
    chars = list(word or "")
    i = 0
    while i < len(chars):
        ch = chars[i]
        if ch in _CONSONANTS:
            out.append(_CONSONANTS[ch])
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt == _VIRAMA:
                i += 2                      # bare consonant, no vowel
                continue
            if nxt in _MATRAS:
                out.append(_MATRAS[nxt])
                i += 2
                continue
            out.append("a")                 # inherent vowel
            i += 1
            continue
        if ch in _INDEPENDENT_VOWELS:
            out.append(_INDEPENDENT_VOWELS[ch])
        elif ch == _ANUSVARA:
            # Assimilates to the following consonant: m before a labial, which
            # is why ಬೇಗಂ is written Begum and not Begun.
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            out.append("m" if (not nxt or nxt in "ಪಫಬಭಮ") else "n")
        elif ch in (_VISARGA, _VIRAMA):
            pass
        elif ch in _MATRAS:
            out.append(_MATRAS[ch])         # stray matra
        elif not _KN_CHAR.match(ch):
            out.append(ch)                  # already Latin, digits, punctuation
        i += 1
    return "".join(out)


@lru_cache(maxsize=8192)
def _ascii_fold(s: str) -> str:
    # Cached: every candidate sweep folds all 3,525 accused names, and the same
    # names come back on every call.
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c))


@lru_cache(maxsize=8192)
def _compare_form(s: str) -> str:
    return re.sub(r"[^a-z]", "", _ascii_fold(s).lower())


def skeleton(s: str) -> str:
    """Consonant skeleton: the recall net. Deliberately lossy, hence candidates.

    The normalisations below are not cosmetic. Each one comes from a real pair
    that failed to match against the live accused table:

        Mirza / ಮಿರ್ಜಾ      ja is romanised j or z depending on the clerk
        Begum / ಬೇಗಂ        the anusvara is m before labials, n elsewhere
        Thomas / ಥಾಮಸ್      aspirates are written th or t, bh or b, at whim
    """
    s = _ascii_fold(s).lower()
    s = re.sub(r"[^a-z]", "", s)
    # Aspirates collapse before vowels are dropped, so "th" becomes "t" rather
    # than surviving as a bare "h".
    s = re.sub(r"(?<=[bcdgjkpstz])h", "", s)
    s = re.sub(r"[aeiouh]", "", s)
    s = s.replace("ph", "f").replace("w", "v")
    s = s.replace("z", "j")          # Mirza / Mirja
    s = s.replace("m", "n")          # anusvara is written either way
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


def similarity(a: str, b: str) -> float:
    """0..1 over the folded, lowercased forms. Ranks within a candidate set."""
    return SequenceMatcher(None, _compare_form(a), _compare_form(b)).ratio()


# ── Finding the names in a Kannada statement ────────────────────────────────
# Kannada has no capitalisation, so there is no orthographic signal that a word
# is a name. These are the grammatical frames a person is actually introduced in
# inside an FIR or a statement. Precision matters far more than recall here: a
# missed name costs a lookup, an invented one costs someone their reputation.

_ROLE = r"(?:ಆರೋಪಿ|ಶಂಕಿತ|ಸಾಕ್ಷಿ|ದೂರುದಾರ|ಚಾಲಕ|ಹೆಸರು)"
_MARKER = r"(?:ಎಂಬುವವರು|ಎಂಬವರು|ಎಂಬಾತ|ಎಂಬ|ಎಂದು|ಎನ್ನುವ|ರವರು|ಅವರು)"

# A name word. Two guards, both learned from real misfires:
#   - the negative lookahead stops the span swallowing the very marker that
#     terminates it, which produced "ಅರುಣ್ ಪಾಟೀಲ್ ಎಂಬುವವರು" as a name;
#   - the 12-character ceiling rejects inflected verbs. Kannada piles suffixes
#     onto a stem, so ಚಲಾಯಿಸುತ್ತಿದ್ದವನನ್ನು ("the one who was driving") is one
#     long word and was being read as part of the driver's name.
_NAME_WORD = rf"(?!{_MARKER}\b)[ಀ-೿]{{2,12}}"
# Two words. Every accused name in CCTNS is given/surname, and allowing three
# let the span reach back over a verb into the previous clause.
_NAME_SPAN = rf"{_NAME_WORD}(?:\s+{_NAME_WORD})?"

# Ordered by precision. A span found by an earlier pattern blocks any later
# overlapping span, so the role-marked reading of a sentence wins.
_PATTERNS = [
    re.compile(rf"{_ROLE}\s+({_NAME_SPAN})\s*{_MARKER}"),
    re.compile(rf"({_NAME_SPAN})\s*{_MARKER}"),
    re.compile(rf"{_ROLE}\s+({_NAME_SPAN})"),
]

# Common words that sit in those frames without being anybody's name.
_NOT_A_NAME = {
    "ಆರೋಪಿ", "ಶಂಕಿತ", "ಸಾಕ್ಷಿ", "ದೂರುದಾರ", "ಚಾಲಕ", "ಹೆಸರು", "ಪೊಲೀಸ್", "ಠಾಣೆ",
    "ಜಿಲ್ಲೆ", "ಪ್ರಕರಣ", "ಅಪರಾಧ", "ನ್ಯಾಯಾಲಯ", "ವಾಹನ", "ಮಹಿಳೆ", "ವ್ಯಕ್ತಿ",
    "ದಿನಾಂಕ", "ರಾತ್ರಿ", "ಬೆಳಿಗ್ಗೆ", "ಸಂಖ್ಯೆ", "ಕಲಂ", "ವರದಿ", "ಹೇಳಿಕೆ", "ತನಿಖೆ",
    "ಸರಕು", "ಮಾಹಿತಿ", "ಗಾಂಜಾ", "ಚಿನ್ನ", "ಸರ", "ಬೈಕ್", "ಅಂಗಡಿ", "ಮಾರುಕಟ್ಟೆ",
    "ರಸ್ತೆ", "ಊರು", "ಗ್ರಾಮ", "ನಗರ", "ಇಬ್ಬರು", "ಒಬ್ಬ", "ಅವನು", "ಅವರು", "ನಾನು",
    # Function words that sit in a name frame without naming anyone.
    "ಸಹ", "ಅಲ್ಲಿದ್ದರು", "ಜನರು", "ಹೇಳಿದರು", "ಗುರುತಿಸಿದೆ", "ನನ್ನ", "ಅವಳು",
    "ಇವರು", "ಯಾರು", "ಎಲ್ಲಿ", "ಆಗ", "ಈಗ", "ನಂತರ", "ಮೊದಲು",
}


def extract_kannada_names(text: str, limit: int = 8) -> list[str]:
    """Kannada-script name candidates, in the order they appear."""
    found: list[str] = []
    claimed: list[tuple[int, int]] = []      # character spans already taken

    for pat in _PATTERNS:
        for m in pat.finditer(text or ""):
            start, end = m.span(1)
            # One person, one reading. Without this the same name surfaced twice
            # (once bare, once with its marker) and the officer saw two entries
            # for one man.
            if any(start < c_end and c_start < end for c_start, c_end in claimed):
                continue
            words = [w for w in m.group(1).strip().split() if w not in _NOT_A_NAME]
            if not words:
                continue
            span = " ".join(words)
            if len(span) < 4 or span in found:
                continue
            found.append(span)
            claimed.append((start, end))
            if len(found) >= limit:
                return found
    return found


# ── Candidate matching ──────────────────────────────────────────────────────
# 0.65, not 0.55. The looser floor let the phrase ಸಹ ಅಲ್ಲಿದ್ದರು ("also were
# there") surface a real person, Usha Ali, at 0.60 - a bystander phrase becoming
# an accused. Genuine transliterations in this database land at 0.74 and above
# (ತಿಮ್ಮಯ್ಯ ಬೇಗಂ -> Thimmaiah Begum is the weakest true match at 0.74), so the
# gap is wide enough to cut through without losing a real name.
MIN_SIMILARITY = 0.65
BACKSTOP_SIMILARITY = 0.72  # no skeleton agreement, so demand a closer string
CONFIDENT_SIMILARITY = 0.80  # below this, sweep the full table before answering


def match_candidates(kn_name: str, db_names: list[str], top: int = 4) -> list[dict]:
    """Ranked candidates for one Kannada name. Never fewer than the ambiguity.

    Returns dicts of {name, score, exact_skeleton}. An empty list means nothing
    in the database resembles this person, which is a real and useful answer.
    """
    latin = transliterate(kn_name)
    skel = skeleton(latin)
    if not skel:
        return []

    scored: list[dict] = []
    for name in db_names:
        db_skel = skeleton(name)
        if not db_skel:
            continue
        # Recall net first: same skeleton, or one contains the other (covers a
        # statement giving only part of the name).
        hit = db_skel == skel or (len(skel) >= 4 and (skel in db_skel or db_skel in skel))
        if not hit:
            continue
        scored.append({
            "name": name,
            "score": round(similarity(latin, name), 3),
            "exact_skeleton": db_skel == skel,
        })

    scored = [s for s in scored if s["score"] >= MIN_SIMILARITY]

    # Backstop. Transliterations disagree badly enough that the skeleton can
    # miss a name a human would read as obviously the same person
    # (ಸಾಲಿಯಾನ್ -> "saliyan" against a recorded "Salian", where CCTNS drops the
    # y glide). It runs whenever the skeleton produced nothing *convincing*, not
    # merely nothing at all: ಬಸವರಾಜ್ ಸಾಲಿಯಾನ್ skeleton-matched "Basavraj Joshi"
    # at 0.69, and that weak wrong answer was hiding the right one. Loosening the
    # skeleton instead would push name collisions from 25% to 31%.
    best = max((s["score"] for s in scored), default=0.0)
    if best < CONFIDENT_SIMILARITY:
        seen = {s["name"] for s in scored}
        # A full ratio() against every accused name is O(n*m) and the sweep ran
        # to ~130ms per name. difflib's own upper bounds are cheap and monotonic
        # (real_quick_ratio >= quick_ratio >= ratio), so anything they rule out
        # cannot clear the threshold and never needs the real comparison.
        matcher = SequenceMatcher()
        matcher.set_seq2(_compare_form(latin))
        for name in db_names:
            if name in seen:
                continue
            matcher.set_seq1(_compare_form(name))
            if (matcher.real_quick_ratio() < BACKSTOP_SIMILARITY
                    or matcher.quick_ratio() < BACKSTOP_SIMILARITY):
                continue
            sc = matcher.ratio()
            if sc >= BACKSTOP_SIMILARITY:
                scored.append({"name": name, "score": round(sc, 3),
                               "exact_skeleton": False})

    scored.sort(key=lambda s: (-s["score"], not s["exact_skeleton"], s["name"]))
    return scored[:top]
