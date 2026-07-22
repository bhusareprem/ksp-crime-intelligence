"""Route natural language questions to the best database with explicit reasoning."""

from __future__ import annotations

import re
from dataclasses import dataclass

# What each database is for (shown to LLM)
DB_PURPOSE = {
    "ksp_crime": (
        "NCRB national/metro statistics, crime rates, chargesheet rates, "
        "demographic benchmarks 2022–2024, synthetic demo FIRs, named criminals (demo only)"
    ),
    "criminal": (
        "KSP FIR Database — 500k FIRs (2020-2024), 906 stations, 31 districts. "
        "Tables: CaseMaster, Accused (with names), Victim, Unit, District, "
        "CrimeSubHead, CrimeGang, AccusedGangLink, ArrestSurrender. "
        "Has accused names, gang data, communal motive tracking."
    ),
    "cases": (
        "Criminal court cases 2010–2018: convictions, acquittals, "
        "dispositions, case duration, pending trials"
    ),
}


@dataclass
class RouteResult:
    database: str
    reason: str
    confidence: str  # high | medium | low
    needs_web_search: bool = False


def _extract_year(q: str) -> int | None:
    m = re.search(r"\b(20\d{2})\b", q)
    return int(m.group(1)) if m else None


def route_with_reason(question: str) -> RouteResult:
    """Intent-based router — picks DB with explanation for RAG / LLM prompts."""
    q = question.lower()
    year = _extract_year(q)

    # --- ksp_crime: NCRB / national / rates / benchmarks ---
    if re.search(
        r"\bncrb\b|\bnational\b|\ball india\b|\bnationwide\b|\bmetro\b|"
        r"\bbenchmark\b|\bchargesheet rate\b|\bcrime rate\b|\bpopulation lakhs\b|"
        r"\beconomic offence\b|\bcomplaint stat",
        q,
    ):
        return RouteResult(
            "ksp_crime",
            "Question asks for NCRB / national statistics or official crime rates",
            "high",
        )

    # --- criminal: person profile / FIR details by name (Accused table has names) ---
    if re.search(
        r"(?:details?|info|information|profile|data)\s+(?:about|on|for)\s+[A-Za-z]|"
        r"(?:about|on)\s+[A-Za-z].{2,40}\??$|"
        r"^who is\s+[A-Za-z]",
        q,
    ) and not re.search(r"each district|every district|by district", q):
        return RouteResult(
            "criminal",
            "Accused names and FIR details are in criminal DB (Accused.AccusedName)",
            "high",
        )

    # --- criminal: top accused / repeat offenders by name ---
    if re.search(r"\bname[s]?\b", q) and re.search(r"criminal|offender|accused|suspect", q):
        return RouteResult(
            "criminal",
            "Accused names available in Accused.AccusedName in KSP FIR DB",
            "high",
        )
    if re.search(r"who is.*criminal|who's.*criminal|top criminal|main criminal|top accused", q):
        return RouteResult(
            "criminal",
            "Top accused by FIR count in Accused table",
            "high",
        )

    # --- ksp_crime: murder rate (needs population from districts) ---
    if re.search(r"murder", q) and re.search(r"rate|per 100|100k|100000", q):
        return RouteResult(
            "ksp_crime",
            "Murder rate per population uses ksp_crime districts.population + demo FIRs",
            "high",
        )

    # --- cases: court / judicial ---
    if re.search(
        r"\bcourt\b|\bjudicial\b|\bconvict|\bacquit|\bjudge\b|\bdisposition\b|"
        r"\bpending trial\b|\be-court\b|\becourt\b|\bcase duration\b|\bbail\b",
        q,
    ):
        return RouteResult(
            "cases",
            "Question is about court outcomes / judicial dispositions (cases.db 2010–2018)",
            "high",
        )

    # Year-based split: 2010–2018 court vs 2019+ FIR
    if year is not None:
        if year <= 2018 and re.search(r"\bcase[s]?\b|\btrial\b|\bcourt\b", q):
            return RouteResult(
                "cases",
                f"Year {year} is in cases.db range (2010–2018) and question mentions court/cases",
                "high",
            )
        if year >= 2020 and re.search(r"\bfir\b|\btheft|\bmurder|\barrest|\baccused|\brobbery", q):
            return RouteResult(
                "criminal",
                f"Year {year} — use KSP FIR DB (2020–2024, CaseMaster/Accused schema)",
                "high",
            )

    # --- criminal: street-level FIR / police data ---
    if re.search(
        r"\bfir[s]?\b|\btheft|\bmurder|\brobbery|\baccused\b|\barrest|\bpolice station\b|"
        r"\bhotspot\b|\bnetwork\b|\brepeat offender\b|\bprofil|\bbehavior|\bndps\b",
        q,
    ):
        # Ambiguous: "cyber" could be NCRB or FIR
        if re.search(r"\bncrb\b|\bnational\b|\brate\b", q):
            return RouteResult(
                "ksp_crime",
                "Cyber + NCRB/rate keywords → national stats in ksp_crime",
                "medium",
            )
        return RouteResult(
            "criminal",
            "Street-level crime / FIR / accused / profiles → real police data (criminal.db)",
            "high",
        )

    # --- Ambiguous theft without other signals → criminal (real FIRs) ---
    if re.search(r"\btheft|\bcyber|\bcrime count|\bhow many", q):
        if re.search(r"\bncrb\b|\bnational\b|\bmetro\b", q):
            return RouteResult("ksp_crime", "Crime count with NCRB/national context", "medium")
        return RouteResult(
            "criminal",
            "General crime counts default to real FIR data (criminal.db); "
            "use ksp_crime only for NCRB/national rates",
            "medium",
        )

    # Keyword scoring fallback
    scores = {"ksp_crime": 0, "criminal": 0, "cases": 0}
    patterns = {
        "cases": [r"\bcourt\b", r"\bconvict", r"\b2017\b", r"\b2016\b"],
        "ksp_crime": [r"\bncrb\b", r"\bnational\b", r"\brate\b"],
        "criminal": [r"\bfir\b", r"\btheft", r"\b2024\b", r"\b2023\b"],
    }
    for db, pats in patterns.items():
        for pat in pats:
            if re.search(pat, q):
                scores[db] += 1

    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return RouteResult(
            "criminal",
            "Default: criminal.db for general Karnataka crime questions",
            "low",
        )
    return RouteResult(
        best,
        f"Keyword match score: {scores}",
        "low",
    )


def route_question(question: str) -> str:
    """Backward-compatible: return database name only."""
    return route_with_reason(question).database


# Matches "how do I / how to / steps to investigate / procedure for ..." questions
_INVESTIGATIVE = re.compile(
    r"\b("
    r"how\s+(do|to|should|can|would|must)\s+(i|we|you|one|officer|police|investigators?)\s+"
    r"(investigate|handle|approach|solve|crack|process|work\s+on|deal\s+with)|"
    r"how\s+to\s+(investigate|solve|handle|approach|crack|process)\b|"
    r"(steps?|procedure|protocol|guide|method|process|checklist|tips?)\s+(to|for)\s+(investigate|solving?|handling?|approaching?)|"
    r"what\s+(should|do|are\s+the)\s+(i|we|you|steps?|procedure).*invest|"
    r"help\s+(me\s+)?(investigate|solve|handle|crack)\b|"
    r"investigation\s+(guide|procedure|steps?|process|method|protocol|checklist)|"
    r"how\s+do\s+police\s+(handle|investigate|solve)\b|"
    r"(guide|advise|walk)\s+(me\s+)?(on|through)\s+(investing?|solv|handl)"
    r")\b",
    re.I,
)


def is_investigative_question(question: str) -> bool:
    """Returns True for procedural 'how to investigate X' questions that should NOT query the DB."""
    return bool(_INVESTIGATIVE.search(question))


def needs_web_search(question: str) -> bool:
    from src.chatbot.rag.web_search import needs_web_search as _needs

    return _needs(question)
