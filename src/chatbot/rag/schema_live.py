"""Live schema introspection from SQLite / DuckDB files."""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from pathlib import Path

import duckdb

# Tables the LLM should use most often (full list appended from DB)
KSP_CORE_TABLES = (
    "districts", "police_stations", "crime_heads", "fir_records",
    "criminals", "fir_criminal_link", "ncrb_city_stats", "ncrb_national_stats",
    "ncrb_crime_stats", "ncrb_complaint_stats", "ncrb_economic_headwise",
)

CRIMINAL_CORE_TABLES = (
    "CaseMaster", "Unit", "District", "CrimeSubHead", "Accused",
    "CrimeGang", "AccusedGangLink", "CaseStatusMaster", "OccupationMaster", "Victim",
)

CASES_CORE_TABLES = ("cases",)

VALUE_HINTS = {
    "ksp_crime": """
Data coverage: demo FIRs 2022–2024; NCRB tables 2022–2024.
District names (districts.name): title case — 'Bengaluru Urban', 'Bagalkot', 'Gadag', 'Mysuru'.
  → User says Bangalore/Bengaluru: use WHERE d.name LIKE '%Bengaluru%'
Engine: SQLite — use LIKE (not ILIKE).
Join keys: fir_records.station_id→police_stations; crime_head_id→crime_heads.crime_head_id;
  criminals.district_id→districts.district_id.
Person NAMES only in criminals table (synthetic demo data).
""",
    "criminal": """
Data coverage: 500,000 synthetic Karnataka FIRs, 2020–2024 (CCTNS schema).
Engine: DuckDB — use ILIKE and EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT for the year.
Core join chain:
  CaseMaster cm JOIN Unit u ON cm.PoliceStationID=u.UnitID
                JOIN District d ON u.DistrictID=d.DistrictID
                JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID=csh.CrimeSubHeadID
District names (District.DistrictName): title case — 'Bengaluru Urban', 'Mysuru', 'Gadag'.
  → 'Bangalore'/'Bengaluru' means the district 'Bengaluru Urban'.
Crime type: csh.CrimeHeadName (e.g. 'Murder','Theft','Cyber Crime - Online Fraud','NDPS - Trafficking','POCSO Act Offences').
Accused NAMES exist: Accused.AccusedName (JOIN Accused a ON a.CaseMasterID=cm.CaseMasterID). Gangs: CrimeGang + AccusedGangLink.
Case status: CaseStatusMaster.CaseStatusName ('Charge Sheeted','Pending','Under Investigation',...).
Do NOT use old tables (fir_details, crime_heads, districts, accused_persons, co_accused_links) — they are not in this database.
""",
    "cases": """
Data coverage: e-Courts criminal cases 2010–2018 only.
District names (cases.district_name): UPPERCASE — 'BAGALKOT', 'BENGALURU', 'GADAG'.
  → Use district_name ILIKE '%BAGALKOT%'
Engine: DuckDB — use ILIKE.
Key columns: type_name_s (case type), disp_name_s (disposition), year, case_duration_days.
For convictions: disp_name_s ILIKE '%convict%'. For acquittals: ILIKE '%acquit%'.
""",
}


@lru_cache(maxsize=3)
def _cached_schema(db_path: str, db_name: str) -> str:
    path = Path(db_path)
    if not path.exists():
        return f"(database file not found: {path})"

    if db_name == "ksp_crime":
        return _sqlite_schema(path, KSP_CORE_TABLES)
    return _duckdb_schema(path, _core_tables(db_name))


def _core_tables(db_name: str) -> tuple[str, ...]:
    if db_name == "cases":
        return CASES_CORE_TABLES
    return CRIMINAL_CORE_TABLES


def _sqlite_schema(path: Path, prefer_tables: tuple[str, ...]) -> str:
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        all_tables = [r[0] for r in rows if not r[0].startswith("sqlite_")]
        ordered = [t for t in prefer_tables if t in all_tables]
        ordered += [t for t in all_tables if t not in ordered]

        parts = []
        for table in ordered[:14]:
            cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
            col_str = ", ".join(f"{c[1]} ({c[2]})" for c in cols)
            parts.append(f"  {table}: {col_str}")
        return "Live schema (SQLite):\n" + "\n".join(parts)
    finally:
        conn.close()


def _duckdb_schema(path: Path, prefer_tables: tuple[str, ...]) -> str:
    # Config must match every other reader or DuckDB refuses the connection.
    conn = duckdb.connect(str(path), read_only=True,
                          config={"enable_external_access": False})
    try:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' ORDER BY table_name"
        ).fetchall()
        all_tables = [r[0] for r in rows]
        ordered = [t for t in prefer_tables if t in all_tables]
        ordered += [t for t in all_tables if t not in ordered]

        parts = []
        for table in ordered[:14]:
            cols = conn.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [table],
            ).fetchall()
            col_str = ", ".join(f"{c[0]} ({c[1]})" for c in cols)
            parts.append(f"  {table}: {col_str}")
        return "Live schema (DuckDB):\n" + "\n".join(parts)
    finally:
        conn.close()


def get_live_schema(db_path: Path, db_name: str) -> str:
    return _cached_schema(str(db_path.resolve()), db_name)


def get_value_hints(db_name: str) -> str:
    return VALUE_HINTS.get(db_name, "").strip()


# ── Value grounding (CCTNS) — inject the DB's real district + crime-head values ──
# Matches the question to exact literal filter values so the LLM never guesses a
# value that returns 0 rows (e.g. "drugs" → NDPS heads, "cyber" → the two cyber heads).
import re as _re

_DISTRICT_ALIASES = {
    "bangalore": "Bengaluru Urban", "bengaluru": "Bengaluru Urban", "mysore": "Mysuru",
    "belgaum": "Belagavi", "gulbarga": "Kalaburagi", "bellary": "Ballari",
    "bijapur": "Vijayapura", "mangalore": "Dakshina Kannada", "hubli": "Dharwad",
    "shimoga": "Shivamogga", "tumkur": "Tumakuru",
}

# user word → substring to look for inside CrimeHeadName
_HEAD_SYNONYMS = {
    "drug": "ndps", "drugs": "ndps", "narcotic": "ndps", "ganja": "ndps", "peddler": "ndps",
    "cyber": "cyber", "hacking": "hacking", "phishing": "cyber", "online fraud": "online fraud",
    "fraud": "fraud", "cheat": "cheating", "scam": "cheating", "forgery": "forgery",
    "murder": "murder", "kill": "murder", "homicide": "murder",
    "rape": "rape", "sexual": "sexual", "molest": "sexual harassment", "harass": "harassment",
    "pocso": "pocso", "minor": "pocso",
    "theft": "theft", "steal": "theft", "burglary": "burglary", "housebreak": "trespass",
    "robbery": "robbery", "loot": "robbery", "dacoit": "robbery",
    "snatch": "snatching", "vehicle": "vehicle theft", "car theft": "vehicle theft", "bike theft": "vehicle theft",
    "kidnap": "kidnapping", "abduct": "kidnapping", "missing": "missing person",
    "riot": "riot", "communal": "communal", "caste": "atrocities", "atrocit": "atrocities",
    "religious": "religious hate", "dowry": "dowry", "domestic": "cruelty", "cruelty": "cruelty",
    "stalk": "stalking", "accident": "road accident", "suicide": "abetment to suicide",
    "grievous": "grievous", "assault": "assault", "trespass": "trespass",
    "social media": "social media", "unnatural": "unnatural death",
}

# ── Kannada vocabulary ────────────────────────────────────────────────────
# Kannada is case-marked, so a district name rarely appears in its bare form:
# ಮೈಸೂರು ("Mysuru") becomes ಮೈಸೂರಿನಲ್ಲಿ ("in Mysuru"). Matching the full word
# therefore fails on almost every real question. We match on the consonant stem
# instead (the name minus its final vowel sign), which survives every case ending.
_KN_DISTRICTS = {
    "ಬಾಗಲಕೋಟೆ": "Bagalkot", "ಬಳ್ಳಾರಿ": "Ballari", "ಬೆಳಗಾವಿ": "Belagavi",
    "ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರ": "Bengaluru Rural", "ಬೆಂಗಳೂರು ನಗರ": "Bengaluru Urban",
    "ಬೆಂಗಳೂರು": "Bengaluru Urban", "ಬೀದರ್": "Bidar", "ಬೀದರ": "Bidar",
    "ಚಾಮರಾಜನಗರ": "Chamarajanagara", "ಚಿಕ್ಕಬಳ್ಳಾಪುರ": "Chikkaballapur",
    "ಚಿಕ್ಕಮಗಳೂರು": "Chikkamagaluru", "ಚಿತ್ರದುರ್ಗ": "Chitradurga",
    "ದಕ್ಷಿಣ ಕನ್ನಡ": "Dakshina Kannada", "ಮಂಗಳೂರು": "Dakshina Kannada",
    "ದಾವಣಗೆರೆ": "Davanagere", "ಧಾರವಾಡ": "Dharwad", "ಹುಬ್ಬಳ್ಳಿ": "Dharwad",
    "ಗದಗ": "Gadag", "ಹಾಸನ": "Hassan", "ಹಾವೇರಿ": "Haveri",
    "ಕಲಬುರಗಿ": "Kalaburagi", "ಗುಲಬರ್ಗಾ": "Kalaburagi", "ಕೊಡಗು": "Kodagu",
    "ಮಡಿಕೇರಿ": "Kodagu", "ಕೋಲಾರ": "Kolar", "ಕೊಪ್ಪಳ": "Koppal",
    "ಮಂಡ್ಯ": "Mandya", "ಮೈಸೂರು": "Mysuru", "ರಾಯಚೂರು": "Raichur",
    "ರಾಮನಗರ": "Ramanagara", "ಶಿವಮೊಗ್ಗ": "Shivamogga", "ತುಮಕೂರು": "Tumakuru",
    "ಉಡುಪಿ": "Udupi", "ಉತ್ತರ ಕನ್ನಡ": "Uttara Kannada", "ಕಾರವಾರ": "Uttara Kannada",
    "ವಿಜಯನಗರ": "Vijayanagara", "ವಿಜಯಪುರ": "Vijayapura", "ಯಾದಗಿರಿ": "Yadgir",
}

# Kannada crime word → substring to look for inside CrimeHeadName
_KN_HEAD_SYNONYMS = {
    "ಕಳ್ಳತನ": "theft", "ಚೋರಿ": "theft", "ವಾಹನ ಕಳ್ಳತನ": "vehicle theft",
    "ಕೊಲೆ": "murder", "ಹತ್ಯೆ": "murder", "ಕೊಲೆಯತ್ನ": "attempt to murder",
    "ಅತ್ಯಾಚಾರ": "rape", "ಅತ್ಯಾಚಾರದ": "rape",
    "ದರೋಡೆ": "robbery", "ಸುಲಿಗೆ": "robbery", "ಕನ್ನ": "burglary",
    "ವಂಚನೆ": "cheating", "ಮೋಸ": "cheating", "ಸೈಬರ್": "cyber",
    "ಮಾದಕ": "ndps", "ಗಾಂಜಾ": "ndps", "ಡ್ರಗ್ಸ್": "ndps",
    "ಅಪಹರಣ": "kidnapping", "ನಾಪತ್ತೆ": "missing person",
    "ವರದಕ್ಷಿಣೆ": "dowry", "ದೌರ್ಜನ್ಯ": "atrocities", "ಗಲಭೆ": "riot",
    "ಕೋಮು": "communal", "ಜಾತಿ": "atrocities", "ಬೆಂಬತ್ತು": "stalking",
    "ಅಪಘಾತ": "road accident", "ಆತ್ಮಹತ್ಯೆ": "abetment to suicide",
    "ಲೈಂಗಿಕ": "sexual", "ಕಿರುಕುಳ": "harassment", "ಹಲ್ಲೆ": "assault",
}

# Kannada vowel signs / virama — stripped to get a stem that survives case endings.
_KN_MATRA = "".join(chr(c) for c in range(0x0CBE, 0x0CCD + 1)) + "ೕೖ"


def _kn_stem(word: str) -> str:
    return word.rstrip(_KN_MATRA)


_KN_DISTRICT_STEMS = sorted(
    ((_kn_stem(k), v) for k, v in _KN_DISTRICTS.items()),
    key=lambda kv: -len(kv[0]))          # longest first: "ಬೆಂಗಳೂರು ಗ್ರಾಮಾಂತರ" before "ಬೆಂಗಳೂರು"
_KN_HEAD_STEMS = sorted(
    ((_kn_stem(k), v) for k, v in _KN_HEAD_SYNONYMS.items()),
    key=lambda kv: -len(kv[0]))

_STOP = {"crime", "crimes", "case", "cases", "fir", "firs", "district", "districts", "police",
         "station", "stations", "year", "years", "many", "count", "total", "data", "records",
         "record", "number", "report", "reports", "registered", "list", "show", "give", "what",
         "which", "highest", "most", "top", "accused", "offender", "suspect"}


# The UI prefixes "[Respond in Kannada language.]" when a language is selected.
# That directive is for the answer, not the filter — and the word "Kannada" in it
# matches the districts Dakshina Kannada / Uttara Kannada, which silently
# rewrote every Kannada question to the wrong district. Strip it before any
# value is derived from the text.
_DIRECTIVE_RE = _re.compile(r"^\s*\[[^\]]*\]\s*")


def strip_directive(text: str) -> str:
    return _DIRECTIVE_RE.sub("", text or "")


@lru_cache(maxsize=1)
def _fir_vocab(db_path: str):
    try:
        conn = duckdb.connect(db_path, read_only=True, config={"enable_external_access": False})
        try:
            d = tuple(r[0] for r in conn.execute(
                "SELECT DISTINCT DistrictName FROM District WHERE DistrictName IS NOT NULL ORDER BY 1").fetchall())
            h = tuple(r[0] for r in conn.execute(
                "SELECT DISTINCT CrimeHeadName FROM CrimeSubHead WHERE CrimeHeadName IS NOT NULL ORDER BY 1").fetchall())
            return d, h
        finally:
            conn.close()
    except Exception:
        return (), ()


def match_districts(question: str, db_path: str) -> list[str]:
    """Exact DistrictName values the question refers to (via name or alias)."""
    districts, _ = _fir_vocab(db_path)
    if not districts:
        return []
    question = strip_directive(question)
    ql = " " + question.lower() + " "
    md = []
    for alias, canon in _DISTRICT_ALIASES.items():
        if _re.search(rf"\b{_re.escape(alias)}\b", ql) and canon in districts and canon not in md:
            md.append(canon)
    for stem, canon in _KN_DISTRICT_STEMS:            # Kannada script, any case ending
        if stem and stem in question and canon in districts and canon not in md:
            md.append(canon)
    for d in districts:
        first = d.split()[0].lower()
        if d.lower() in ql or (len(first) >= 5 and _re.search(rf"\b{_re.escape(first)}\b", ql)):
            if d not in md:
                md.append(d)
    return md


def match_crime_heads(question: str, db_path: str) -> list[str]:
    """Exact CrimeHeadName values matching the question (via synonyms + tokens)."""
    _, heads = _fir_vocab(db_path)
    if not heads:
        return []
    question = strip_directive(question)
    ql = " " + question.lower() + " "
    mh = []
    for word, key in _HEAD_SYNONYMS.items():
        if word in ql:
            for h in heads:
                if key in h.lower() and h not in mh:
                    mh.append(h)
    for stem, key in _KN_HEAD_STEMS:                  # Kannada script, any case ending
        if stem and stem in question:
            for h in heads:
                if key in h.lower() and h not in mh:
                    mh.append(h)
    toks = {t for t in _re.findall(r"[a-z]{4,}", ql) if t not in _STOP}
    for h in heads:
        if any(t in h.lower() for t in toks) and h not in mh:
            mh.append(h)
    # "Attempt to Murder" is a separate offence, not a kind of murder. Counting it
    # under "how many murders" inflates the figure, so drop attempt heads unless
    # the question actually asked about attempts (and never drop the only match).
    if not _re.search(r"attempt|ಪ್ರಯತ್ನ|ಯತ್ನ", ql):
        completed = [h for h in mh if not h.lower().startswith("attempt")]
        if completed:
            mh = completed
    return mh


# "in Wakanda district" / "district of Wakanda" — an explicitly named place.
_UNIT_WORD_RE = _re.compile(r"\b(?:districts?|taluks?|jille)\b", _re.I)
_UNIT_OF_RE = _re.compile(r"\b(?:districts?|taluks?)\s+of\s+([A-Za-z][A-Za-z'’ -]{2,30})", _re.I)
_WORD_RE = _re.compile(r"[A-Za-z][A-Za-z'’-]*")
# Words that can sit next to "district" without naming one.
_PLACE_STOP = {
    "the", "this", "that", "these", "those", "each", "every", "any", "all", "which", "what",
    "per", "a", "an", "one", "same", "other", "another", "respective", "individual", "single",
    "given", "many", "much", "few", "several", "top", "total", "highest", "lowest", "most",
    "least", "no", "some", "both", "by", "in", "of", "for", "at", "and", "or", "is", "are",
    "was", "were", "be", "across", "within", "from", "to", "with", "on", "than", "then",
    "crime", "crimes", "police", "state", "karnataka", "reported", "registered", "recorded",
    "filed", "covered", "wise", "level", "each", "my", "our", "their", "its", "it",
}


def unknown_places(question: str, db_path: str) -> list[str]:
    """Place names the question states explicitly that are NOT districts in the DB.

    Without this the model silently drops an unrecognised district filter and
    reports a statewide figure as if it belonged to that place — the most
    dangerous failure mode for a policing tool.
    """
    districts, _ = _fir_vocab(db_path)
    if not districts:
        return []
    known = {d.lower() for d in districts}
    known |= {d.split()[0].lower() for d in districts}
    known |= set(_DISTRICT_ALIASES)
    q = strip_directive(question)

    candidates: list[list[str]] = []
    for m in _UNIT_OF_RE.finditer(q):                    # "district of <Name>"
        toks = _WORD_RE.findall(m.group(1))[:2]
        if toks:
            candidates.append(toks)
    for m in _UNIT_WORD_RE.finditer(q):                  # "<Name> district"
        toks = _WORD_RE.findall(q[:m.start()])[-2:]
        if toks:
            candidates.append(toks)

    out: list[str] = []
    for toks in candidates:
        toks = [t.lower() for t in toks]
        if toks[-1] in _PLACE_STOP:                      # "per district", "many districts"
            continue
        names = []
        if len(toks) == 2 and toks[0] not in _PLACE_STOP:
            names.append(" ".join(toks))                 # "Bengaluru Urban"
        names.append(toks[-1])                           # "Mysuru"
        if any(n in known or (len(n) >= 5 and any(n in k or k in n for k in known))
               for n in names):
            continue
        pretty = " ".join(w.capitalize() for w in names[0].split())
        if pretty not in out:
            out.append(pretty)
    return out


def ground_values(question: str, db_path: str) -> str:
    """Return exact District + CrimeHeadName literals matching the question (CCTNS DB)."""
    md = match_districts(question, db_path)
    mh = match_crime_heads(question, db_path)
    unknown = unknown_places(question, db_path)
    lines = []
    if unknown:
        names = ", ".join(f"'{x}'" for x in unknown[:3])
        lines.append(
            f"!! CRITICAL — {names} is NOT a district in this database. Karnataka has "
            f"{len(_fir_vocab(db_path)[0])} districts and this is not one of them. "
            "You MUST reply that no such district exists in the database and give NO count. "
            "Do NOT drop the filter and report a statewide or state-total number instead — "
            "that would report a figure the user will read as belonging to that place.")
    if md:
        lines.append("District values to filter on (d.DistrictName = or ILIKE): " + ", ".join(f"'{x}'" for x in md[:5]))
    if mh:
        lines.append("CrimeHeadName values matching the question (use csh.CrimeHeadName IN (...) or ILIKE): "
                     + ", ".join(f"'{x}'" for x in mh[:8]))
    if not lines:
        return ""
    return "=== EXACT DB VALUES TO USE IN FILTERS (prevents empty results) ===\n" + "\n".join(lines)
