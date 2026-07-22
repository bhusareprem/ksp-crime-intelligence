"""Rule-based SQL for common crime queries — uses KSP FIR schema (CaseMaster / Accused / Unit)."""

import re
from dataclasses import dataclass

from src.karnataka_data import KARNATAKA_DISTRICTS

DISTRICT_ALIASES = {
    "bangalore": "Bengaluru Urban",
    "bengaluru": "Bengaluru Urban",
    "mysore": "Mysuru",
    "belgaum": "Belagavi",
    "gulbarga": "Kalaburagi",
    "bellary": "Ballari",
    "bijapur": "Vijayapura",
    "chikmagalur": "Chikkamagaluru",
    "shimoga": "Shivamogga",
    "tumkur": "Tumakuru",
    "mangalore": "Dakshina Kannada",
    "hubli": "Dharwad",
    "dakshina": "Dakshina Kannada",
}

DB = "criminal"   # always routes to ksp_fir.duckdb via db_manager


@dataclass
class FallbackQuery:
    db: str
    sql: str
    explanation: str
    note: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_year(text: str) -> int | None:
    m = re.search(r"\b(20\d{2})\b", text)
    return int(m.group(1)) if m else None


def _find_district(text: str) -> str | None:
    q = text.lower()
    for alias, canonical in DISTRICT_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", q):
            return canonical

    for d in KARNATAKA_DISTRICTS:
        name = d["name"].lower()
        parts = name.split()
        for part in parts:
            if len(part) >= 5 and re.search(rf"\b{re.escape(part)}\b", q):
                return d["name"]
        if re.search(rf"\b{re.escape(name)}\b", q):
            return d["name"]

    for d in KARNATAKA_DISTRICTS:
        first = d["name"].split()[0]
        if re.search(rf"\b{re.escape(first.lower())}\b", q):
            return d["name"]

    return None


def _dist_filter(district: str) -> str:
    return f"d.DistrictName ILIKE '%{district}%'"


def _year_filter(year: int | None, alias: str = "cm") -> str:
    if not year:
        return ""
    return f"AND EXTRACT(YEAR FROM {alias}.CrimeRegisteredDate)::INT = {year}"


def _district_from_history(history: list[dict]) -> str | None:
    for turn in reversed(history[-8:]):
        if turn.get("role") != "user":
            continue
        found = _find_district(turn.get("content", ""))
        if found:
            return found
    return None


def _combined_context(question: str, history: list[dict]) -> str:
    parts = [question]
    for turn in history[-8:]:
        parts.append(turn.get("content", ""))
    return " ".join(parts).lower()


def _detect_crime_topic(question: str, history: list[dict]) -> str | None:
    ctx = _combined_context(question, history)
    if re.search(r"\bpocso\b", ctx):
        return "pocso"
    if re.search(r"\bmurder\b", ctx):
        return "murder"
    if re.search(r"\btheft|\brobbery\b", ctx):
        return "theft"
    if re.search(r"\bcyber\b", ctx):
        return "cyber"
    if re.search(r"\bndps|\bdrug|\bnarcot", ctx):
        return "ndps"
    return None


# ── Core FIR join block ────────────────────────────────────────────────────────

def _fir_base(extra_joins: str = "") -> str:
    """Standard join chain: CaseMaster → Unit → District → CrimeSubHead."""
    return f"""
        FROM CaseMaster cm
        JOIN Unit u ON cm.PoliceStationID = u.UnitID
        JOIN District d ON u.DistrictID = d.DistrictID
        JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
        {extra_joins}
    """


def _crime_filter_by_keyword(keyword: str) -> str:
    return f"csh.CrimeHeadName ILIKE '%{keyword}%'"


# ── Pattern helpers ────────────────────────────────────────────────────────────

def _extract_person_name(question: str) -> str | None:
    q = question.strip()
    for pat in (
        r"(?:details?|info|information|profile|data)\s+(?:about|on|for)\s+([A-Za-z][A-Za-z\s'.-]{2,50})",
        r"(?:about|on)\s+([A-Za-z][A-Za-z\s'.-]{2,50})\??$",
        r"^who is\s+([A-Za-z][A-Za-z\s'.-]{2,50})\??$",
    ):
        m = re.search(pat, q, re.I)
        if m:
            name = m.group(1).strip().rstrip("?.!")
            if name.lower() not in ("the top criminal", "top criminal", "karnataka",
                                    "the accused", "accused", "suspect"):
                return name
    return None


def _is_details_followup(question: str) -> bool:
    q = question.strip().lower()
    if _extract_person_name(question):
        return False
    if re.search(r"how many|count|number of|each district|by district|per district", q):
        return False
    return bool(re.search(
        r"\bdetails?\b|\beach case\b|\ball cases\b|\blist (the |all )?cases\b|"
        r"case by case|individual cases|more info|tell me more|"
        r"give me (the )?details|show (me )?(the )?cases|breakdown of cases",
        q,
    ))


def _is_name_followup(question: str) -> bool:
    q = question.strip().lower()
    if re.fullmatch(r"name[s]?", q):
        return True
    return bool(re.match(
        r"^(give me|show me|what are|list|tell me)( the)?\s+names?\??$|"
        r"^(give|show|list)( me)?( the)?\s+names?\??$|"
        r"^who are they\??$|^(their )?names?\??$",
        q,
    )) or (len(q) < 30 and re.search(r"\bnames?\b", q) and not _find_district(question))


def _is_all_districts_followup(question: str) -> bool:
    q = question.lower()
    return bool(re.search(
        r"other district|rest of|missing district|remaining district|"
        r"where are.*district|all district|every district|complete list|"
        r"what about.*district|show all district",
        q,
    ))


def _wants_criminal_names(q: str) -> bool:
    return bool(re.search(
        r"who is.*criminal|who's.*criminal|who are.*criminal|"
        r"top criminal|main criminal|biggest criminal|"
        r"criminal.*name|name.*criminal|offender.*name|\bnames?\b",
        q,
    ))


def _wants_per_district_criminals(q: str) -> bool:
    return bool(re.search(
        r"every district|each district|all district|per district|"
        r"all \d+ district|every district in",
        q,
    ))


# ── SQL builders ───────────────────────────────────────────────────────────────

def _person_details(name: str) -> FallbackQuery:
    safe = name.replace("'", "''")
    return FallbackQuery(
        db=DB,
        sql=f"""
            SELECT a.AccusedName AS name, a.AgeYear AS age,
                   CASE a.GenderID WHEN 1 THEN 'Male' WHEN 2 THEN 'Female' ELSE 'Other' END AS gender,
                   a.District AS district, om.OccupationName AS occupation,
                   rm.ReligionName AS religion, cm.CrimeNo AS fir_no,
                   csh.CrimeHeadName AS crime_type,
                   EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS year,
                   csm.CaseStatusName AS status
            FROM Accused a
            JOIN CaseMaster cm ON cm.CaseMasterID = a.CaseMasterID
            JOIN CrimeSubHead csh ON cm.CrimeMinorHeadID = csh.CrimeSubHeadID
            JOIN CaseStatusMaster csm ON cm.CaseStatusID = csm.CaseStatusID
            LEFT JOIN OccupationMaster om ON a.OccupationID = om.OccupationID
            LEFT JOIN ReligionMaster rm ON a.ReligionID = rm.ReligionID
            WHERE a.AccusedName ILIKE '%{safe}%'
            ORDER BY cm.CrimeRegisteredDate DESC
            LIMIT 50
        """,
        explanation=f"FIR records for accused: {name}",
    )


def _district_crime_overview(district: str, year: int | None) -> FallbackQuery:
    yr = _year_filter(year)
    return FallbackQuery(
        db=DB,
        sql=f"""
            SELECT csh.CrimeHeadName AS crime_type, COUNT(*) AS fir_count,
                   COUNT(DISTINCT ar.AccusedMasterID) AS total_arrested
            {_fir_base("LEFT JOIN ArrestSurrender ar ON ar.CaseMasterID = cm.CaseMasterID")}
            WHERE {_dist_filter(district)} {yr}
            GROUP BY csh.CrimeHeadName
            ORDER BY fir_count DESC LIMIT 10
        """,
        explanation=f"Crime breakdown in {district}",
    )


def _top_accused_statewide(limit: int = 15) -> FallbackQuery:
    return FallbackQuery(
        db=DB,
        sql=f"""
            SELECT a.AccusedName AS name, a.AgeYear AS age, a.District AS district,
                   om.OccupationName AS occupation,
                   COUNT(DISTINCT a.CaseMasterID) AS fir_count
            FROM Accused a
            LEFT JOIN OccupationMaster om ON a.OccupationID = om.OccupationID
            WHERE a.AccusedName IS NOT NULL
            GROUP BY a.AccusedMasterID, a.AccusedName, a.AgeYear, a.District, om.OccupationName
            HAVING COUNT(DISTINCT a.CaseMasterID) > 1
            ORDER BY fir_count DESC
            LIMIT {limit}
        """,
        explanation="Top repeat accused by FIR count",
        note="Accused with 2+ FIRs — proxy for repeat offenders.",
    )


def _top_accused_in_district(district: str, limit: int = 10) -> FallbackQuery:
    return FallbackQuery(
        db=DB,
        sql=f"""
            SELECT a.AccusedName AS name, a.AgeYear AS age,
                   om.OccupationName AS occupation,
                   COUNT(DISTINCT a.CaseMasterID) AS fir_count
            FROM Accused a
            JOIN CaseMaster cm ON a.CaseMasterID = cm.CaseMasterID
            JOIN Unit u ON cm.PoliceStationID = u.UnitID
            JOIN District d ON u.DistrictID = d.DistrictID
            LEFT JOIN OccupationMaster om ON a.OccupationID = om.OccupationID
            WHERE {_dist_filter(district)}
              AND a.AccusedName IS NOT NULL
            GROUP BY a.AccusedMasterID, a.AccusedName, a.AgeYear, om.OccupationName
            ORDER BY fir_count DESC
            LIMIT {limit}
        """,
        explanation=f"Top accused in {district}",
    )


def _top_accused_per_district() -> FallbackQuery:
    return FallbackQuery(
        db=DB,
        sql="""
            WITH ranked AS (
                SELECT d.DistrictName AS district, a.AccusedName AS name,
                       a.AgeYear AS age, COUNT(DISTINCT a.CaseMasterID) AS fir_count,
                       ROW_NUMBER() OVER (
                           PARTITION BY d.DistrictID ORDER BY COUNT(DISTINCT a.CaseMasterID) DESC
                       ) AS rn
                FROM Accused a
                JOIN CaseMaster cm ON a.CaseMasterID = cm.CaseMasterID
                JOIN Unit u ON cm.PoliceStationID = u.UnitID
                JOIN District d ON u.DistrictID = d.DistrictID
                WHERE a.AccusedName IS NOT NULL
                GROUP BY d.DistrictID, d.DistrictName, a.AccusedMasterID, a.AccusedName, a.AgeYear
            )
            SELECT district, name, age, fir_count
            FROM ranked WHERE rn = 1
            ORDER BY district, fir_count DESC
        """,
        explanation="Top accused per district",
    )


def _murder_by_district(year: int) -> FallbackQuery:
    return FallbackQuery(
        db=DB,
        sql=f"""
            SELECT d.DistrictName AS district, COUNT(*) AS murder_firs,
                   d.Population AS population,
                   ROUND(COUNT(*) * 100000.0 / d.Population, 2) AS rate_per_100k
            {_fir_base()}
            WHERE {_crime_filter_by_keyword('murder')}
              AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = {year}
            GROUP BY d.DistrictID, d.DistrictName, d.Population
            ORDER BY murder_firs DESC LIMIT 5
        """,
        explanation=f"Murder FIRs by district {year}",
    )


def _communal_trends(district: str | None, year: int | None) -> FallbackQuery:
    dist_clause = f"AND {_dist_filter(district)}" if district else ""
    yr = _year_filter(year)
    return FallbackQuery(
        db=DB,
        sql=f"""
            SELECT EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS year,
                   d.DistrictName AS district, csh.CrimeHeadName AS crime_type,
                   COUNT(*) AS fir_count
            {_fir_base()}
            WHERE (csh.MotiveType IN ('communal','caste')
                   OR csh.CrimeHeadName ILIKE '%communal%'
                   OR csh.CrimeHeadName ILIKE '%riot%'
                   OR csh.CrimeHeadName ILIKE '%atrocit%'
                   OR csh.CrimeHeadName ILIKE '%religious%')
            {dist_clause} {yr}
            GROUP BY 1, 2, 3
            ORDER BY fir_count DESC LIMIT 50
        """,
        explanation="Communal/hate crime trend",
        note="Filtered on MotiveType='communal'/'caste' and crime names containing riot/communal/atrocity.",
    )


def _gang_query(crime_kw: str | None, district: str | None) -> FallbackQuery:
    spec_clause = f"AND g.Specialization ILIKE '%{crime_kw}%'" if crime_kw else ""
    dist_clause = f"AND d.DistrictName ILIKE '%{district}%'" if district else ""
    return FallbackQuery(
        db=DB,
        sql=f"""
            SELECT g.GangName, g.Specialization, g.ActiveSince,
                   COUNT(DISTINCT agl.AccusedMasterID) AS member_count,
                   COUNT(DISTINCT a.CaseMasterID) AS linked_firs,
                   STRING_AGG(DISTINCT a.AccusedName, ', ' ORDER BY a.AccusedName) AS known_members
            FROM CrimeGang g
            JOIN AccusedGangLink agl ON agl.GangID = g.GangID
            JOIN Accused a ON agl.AccusedMasterID = a.AccusedMasterID
            JOIN CaseMaster cm ON a.CaseMasterID = cm.CaseMasterID
            JOIN Unit u ON cm.PoliceStationID = u.UnitID
            JOIN District d ON u.DistrictID = d.DistrictID
            WHERE 1=1 {spec_clause} {dist_clause}
            GROUP BY g.GangID, g.GangName, g.Specialization, g.ActiveSince
            ORDER BY linked_firs DESC LIMIT 10
        """,
        explanation="Crime gang profiles",
    )


def _accused_fir_records(crime_kw: str | None, district: str | None) -> FallbackQuery:
    crime_clause = f"AND {_crime_filter_by_keyword(crime_kw)}" if crime_kw else ""
    dist_clause = f"AND {_dist_filter(district)}" if district else ""
    return FallbackQuery(
        db=DB,
        sql=f"""
            SELECT a.AccusedName AS name, a.AgeYear AS age, a.District AS district,
                   om.OccupationName AS occupation,
                   csh.CrimeHeadName AS crime_type,
                   EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS year,
                   csm.CaseStatusName AS status, cm.CrimeNo AS fir_no
            {_fir_base()}
            JOIN Accused a ON a.CaseMasterID = cm.CaseMasterID
            LEFT JOIN OccupationMaster om ON a.OccupationID = om.OccupationID
            JOIN CaseStatusMaster csm ON cm.CaseStatusID = csm.CaseStatusID
            WHERE a.AccusedName IS NOT NULL
            {crime_clause} {dist_clause}
            ORDER BY cm.CrimeRegisteredDate DESC LIMIT 30
        """,
        explanation="Accused FIR records",
    )


def _pocso_by_district() -> FallbackQuery:
    return FallbackQuery(
        db=DB,
        sql="""
            SELECT d.DistrictName AS district, COUNT(*) AS pocso_cases
            {_fir_base()}
            WHERE csh.CrimeHeadName ILIKE '%pocso%'
               OR (csh.CrimeHeadID = 4)
            GROUP BY d.DistrictName ORDER BY pocso_cases DESC
        """.replace("{_fir_base()}", _fir_base()),
        explanation="POCSO FIR counts by district",
    )


def _top_crimes_by_year(year: int) -> FallbackQuery:
    return FallbackQuery(
        db=DB,
        sql=f"""
            SELECT csh.CrimeHeadName AS crime_type, COUNT(*) AS count
            {_fir_base()}
            WHERE EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = {year}
            GROUP BY csh.CrimeHeadName ORDER BY count DESC LIMIT 10
        """,
        explanation=f"Top crime types in {year}",
    )


# ── Context helpers ────────────────────────────────────────────────────────────

def expand_question_with_history(question: str, history: list[dict]) -> str:
    if _is_name_followup(question):
        district = _find_district(question) or _district_from_history(history)
        if district:
            return f"top 10 accused/criminal names in {district} district"
        return "top 10 repeat offenders in karnataka"

    if _is_all_districts_followup(question):
        return "top accused in every district in karnataka"

    person = _extract_person_name(question)
    if person:
        return f"FIR records and details for accused {person}"

    if _is_details_followup(question):
        topic = _detect_crime_topic(question, history)
        district = _find_district(question)
        if topic == "pocso":
            return f"POCSO case details{' in ' + district if district else ''}"
        if topic:
            return f"{topic} case details{' in ' + district + ' district' if district else ''}"
        return "case details from previous question"

    return question


# ── Main dispatcher ────────────────────────────────────────────────────────────

def try_fallback_sql(question: str, history: list[dict] | None = None) -> FallbackQuery | None:
    history = history or []
    q = question.lower()
    year = _extract_year(question)
    district = _find_district(question) or _district_from_history(history)

    # --- Person profile by name ---
    person_name = _extract_person_name(question)
    if person_name:
        return _person_details(person_name)

    # --- Communal / hate crime / caste violence trends ---
    if re.search(r"communal|hate\s*crime|religious.*crime|sectarian|caste\s*attack|mob\s*lynch|minority.*crime", q):
        return _communal_trends(district, year)

    # --- Gang / organized crime ---
    if re.search(r"\bgang(s)?\b|organized\s*crime|crime\s*group|syndicate|cartel", q):
        crime_kw = None
        if re.search(r"cyber|online.*fraud|hacking", q):
            crime_kw = "cyber"
        elif re.search(r"fraud|cheating|scam", q):
            crime_kw = "fraud"
        elif re.search(r"murder|homicide", q):
            crime_kw = "murder"
        elif re.search(r"theft|robbery|burglary", q):
            crime_kw = "theft"
        elif re.search(r"narcot|drug|ndps", q):
            crime_kw = "narcot"
        return _gang_query(crime_kw, district)

    # --- Accused / suspect FIR records ---
    if re.search(
        r"\b(accused|suspect|offender)\b.*\b(fir|record|detail|info|data)\b|"
        r"\b(fir|record)\b.*\b(accused|suspect|offender)\b", q
    ):
        crime_kw = None
        if re.search(r"cyber", q):
            crime_kw = "cyber"
        elif re.search(r"fraud|cheat", q):
            crime_kw = "fraud"
        elif re.search(r"murder", q):
            crime_kw = "murder"
        return _accused_fir_records(crime_kw, district)

    # --- Top criminal in every district ---
    if _wants_per_district_criminals(q) and _wants_criminal_names(q):
        return _top_accused_per_district()

    if _is_all_districts_followup(question):
        return _top_accused_per_district()

    # --- Follow-up: "give me names" ---
    if _is_name_followup(question):
        if district:
            return _top_accused_in_district(district)
        return _top_accused_statewide()

    crime_topic = _detect_crime_topic(question, history)

    # --- Follow-up: "give me details" ---
    if _is_details_followup(question):
        if crime_topic == "pocso":
            return _pocso_by_district()
        if crime_topic == "murder":
            yr = year or 2023
            return FallbackQuery(
                db=DB,
                sql=f"""
                    SELECT cm.CrimeNo AS fir_no, d.DistrictName AS district,
                           EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT AS year,
                           csh.CrimeHeadName AS crime_type,
                           csm.CaseStatusName AS status,
                           COUNT(a.AccusedMasterID) AS accused_count
                    {_fir_base()}
                    JOIN CaseStatusMaster csm ON cm.CaseStatusID = csm.CaseStatusID
                    LEFT JOIN Accused a ON a.CaseMasterID = cm.CaseMasterID
                    WHERE {_crime_filter_by_keyword('murder')}
                    {f"AND {_dist_filter(district)}" if district else ""}
                    GROUP BY 1,2,3,4,5
                    ORDER BY 2, 3 DESC LIMIT 100
                """,
                explanation="Individual murder FIR records",
            )

    # --- POCSO ---
    if re.search(r"\bpocso\b", q) or crime_topic == "pocso":
        return _pocso_by_district()

    # --- How many [crime] in each district ---
    if re.search(r"how many|count|number of", q) and re.search(
        r"each district|by district|per district|every district", q
    ):
        if crime_topic:
            yr = year or 2023
            kw = {"murder": "murder", "theft": "theft", "cyber": "cyber", "ndps": "NDPS"}.get(crime_topic, crime_topic)
            return FallbackQuery(
                db=DB,
                sql=f"""
                    SELECT d.DistrictName AS district, COUNT(*) AS fir_count
                    {_fir_base()}
                    WHERE {_crime_filter_by_keyword(kw)}
                    AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = {yr}
                    GROUP BY d.DistrictName ORDER BY fir_count DESC
                """,
                explanation=f"{crime_topic} FIR counts by district {yr}",
            )

    # --- Statewide top accused (no district) ---
    if not district and re.search(r"top|who.*criminal|repeat offender|profile|main criminal", q):
        if re.search(r"criminal|offender|accused|suspect", q):
            if _wants_per_district_criminals(q):
                return _top_accused_per_district()
            return _top_accused_statewide()

    # --- Top accused by name in district ---
    if district and _wants_criminal_names(q):
        return _top_accused_in_district(district)

    # --- Top accused profiles in district ---
    if district and re.search(r"criminal|offender|profile|hotspot|network|accused", q):
        return _top_accused_in_district(district)

    # --- Murder rate / murder count by district ---
    if re.search(r"murder", q) and re.search(r"rate|district|top|count|how many", q):
        yr = year or 2023
        return _murder_by_district(yr)

    # --- NCRB / national stats ---
    if re.search(r"ncrb|national|metro|chargesheet rate|crime rate|benchmark", q):
        yr = year or 2024
        if re.search(r"cyber", q) and re.search(r"bengaluru|bangalore|city|metro", q):
            return FallbackQuery(
                db="ksp_crime",
                sql=f"""
                    SELECT city, year, total_cases, crime_rate, chargesheet_rate, stat_type
                    FROM ncrb_city_stats
                    WHERE city = 'Bengaluru' AND state = 'Karnataka'
                      AND year = {yr} AND stat_type = 'cyber'
                """,
                explanation="NCRB cyber stats for Bengaluru",
            )
        if re.search(r"bengaluru|bangalore", q):
            return FallbackQuery(
                db="ksp_crime",
                sql=f"""
                    SELECT city, year, total_cases, crime_rate, chargesheet_rate, stat_type
                    FROM ncrb_city_stats
                    WHERE city = 'Bengaluru' AND state = 'Karnataka' AND year = {yr}
                    ORDER BY stat_type
                """,
                explanation="NCRB city stats for Bengaluru",
            )
        return FallbackQuery(
            db="ksp_crime",
            sql=f"""
                SELECT year, total_incidence, total_crime_rate, ipc_bns_crime_rate
                FROM ncrb_national_stats WHERE year = {yr}
            """,
            explanation="NCRB national statistics",
        )

    # --- District crime overview ---
    if district and re.search(r"crime|fir|overview|status|how|what", q):
        if not re.search(r"ncrb|national|rate|benchmark", q):
            return _district_crime_overview(district, year)

    # --- Theft in Bengaluru ---
    if re.search(r"theft", q) and re.search(r"bengaluru|bangalore", q):
        yr = year or 2023
        return FallbackQuery(
            db=DB,
            sql=f"""
                SELECT csh.CrimeHeadName AS crime_type, COUNT(*) AS count
                {_fir_base()}
                WHERE d.DistrictName ILIKE '%Bengaluru%'
                  AND csh.CrimeHeadName ILIKE '%theft%'
                  AND EXTRACT(YEAR FROM cm.CrimeRegisteredDate)::INT = {yr}
                GROUP BY csh.CrimeHeadName ORDER BY count DESC
            """,
            explanation="Theft FIRs in Bengaluru",
        )

    # --- Court convictions / acquittals ---
    if re.search(r"convict|acquit", q):
        where_parts = []
        if district:
            where_parts.append(f"district_name ILIKE '%{district.upper()}%'")
        if year:
            where_parts.append(f"year = {year}")
        if "convict" in q:
            where_parts.append("disp_name_s ILIKE '%convict%'")
        elif "acquit" in q:
            where_parts.append("disp_name_s ILIKE '%acquit%'")
        where = "WHERE " + " AND ".join(where_parts) if where_parts else ""
        return FallbackQuery(
            db="cases",
            sql=f"""
                SELECT district_name, disp_name_s, COUNT(*) AS case_count
                FROM cases {where}
                GROUP BY district_name, disp_name_s
                ORDER BY case_count DESC LIMIT 15
            """,
            explanation="Court outcomes",
        )

    # --- Top crimes overall ---
    if re.search(r"top|most common|highest", q) and re.search(r"crime", q) and not district:
        yr = year or 2023
        if yr <= 2018:
            return FallbackQuery(
                db="cases",
                sql=f"SELECT type_name_s, COUNT(*) AS count FROM cases WHERE year={yr} GROUP BY type_name_s ORDER BY count DESC LIMIT 10",
                explanation="Top court case types",
            )
        return _top_crimes_by_year(yr)

    # --- Repeat offenders global ---
    if re.search(r"repeat|profile|risk|dangerous", q) and not district:
        return _top_accused_statewide()

    return None
